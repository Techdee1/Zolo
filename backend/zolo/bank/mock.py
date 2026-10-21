"""MockBankAdapter: behaves like a bank's name enquiry and transfer services.

- Balances live in `mock_accounts`, so a transfer really reduces them and the demo can show it.
- Each transfer is one database transaction of its own (a real bank commits independently of
  Zolo), so a crash on Zolo's side can never leave half a transfer behind.
- Idempotent: a repeated idempotency key returns the stored result and never debits twice. The
  same key with different details is refused, not silently re-run.
- Realistic latency (300 to 800 ms by default; 0 in tests). Failure injection is Phase 2.
"""

import asyncio
import random
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zolo.bank.adapter import CardAuthResult, NameEnquiryResult, TransferResult
from zolo.bank.models import MockAccount, MockTransfer


@dataclass(frozen=True)
class Latency:
    min_ms: int = 300
    max_ms: int = 800


class MockBankAdapter:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        home_bank_code: str = "057",
        latency: Latency | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self._sm = sessionmaker
        self.home_bank_code = home_bank_code
        self._latency = latency or Latency()
        self._sleep = sleep
        self._rng = rng or random.Random()

    async def _pause(self) -> None:
        lo, hi = self._latency.min_ms, self._latency.max_ms
        if hi > 0:
            await self._sleep(self._rng.randint(lo, max(lo, hi)) / 1000)

    # ------------------------------------------------------------------ name enquiry

    async def name_enquiry(self, account: str, bank_code: str) -> NameEnquiryResult:
        await self._pause()
        async with self._sm() as s:
            name = (
                await s.execute(
                    select(MockAccount.account_name).where(
                        MockAccount.account_number == account, MockAccount.bank_code == bank_code
                    )
                )
            ).scalar_one_or_none()
        return NameEnquiryResult(found=name is not None, account_name=name)

    # ------------------------------------------------------------------ transfer

    async def transfer(
        self,
        *,
        idempotency_key: UUID,
        from_account: str,
        to_account: str,
        to_bank: str,
        amount_kobo: int,
        narration: str,
    ) -> TransferResult:
        await self._pause()
        if amount_kobo <= 0:  # nothing to store or replay: refuse outright
            return TransferResult(status="REJECTED", reason="INVALID_AMOUNT")
        async with self._sm() as s, s.begin():
            # Claim the key first. A concurrent call with the same key waits here until the
            # first commits, then finds the stored result below.
            claimed = (
                await s.execute(
                    pg_insert(MockTransfer)
                    .values(
                        idempotency_key=idempotency_key,
                        from_account=from_account,
                        to_account=to_account,
                        to_bank=to_bank,
                        amount_kobo=amount_kobo,
                        narration=narration,
                        status="REJECTED",
                        reason="PENDING",
                    )
                    .on_conflict_do_nothing(index_elements=["idempotency_key"])
                    .returning(MockTransfer.idempotency_key)
                )
            ).first()
            if claimed is None:
                return await self._stored(
                    s, idempotency_key, from_account, to_account, to_bank, amount_kobo
                )

            reason = await self._move(s, from_account, to_account, to_bank, amount_kobo)
            if reason is None:
                reference = "MOCK-" + secrets.token_hex(6).upper()
                await s.execute(
                    update(MockTransfer)
                    .where(MockTransfer.idempotency_key == idempotency_key)
                    .values(
                        amount_kobo=amount_kobo, status="SUCCESS", reference=reference, reason=None
                    )
                )
                return TransferResult(status="SUCCESS", reference=reference)
            await s.execute(
                update(MockTransfer)
                .where(MockTransfer.idempotency_key == idempotency_key)
                .values(reason=reason)
            )
            return TransferResult(status="REJECTED", reason=reason)

    async def _move(
        self, s: AsyncSession, from_account: str, to_account: str, to_bank: str, amount_kobo: int
    ) -> str | None:
        """Debit and credit inside the open transaction. Returns a rejection reason or None."""
        source = (from_account, self.home_bank_code)
        target = (to_account, to_bank)
        if source == target:
            return "SAME_ACCOUNT"
        # Lock both rows in a fixed order so two opposite transfers cannot deadlock.
        keys = sorted({source, target}, key=lambda k: (k[1], k[0]))
        rows = {
            (r.account_number, r.bank_code): r
            for r in (
                await s.execute(
                    select(MockAccount)
                    .where(
                        MockAccount.account_number.in_([k[0] for k in keys]),
                        MockAccount.bank_code.in_([k[1] for k in keys]),
                    )
                    .order_by(MockAccount.bank_code, MockAccount.account_number)
                    .with_for_update()
                )
            ).scalars()
        }
        if source not in rows or target not in rows:
            return "ACCOUNT_NOT_FOUND"
        if rows[source].balance_kobo < amount_kobo:
            return "INSUFFICIENT_FUNDS"
        rows[source].balance_kobo -= amount_kobo
        rows[target].balance_kobo += amount_kobo
        return None

    async def _stored(
        self,
        s: AsyncSession,
        key: UUID,
        from_account: str,
        to_account: str,
        to_bank: str,
        amount_kobo: int,
    ) -> TransferResult:
        row = (
            await s.execute(select(MockTransfer).where(MockTransfer.idempotency_key == key))
        ).scalar_one()
        same = (row.from_account, row.to_account, row.to_bank, row.amount_kobo) == (
            from_account,
            to_account,
            to_bank,
            amount_kobo,
        )
        if not same:  # a reused key with different details is a client bug: refuse, do not re-run
            return TransferResult(status="REJECTED", reason="IDEMPOTENCY_MISMATCH", replayed=True)
        return TransferResult(
            status="SUCCESS" if row.status == "SUCCESS" else "REJECTED",
            reference=row.reference,
            reason=row.reason,
            replayed=True,
        )

    # ------------------------------------------------------------------ card (Phase 2+)

    async def card_auth(self, *, card_ref: str, amount_kobo: int, merchant: str) -> CardAuthResult:
        # Cards are locked by default and Card Guard windows arrive in Phase 2, so until then
        # every attempt is declined.
        await self._pause()
        return CardAuthResult(approved=False, reason="CARD_LOCKED")
