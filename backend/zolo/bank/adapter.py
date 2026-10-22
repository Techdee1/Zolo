"""The bank boundary. In production this is the bank's own name enquiry and transfer services;
in the hackathon it is `MockBankAdapter`. Swapping one for the other changes one class, never the
consent engine.

Only the consent module may call `transfer`.
"""

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID


@dataclass(frozen=True)
class NameEnquiryResult:
    found: bool
    account_name: str | None = None  # the bank-verified name; None when not found


@dataclass(frozen=True)
class TransferResult:
    status: Literal["SUCCESS", "REJECTED"]
    reference: str | None = None  # the bank's reference when it succeeded
    reason: str | None = None  # a code when it was rejected (INSUFFICIENT_FUNDS, ...)
    replayed: bool = False  # True when this is the stored result of an earlier call


@dataclass(frozen=True)
class CardAuthResult:
    approved: bool
    reason: str | None = None  # CARD_LOCKED, OVER_LIMIT, WINDOW_USED (Phase 2+)


class BankAdapter(Protocol):
    async def name_enquiry(self, account: str, bank_code: str) -> NameEnquiryResult: ...

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
        """Move money. A repeated `idempotency_key` MUST return the original result and never
        debit twice. `from_account` is held at the adapter's own bank."""
        ...

    async def card_auth(self, *, card_ref: str, amount_kobo: int, merchant: str) -> CardAuthResult:
        """Phase 2+. Approves only inside an open, unused Card Guard window."""
        ...
