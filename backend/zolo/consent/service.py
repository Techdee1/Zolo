"""The consent engine: the only code that changes request state or calls `bank.transfer`.

Every public method is one transaction: it commits its own work (also before raising, so a lazy
expiry is saved) and returns plain dataclasses, never ORM rows. Time comes from an injectable
clock so expiry is testable without sleeping.
"""

import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from zolo.agents.service import get_agent
from zolo.ai.types import Lang
from zolo.audit.models import AuditEvent
from zolo.audit.service import events_for_request, record
from zolo.bank.accounts import customer_account, get_account
from zolo.bank.adapter import BankAdapter
from zolo.consent.activity import ActivityItem, activity_line
from zolo.consent.audio import AudioLookup, NoAudio
from zolo.consent.intent import Intent, intent_hash
from zolo.consent.machine import EXPIRABLE, apply_transition, reload
from zolo.consent.models import PaymentRequest
from zolo.consent.readback import build_readback, readback_lang
from zolo.consent.states import State
from zolo.core.config import Settings
from zolo.core.errors import ApiError, ErrorCode
from zolo.passkeys.service import PasskeyService, SignatureInvalid
from zolo.risk.rules import check_per_payment, evaluate
from zolo.risk.service import customer_limits, day_window, global_limits

Clock = Callable[[], datetime]
MAX_CODE_TRIES = 25
EXPIRABLE_VALUES = tuple(s.value for s in EXPIRABLE)
SIGNED_STATES = (State.APPROVED.value, State.SUBMITTED.value, State.SETTLED.value)


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Viewer:
    kind: Literal["customer", "agent"]
    id: uuid.UUID


@dataclass(frozen=True)
class CreatedRequest:
    id: uuid.UUID
    claim_code: str | None
    qr_payload: str
    expires_at: datetime
    payee_name: str
    amount_kobo: int
    state: str


@dataclass(frozen=True)
class RequestView:
    id: uuid.UUID
    state: str
    amount_kobo: int
    payee_name: str
    expires_at: datetime
    claimed: bool
    bank_reference: str | None
    failure_reason: str | None


@dataclass(frozen=True)
class ReadbackView:
    text: str
    lang: Lang
    audio_url: str | None
    amount_words: str
    payee_name: str
    amount_kobo: int
    expires_at: datetime


@dataclass(frozen=True)
class Timeline:
    request: "RequestView"
    events: list[AuditEvent]


def _not_found() -> ApiError:
    return ApiError(404, ErrorCode.NOT_FOUND, "Request not found")


def _conflict(detail: str = "") -> ApiError:
    return ApiError(
        409, ErrorCode.STATE_CONFLICT, "The request is not in a state that allows this", detail
    )


def _expired() -> ApiError:
    return ApiError(410, ErrorCode.REQUEST_EXPIRED, "The request has expired")


def view_of(row: PaymentRequest) -> RequestView:
    return RequestView(
        id=row.id,
        state=row.state,
        amount_kobo=row.amount_kobo,
        payee_name=row.payee_verified_name,
        expires_at=row.expires_at,
        claimed=row.customer_id is not None,
        bank_reference=row.bank_reference,
        failure_reason=row.failure_reason,
    )


class ConsentService:
    def __init__(
        self,
        settings: Settings,
        bank: BankAdapter,
        audio: AudioLookup | None = None,
        clock: Clock = utcnow,
        passkeys: PasskeyService | None = None,
    ) -> None:
        self.settings, self.bank = settings, bank
        self.audio: AudioLookup = audio or NoAudio()
        self.clock = clock
        self.passkeys = passkeys or PasskeyService(settings, clock)

    # ------------------------------------------------------------------ helpers

    async def _load(self, session: AsyncSession, request_id: uuid.UUID) -> PaymentRequest:
        row = await reload(session, request_id)
        if row is None:
            raise _not_found()
        return row

    async def _expire_if_due(
        self, session: AsyncSession, row: PaymentRequest, now: datetime
    ) -> PaymentRequest:
        """Lazy expiry: applied whenever a live request is read or written after its deadline."""
        if row.state not in EXPIRABLE or row.expires_at > now:
            return row
        for source in EXPIRABLE:
            done = await apply_transition(
                session, row.id, source, State.EXPIRED, guards=[PaymentRequest.expires_at <= now]
            )
            if done is not None:
                await record(
                    session, "request.expired", "system", request_id=row.id,
                    customer_id=row.customer_id, from_state=source.value, to_state="EXPIRED",
                )  # fmt: skip
                return done
        return await self._load(session, row.id)  # someone else moved it first

    async def _expired_error(self, session: AsyncSession, row: PaymentRequest) -> ApiError:
        """Save the expiry, then report it: the caller raises the returned error."""
        await self._expire_if_due(session, row, self.clock())
        await session.commit()
        return _expired()

    async def _visible(self, session: AsyncSession, row: PaymentRequest, viewer: Viewer) -> None:
        if viewer.kind == "customer":
            ok = row.customer_id == viewer.id
        else:
            payee = await get_account(session, row.payee_account_id)
            ok = payee is not None and payee.agent_id == viewer.id
        if not ok:
            raise _not_found()  # never reveal that a request exists to someone who cannot see it

    # ------------------------------------------------------------------ create (agent)

    async def create_agent_request(
        self,
        session: AsyncSession,
        agent_id: uuid.UUID,
        amount_kobo: int,
        idempotency_key: uuid.UUID | None = None,
    ) -> CreatedRequest:
        if isinstance(amount_kobo, bool) or amount_kobo <= 0 or amount_kobo % 100 != 0:
            # Whole naira only in Phase 1: the spoken readback has no way to say kobo.
            raise ApiError(
                422, ErrorCode.VALIDATION_ERROR, "Amount must be a whole number of naira"
            )
        if not check_per_payment(amount_kobo, global_limits(self.settings)).allowed:
            raise ApiError(422, ErrorCode.LIMIT_EXCEEDED, "Amount is over the payment limit")

        agent = await get_agent(session, agent_id)
        account = await get_account(session, agent.account_id) if agent else None
        if agent is None or account is None:
            raise ApiError(403, ErrorCode.FORBIDDEN, "Not an agent")

        if idempotency_key is not None:
            existing = (
                await session.execute(
                    select(PaymentRequest).where(PaymentRequest.idempotency_key == idempotency_key)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return self._created_view(self._same_or_conflict(existing, account.id, amount_kobo))

        # Never hold a database connection while waiting on the bank (300 to 800 ms, or a timeout).
        account_id, payee_number, payee_bank = account.id, account.account_number, account.bank_code
        await session.commit()
        enquiry = await self.bank.name_enquiry(payee_number, payee_bank)
        if not enquiry.found or enquiry.account_name is None:
            raise ApiError(422, ErrorCode.NAME_ENQUIRY_FAILED, "Could not verify the payee's name")

        now = self.clock()
        expires_at = now.replace(microsecond=0) + timedelta(
            seconds=self.settings.request_ttl_seconds
        )
        for _ in range(MAX_CODE_TRIES):
            row = PaymentRequest(
                id=uuid.uuid4(),
                initiator="agent",
                payee_account_id=account_id,
                payee_verified_name=enquiry.account_name,
                amount_kobo=amount_kobo,
                claim_code=f"{secrets.randbelow(10_000):04d}",
                nonce=secrets.token_bytes(16),
                idempotency_key=idempotency_key or uuid.uuid4(),
                state=State.CREATED.value,
                expires_at=expires_at,
            )
            try:
                async with (
                    session.begin_nested()
                ):  # a savepoint: a clash does not poison the session
                    session.add(row)
                    await session.flush()
            except IntegrityError as exc:
                detail = str(exc.orig)
                if "ux_payment_requests_live_claim_code" in detail:
                    continue  # another live request holds this code: draw again
                if "uq_payment_requests_idempotency_key" in detail and idempotency_key is not None:
                    await session.rollback()
                    existing = (
                        await session.execute(
                            select(PaymentRequest).where(
                                PaymentRequest.idempotency_key == idempotency_key
                            )
                        )
                    ).scalar_one()
                    return self._created_view(
                        self._same_or_conflict(existing, account_id, amount_kobo)
                    )
                raise
            break
        else:
            raise ApiError(503, ErrorCode.INTERNAL_ERROR, "No claim code available, try again")

        await record(
            session, "request.created", f"agent:{agent_id}", request_id=row.id,
            initiator="agent", to_state="CREATED",
        )  # fmt: skip
        await session.commit()
        return self._created_view(row)

    def _same_or_conflict(
        self, existing: PaymentRequest, account_id: uuid.UUID, amount_kobo: int
    ) -> PaymentRequest:
        if existing.payee_account_id != account_id or existing.amount_kobo != amount_kobo:
            raise _conflict("Idempotency-Key was already used for a different request")
        return existing

    def _created_view(self, row: PaymentRequest) -> CreatedRequest:
        base = self.settings.origins[0] if self.settings.origins else ""
        return CreatedRequest(
            id=row.id,
            claim_code=row.claim_code,
            qr_payload=f"{base}/claim?code={row.claim_code}" if row.claim_code else "",
            expires_at=row.expires_at,
            payee_name=row.payee_verified_name,
            amount_kobo=row.amount_kobo,
            state=row.state,
        )

    # ------------------------------------------------------------------ claim (customer)

    async def claim(self, session: AsyncSession, customer_id: uuid.UUID, code: str) -> RequestView:
        now = self.clock()
        live = (State.CREATED.value, State.READ_BACK.value)
        row = (
            await session.execute(
                select(PaymentRequest).where(
                    PaymentRequest.claim_code == code, PaymentRequest.state.in_(live)
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise ApiError(404, ErrorCode.CODE_NOT_FOUND, "No request with that code")
        if row.expires_at <= now:
            raise await self._expired_error(session, row)

        if row.customer_id is None:
            bound = await self._bind(session, row.id, customer_id, now)
            if bound is None:  # lost a race: only the winner may continue
                row = await self._load(session, row.id)
                if row.customer_id != customer_id:
                    raise ApiError(404, ErrorCode.CODE_NOT_FOUND, "No request with that code")
            else:
                row = bound
                await record(
                    session, "request.claimed", f"customer:{customer_id}", request_id=row.id,
                    customer_id=customer_id,
                )  # fmt: skip
        elif row.customer_id != customer_id:
            raise ApiError(404, ErrorCode.CODE_NOT_FOUND, "No request with that code")
        await session.commit()
        return view_of(row)

    async def _bind(
        self, session: AsyncSession, request_id: uuid.UUID, customer_id: uuid.UUID, now: datetime
    ) -> PaymentRequest | None:
        return (
            await session.execute(
                update(PaymentRequest)
                .where(
                    PaymentRequest.id == request_id,
                    PaymentRequest.state == State.CREATED.value,
                    PaymentRequest.customer_id.is_(None),
                    PaymentRequest.expires_at > now,
                )
                .values(customer_id=customer_id)
                .returning(PaymentRequest)
                .execution_options(synchronize_session=False, populate_existing=True)
            )
        ).scalar_one_or_none()

    # ------------------------------------------------------------------ readback (customer)

    async def intent_for(self, session: AsyncSession, row: PaymentRequest) -> Intent:
        """The canonical intent of a claimed request, built from the row as it is right now."""
        payee = await get_account(session, row.payee_account_id)
        if payee is None or row.customer_id is None:
            raise _conflict("Request has no payee or customer")
        return Intent(
            request_id=row.id,
            customer_id=row.customer_id,
            payee_account=payee.account_number,
            payee_bank_code=payee.bank_code,
            payee_name=row.payee_verified_name,
            amount_kobo=row.amount_kobo,
            currency=row.currency,
            nonce=row.nonce,
            expires_at=row.expires_at,
        )

    async def get_readback(
        self, session: AsyncSession, customer_id: uuid.UUID, request_id: uuid.UUID, lang: str
    ) -> ReadbackView:
        language = readback_lang(lang)
        if language is None:
            raise ApiError(422, ErrorCode.VALIDATION_ERROR, "Language not supported for readback")
        now = self.clock()
        row = await self._load(session, request_id)
        if row.customer_id != customer_id:
            raise _not_found()
        row = await self._expire_if_due(session, row, now)
        if row.state == State.EXPIRED.value:
            await session.commit()
            raise _expired()

        digest = intent_hash(await self.intent_for(session, row))
        if row.state == State.CREATED.value:
            moved = await apply_transition(
                session, row.id, State.CREATED, State.READ_BACK,
                guards=[  # the hash must describe exactly the row we read the words from
                    PaymentRequest.customer_id == customer_id,
                    PaymentRequest.expires_at > now,
                    PaymentRequest.expires_at == row.expires_at,
                    PaymentRequest.amount_kobo == row.amount_kobo,
                    PaymentRequest.payee_account_id == row.payee_account_id,
                    PaymentRequest.payee_verified_name == row.payee_verified_name,
                ],
                values={"intent_hash": digest},
            )  # fmt: skip
            if moved is None:
                again = await self._load(session, row.id)
                if again.state != State.READ_BACK.value or again.intent_hash != digest:
                    await session.rollback()
                    raise _conflict("The request changed while it was being read back")
            else:
                await record(
                    session, "request.read_back", f"customer:{customer_id}", request_id=row.id,
                    customer_id=customer_id, lang=language, to_state="READ_BACK",
                )  # fmt: skip
                row = moved
        elif row.state == State.READ_BACK.value:
            if row.intent_hash != digest:
                # Changed after the customer heard it: tell them, never quietly re-read it.
                await record(
                    session, "request.intent_changed", "system", request_id=row.id,
                    customer_id=customer_id, code="INTENT_CHANGED",
                )  # fmt: skip
                await session.commit()
                raise ApiError(
                    409, ErrorCode.INTENT_CHANGED, "This payment changed after you heard it"
                )
        else:
            raise _conflict()

        await session.commit()
        spoken = build_readback(language, row.payee_verified_name, row.amount_kobo)
        return ReadbackView(
            text=spoken.text,
            lang=language,
            audio_url=self.audio.audio_url(spoken.text, language),
            amount_words=spoken.amount_words,
            payee_name=spoken.payee_name,
            amount_kobo=row.amount_kobo,
            expires_at=row.expires_at,
        )

    # ------------------------------------------------------------------ decline (customer)

    async def decline(
        self, session: AsyncSession, customer_id: uuid.UUID, request_id: uuid.UUID
    ) -> RequestView:
        now = self.clock()
        row = await self._load(session, request_id)
        if row.customer_id != customer_id:
            raise _not_found()
        if row.state == State.DECLINED.value:
            return view_of(row)  # declining twice is harmless
        row = await self._expire_if_due(session, row, now)
        if row.state == State.EXPIRED.value:
            await session.commit()
            raise _expired()
        done = await apply_transition(
            session, row.id, State.READ_BACK, State.DECLINED,
            guards=[PaymentRequest.customer_id == customer_id, PaymentRequest.expires_at > now],
        )  # fmt: skip
        if done is None:
            await session.rollback()
            raise _conflict()
        await record(
            session, "request.declined", f"customer:{customer_id}", request_id=row.id,
            customer_id=customer_id, from_state="READ_BACK", to_state="DECLINED",
        )  # fmt: skip
        await session.commit()
        return view_of(done)

    # ------------------------------------------------------------------ challenge and approval

    async def issue_challenge(
        self, session: AsyncSession, customer_id: uuid.UUID, request_id: uuid.UUID
    ) -> dict[str, Any]:
        """WebAuthn options whose challenge is the request's intent hash.

        Re-checks the row against the hash stored at readback first: if anything changed since
        the customer heard it, they are told now instead of after they sign.
        """
        row = await self._load(session, request_id)
        if row.customer_id != customer_id:
            raise _not_found()
        row = await self._expire_if_due(session, row, self.clock())
        if row.state == State.EXPIRED.value:
            await session.commit()
            raise _expired()
        if row.state != State.READ_BACK.value or row.intent_hash is None:
            raise _conflict("Listen to the readback before approving")
        digest = intent_hash(await self.intent_for(session, row))
        if digest != row.intent_hash:
            await record(
                session, "request.intent_changed", "system", request_id=row.id,
                customer_id=customer_id, code="INTENT_CHANGED",
            )  # fmt: skip
            await session.commit()
            raise ApiError(409, ErrorCode.INTENT_CHANGED, "This payment changed after you heard it")
        options = await self.passkeys.issue_challenge(
            session, customer_id, row.id, row.intent_hash, row.expires_at
        )
        await record(
            session, "challenge.issued", f"customer:{customer_id}", request_id=row.id,
            customer_id=customer_id,
        )  # fmt: skip
        await session.commit()
        return options

    async def approve(
        self,
        session: AsyncSession,
        customer_id: uuid.UUID,
        request_id: uuid.UUID,
        assertion: dict[str, Any],
    ) -> RequestView:
        """Verify the passkey assertion and, in ONE transaction, consume the challenge and move
        READ_BACK -> APPROVED; then send the transfer. Returns the final or pending state.

        Checks run in a fixed order: the request, expiry, the challenge, the recomputed hash
        (INTENT_CHANGED), the signature, the signature counter, then risk.
        """
        try:
            return await self._approve(session, customer_id, request_id, assertion)
        except BaseException:
            await session.rollback()  # never leave the row lock held after a refusal
            raise

    async def _approve(
        self,
        session: AsyncSession,
        customer_id: uuid.UUID,
        request_id: uuid.UUID,
        assertion: dict[str, Any],
    ) -> RequestView:
        # Look before locking: it tells a replay of an old approval (ALREADY_USED) apart from
        # losing a race to a simultaneous approval (STATE_CONFLICT).
        seen = await self._load(session, request_id)
        if seen.customer_id != customer_id:
            raise _not_found()
        arrived_after_approval = seen.state != State.READ_BACK.value

        row = (
            await session.execute(
                select(PaymentRequest)
                .where(PaymentRequest.id == request_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        now = self.clock()

        if row.state != State.READ_BACK.value:
            if row.state == State.EXPIRED.value:
                raise _expired()
            if arrived_after_approval and await self.passkeys.challenge_was_used(session, row.id):
                await record(
                    session, "approve.replayed", f"customer:{customer_id}", request_id=row.id,
                    customer_id=customer_id, code="ALREADY_USED",
                )  # fmt: skip
                await session.commit()
                raise ApiError(409, ErrorCode.ALREADY_USED, "This approval was already used")
            raise _conflict()
        if row.expires_at <= now:
            raise await self._expired_error(session, row)

        challenge = await self.passkeys.current_challenge(session, row.id)
        if challenge is None:
            raise ApiError(409, ErrorCode.CHALLENGE_NOT_FOUND, "Ask for a challenge first")

        # The heart of it: rebuild the intent from the row as it is NOW and compare it with
        # what the customer heard (stored hash) and what the challenge carries.
        digest = intent_hash(await self.intent_for(session, row))
        if digest != row.intent_hash or digest != challenge.challenge:
            await record(
                session, "approve.intent_changed", "system", request_id=row.id,
                customer_id=customer_id, code="INTENT_CHANGED",
            )  # fmt: skip
            await session.commit()
            raise ApiError(409, ErrorCode.INTENT_CHANGED, "This payment changed after you heard it")

        try:
            verified = await self.passkeys.verify_assertion(
                session, customer_id, challenge.challenge, assertion
            )
        except SignatureInvalid as exc:
            await record(
                session, "approve.signature_invalid", f"customer:{customer_id}",
                request_id=row.id, customer_id=customer_id, code="SIGNATURE_INVALID",
                reason=exc.reason,
            )  # fmt: skip
            await session.commit()
            raise

        limits = await customer_limits(session, customer_id, self.settings)
        decision = evaluate(
            row.amount_kobo, await self.approved_today_kobo(session, customer_id, now), limits
        )
        if not decision.allowed:
            await record(
                session, "approve.blocked", "system", request_id=row.id,
                customer_id=customer_id, code=decision.code,
            )  # fmt: skip
            await session.commit()
            raise ApiError(422, ErrorCode.LIMIT_EXCEEDED, "This payment is over your limit")

        if not await self.passkeys.consume_challenge(session, challenge.id):
            raise ApiError(409, ErrorCode.ALREADY_USED, "This approval was already used")
        moved = await apply_transition(
            session, row.id, State.READ_BACK, State.APPROVED,
            guards=[
                PaymentRequest.customer_id == customer_id,
                PaymentRequest.expires_at > now,
                PaymentRequest.intent_hash == digest,
            ],
            values={"approved_at": now},
        )  # fmt: skip
        if moved is None:
            raise _conflict()
        await self.passkeys.record_use(session, verified.credential_pk, verified.new_sign_count)
        await record(
            session, "request.approved", f"customer:{customer_id}", request_id=row.id,
            customer_id=customer_id, from_state="READ_BACK", to_state="APPROVED",
        )  # fmt: skip
        await session.commit()
        return await self.settle(session, request_id)

    # ------------------------------------------------------------------ demo console
    # Used only by the demo endpoints. They live here because only the consent module may change
    # request data, and each one refuses to run unless DEMO_MODE is on.

    def _demo_only(self) -> None:
        if not self.settings.demo_mode:
            raise ApiError(404, ErrorCode.NOT_FOUND, "Not found")

    async def demo_tamper(
        self, session: AsyncSession, request_id: uuid.UUID, amount_kobo: int
    ) -> RequestView:
        """Change the amount AFTER the readback, so approval must fail with INTENT_CHANGED."""
        self._demo_only()
        if isinstance(amount_kobo, bool) or amount_kobo <= 0 or amount_kobo % 100 != 0:
            raise ApiError(
                422, ErrorCode.VALIDATION_ERROR, "Amount must be a whole number of naira"
            )
        row = await self._load(session, request_id)
        if row.state != State.READ_BACK.value:
            raise _conflict("Tampering only makes sense after the readback")
        done = (
            await session.execute(
                update(PaymentRequest)
                .where(
                    PaymentRequest.id == request_id, PaymentRequest.state == State.READ_BACK.value
                )
                .values(amount_kobo=amount_kobo)
                .returning(PaymentRequest)
                .execution_options(synchronize_session=False, populate_existing=True)
            )
        ).scalar_one_or_none()
        if done is None:
            await session.rollback()
            raise _conflict()
        await record(
            session, "demo.tampered", "demo", request_id=request_id,
            customer_id=done.customer_id, changed="amount",
        )  # fmt: skip
        await session.commit()
        return view_of(done)

    async def demo_expire(self, session: AsyncSession, request_id: uuid.UUID) -> RequestView:
        """Set expires_at to now. The request becomes EXPIRED the next time anything touches it
        (lazy expiry), so a claim or approval then answers 410, exactly as in real life."""
        self._demo_only()
        done = (
            await session.execute(
                update(PaymentRequest)
                .where(PaymentRequest.id == request_id, PaymentRequest.state.in_(EXPIRABLE_VALUES))
                .values(expires_at=self.clock())
                .returning(PaymentRequest)
                .execution_options(synchronize_session=False, populate_existing=True)
            )
        ).scalar_one_or_none()
        if done is None:
            await session.rollback()
            if await reload(session, request_id) is None:
                raise _not_found()
            raise _conflict("Only a live request can be expired")
        await record(
            session, "demo.expire_now", "demo", request_id=request_id,
            customer_id=done.customer_id, changed="expires_at",
        )  # fmt: skip
        await session.commit()
        return view_of(done)

    async def demo_replay(
        self, session: AsyncSession, request_id: uuid.UUID, assertion: dict[str, Any] | None
    ) -> RequestView:
        """Send the last valid assertion through the normal approve path again. After a real
        approval this is refused with ALREADY_USED, which is the point of the demo."""
        self._demo_only()
        row = await self._load(session, request_id)
        if assertion is None or row.customer_id is None:
            await session.rollback()
            raise _conflict("There is no approval to replay yet")
        return await self.approve(session, row.customer_id, request_id, assertion)

    async def demo_timeline(self, session: AsyncSession, request_id: uuid.UUID) -> Timeline:
        self._demo_only()
        row = await self._expire_if_due(
            session, await self._load(session, request_id), self.clock()
        )
        events = await events_for_request(session, request_id)
        await session.commit()
        return Timeline(view_of(row), events)

    # ------------------------------------------------------------------ status

    async def get_request(
        self, session: AsyncSession, viewer: Viewer, request_id: uuid.UUID
    ) -> RequestView:
        row = await self._load(session, request_id)
        await self._visible(session, row, viewer)
        row = await self._expire_if_due(session, row, self.clock())
        await session.commit()
        return view_of(row)

    async def activity(
        self, session: AsyncSession, customer_id: uuid.UUID, limit: int = 20
    ) -> list[ActivityItem]:
        """The customer's latest payments, newest first, with a readable line for each."""
        now = self.clock()
        rows = list(
            (
                await session.execute(
                    select(PaymentRequest)
                    .where(PaymentRequest.customer_id == customer_id)
                    .order_by(PaymentRequest.created_at.desc())
                    .limit(limit)
                )
            ).scalars()
        )
        items: list[ActivityItem] = []
        for row in rows:
            row = await self._expire_if_due(
                session, row, now
            )  # a stale live request shows as expired
            items.append(
                ActivityItem(
                    row.id, row.state, row.amount_kobo, row.payee_verified_name, row.created_at,
                    activity_line(row.state, row.amount_kobo, row.payee_verified_name),
                )
            )  # fmt: skip
        await session.commit()
        return items

    # ------------------------------------------------------------------ money

    async def approved_today_kobo(
        self, session: AsyncSession, customer_id: uuid.UUID, now: datetime
    ) -> int:
        """Total signed today (a Lagos calendar day): approved, submitted or settled."""
        start, end = day_window(now, self.settings.risk_timezone)
        total = (
            await session.execute(
                select(func.coalesce(func.sum(PaymentRequest.amount_kobo), 0)).where(
                    PaymentRequest.customer_id == customer_id,
                    PaymentRequest.state.in_(SIGNED_STATES),
                    PaymentRequest.approved_at >= start,
                    PaymentRequest.approved_at < end,
                )
            )
        ).scalar_one()
        return int(total)

    async def settle(self, session: AsyncSession, request_id: uuid.UUID) -> RequestView:
        """Send the approved transfer to the bank with the request's own idempotency key.

        Safe to call again for an APPROVED or SUBMITTED request (a retry after a crash or a
        network drop): the bank returns the original result for the same key, so there is never
        a second debit. If the bank cannot be reached the request stays SUBMITTED.
        """
        row = await self._load(session, request_id)
        if row.state == State.APPROVED.value:
            moved = await apply_transition(session, row.id, State.APPROVED, State.SUBMITTED)
            if moved is not None:
                await record(
                    session, "transfer.submitted", "system", request_id=row.id,
                    customer_id=row.customer_id, from_state="APPROVED", to_state="SUBMITTED",
                )  # fmt: skip
            await session.commit()
            row = await self._load(session, request_id)
        if row.state != State.SUBMITTED.value:
            return view_of(row)  # already settled or failed (or not approved): nothing to send

        payee = await get_account(session, row.payee_account_id)
        source = await customer_account(session, row.customer_id) if row.customer_id else None
        if payee is None or source is None:
            return await self._finish(session, row, None, "NO_ACCOUNT")
        await session.commit()  # release the connection before the (slow, external) bank call
        try:
            result = await self.bank.transfer(
                idempotency_key=row.idempotency_key,
                from_account=source.account_number,
                to_account=payee.account_number,
                to_bank=payee.bank_code,
                amount_kobo=row.amount_kobo,
                narration=f"Zolo {str(row.id)[:8]}",
            )
        except Exception:  # noqa: BLE001 - timeout or crash: the outcome is unknown, so keep SUBMITTED
            await record(
                session, "transfer.pending", "system", request_id=row.id,
                customer_id=row.customer_id, code="BANK_UNREACHABLE",
            )  # fmt: skip
            await session.commit()
            return view_of(await self._load(session, request_id))
        if result.status == "SUCCESS" and result.reference:
            return await self._finish(session, row, result.reference, None)
        return await self._finish(session, row, None, result.reason or "BANK_REJECTED")

    async def _finish(
        self, session: AsyncSession, row: PaymentRequest, reference: str | None, failure: str | None
    ) -> RequestView:
        now = self.clock()
        if reference is not None:
            done = await apply_transition(
                session, row.id, State.SUBMITTED, State.SETTLED,
                values={"bank_reference": reference, "settled_at": now},
            )  # fmt: skip
            event = "transfer.settled"
            extra: dict[str, Any] = {"bank_reference": reference}
        else:
            done = await apply_transition(
                session, row.id, State.SUBMITTED, State.FAILED, values={"failure_reason": failure}
            )
            event = "transfer.failed"
            extra = {"reason": failure}
        if done is not None:
            await record(
                session, event, "system", request_id=row.id, customer_id=row.customer_id, **extra
            )
        await session.commit()
        return view_of(await self._load(session, row.id))
