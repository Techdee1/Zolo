
"""Async orchestration for Zolo phone-call approval.

Payment state transitions remain owned by ConsentService.
PIN verification and call management live here.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zolo.consent.models import PaymentRequest
from zolo.consent.service import ConsentService
from zolo.consent.states import State
from zolo.core.config import Settings
from zolo.phone_approval.models import PhoneApprovalEnrolment, PhoneCall
from zolo.phone_approval.pin import verify_pin
from zolo.phone_approval.provider import VoiceProvider


class PhoneApprovalError(Exception):
    """A safe, expected phone-approval refusal."""


class PhoneApprovalService:
    """Manage phone calls, enrolments and PIN lockout."""

    def __init__(self, settings: Settings, consent: ConsentService) -> None:
        self.settings = settings
        self.consent = consent

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
        try:
            return value if isinstance(value, uuid.UUID) else uuid.UUID(value)
        except (ValueError, TypeError, AttributeError) as exc:
            raise PhoneApprovalError("Invalid request identifier.") from exc

    async def initiate_call(
        self,
        session: AsyncSession,
        request_id: str | uuid.UUID,
        provider: VoiceProvider,
    ) -> PhoneCall:
        """Create one outbound call for an eligible, enrolled customer."""

        if not self.settings.feature_phone_call:
            raise PhoneApprovalError("Phone-call approval is disabled.")

        request_uuid = self._as_uuid(request_id)

        result = await session.execute(
            select(PaymentRequest)
            .where(PaymentRequest.id == request_uuid)
            .with_for_update()
        )
        request = result.scalar_one_or_none()

        if request is None or request.customer_id is None:
            raise PhoneApprovalError("Request not found or customer not assigned.")

        if request.channel != "call":
            raise PhoneApprovalError("This request is not using phone approval.")

        if request.state not in (State.CREATED.value, State.READ_BACK.value):
            raise PhoneApprovalError("This request cannot be called in its current state.")

        now = self._now()
        if request.expires_at <= now:
            raise PhoneApprovalError("This request has expired.")

        enrolment_result = await session.execute(
            select(PhoneApprovalEnrolment)
            .where(PhoneApprovalEnrolment.customer_id == str(request.customer_id))
            .with_for_update()
        )
        enrolment = enrolment_result.scalar_one_or_none()

        if enrolment is None:
            raise PhoneApprovalError("Customer is not enrolled for phone approval.")

        # Database timestamps may be naive in some test/database configurations.
        changed_at = enrolment.phone_changed_at
        if changed_at is not None:
            if changed_at.tzinfo is None:
                changed_at = changed_at.replace(tzinfo=UTC)

            cooling_off = timedelta(
                hours=self.settings.phone_cooling_off_hours
            )
            if now - changed_at < cooling_off:
                raise PhoneApprovalError(
                    "Phone approval is paused after a phone-number change."
                )

        if enrolment.locked_until is not None:
            locked_until = enrolment.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=UTC)

            if locked_until > now:
                raise PhoneApprovalError("Phone approvals are temporarily locked.")

        # Enforce the hourly outbound-call limit.
        window_start = now - timedelta(hours=1)
        calls_result = await session.execute(
            select(func.count(PhoneCall.id)).where(
                PhoneCall.request_id == str(request_uuid),
                PhoneCall.started_at >= window_start,
            )
        )
        recent_calls = calls_result.scalar_one()

        if recent_calls >= self.settings.phone_call_attempts_per_hour:
            raise PhoneApprovalError("The call-attempt limit has been reached.")

        # Return the existing live call rather than creating duplicates.
        existing_result = await session.execute(
            select(PhoneCall)
            .where(
                PhoneCall.request_id == str(request_uuid),
                PhoneCall.status.in_(("initiated", "in_progress", "answered")),
            )
            .order_by(PhoneCall.started_at.desc())
        )
        existing_call = existing_result.scalars().first()

        if existing_call is not None:
            await session.commit()
            return existing_call

        public_id = secrets.token_urlsafe(32)
        call = PhoneCall(
            id=str(uuid.uuid4()),
            request_id=str(request_uuid),
            public_id=public_id,
            status="initiated",
        )
        session.add(call)
        await session.commit()
        await session.refresh(call)

        webhook_url = (
            f"{self.settings.public_base_url.rstrip('/')}"
            f"/voice/{public_id}/start"
        )

        try:
            provider_call_id = provider.place_call(
                enrolment.phone_e164,
                webhook_url,
                public_id,
            )
        except Exception as exc:
            call.status = "failed"
            call.outcome = "failed"
            call.ended_at = self._now()
            await session.commit()
            # Do not include provider errors or phone numbers in client-facing errors.
            raise PhoneApprovalError("The outbound call could not be started.") from exc

        call.provider_call_id = provider_call_id
        await session.commit()
        await session.refresh(call)
        return call

    async def get_call_by_public_id(
        self,
        session: AsyncSession,
        public_id: str,
        *,
        lock: bool = False,
    ) -> PhoneCall:
        """Resolve a random call identifier without exposing request IDs in URLs."""

        statement = select(PhoneCall).where(PhoneCall.public_id == public_id)

        if lock:
            statement = statement.with_for_update()

        result = await session.execute(statement)
        call = result.scalar_one_or_none()

        if call is None:
            raise PhoneApprovalError("Call not found.")

        return call

    async def prepare_readback(
        self,
        session: AsyncSession,
        public_id: str,
    ):
        """Run the existing consent read-back flow for the enrolled customer.

        ConsentService remains responsible for setting READ_BACK and recording
        the canonical intent hash. This method records which hash this call heard.
        """

        call = await self.get_call_by_public_id(session, public_id, lock=True)

        request_uuid = self._as_uuid(call.request_id)
        result = await session.execute(
            select(PaymentRequest).where(PaymentRequest.id == request_uuid)
        )
        request = result.scalar_one_or_none()

        if request is None or request.customer_id is None:
            raise PhoneApprovalError("Request not found.")

        if request.channel != "call":
            raise PhoneApprovalError("This request is not using phone approval.")

        enrolment_result = await session.execute(
            select(PhoneApprovalEnrolment).where(
                PhoneApprovalEnrolment.customer_id == str(request.customer_id)
            )
        )
        enrolment = enrolment_result.scalar_one_or_none()

        if enrolment is None:
            raise PhoneApprovalError("Customer is not enrolled for phone approval.")

        readback = await self.consent.get_readback(
            session,
            request.customer_id,
            request_uuid,
            enrolment.language,
        )

        # The consent service owns the canonical byte digest.
        await session.refresh(request)
        if request.intent_hash is None:
            raise PhoneApprovalError("The request has no read-back intent hash.")

        call.intent_hash = request.intent_hash.hex()
        call.status = "answered"
        await session.commit()

        return readback

    async def verify_customer_pin(
        self,
        session: AsyncSession,
        customer_id: uuid.UUID,
        pin: str,
    ) -> bool:
        """Verify a PIN and persist failed-attempt lockout.

        Returns False for an incorrect PIN. Raises PhoneApprovalError if locked.
        Never logs or stores the submitted PIN.
        """

        result = await session.execute(
            select(PhoneApprovalEnrolment)
            .where(PhoneApprovalEnrolment.customer_id == str(customer_id))
            .with_for_update()
        )
        enrolment = result.scalar_one_or_none()

        if enrolment is None:
            raise PhoneApprovalError("Customer is not enrolled for phone approval.")

        now = self._now()
        locked_until = enrolment.locked_until

        if locked_until is not None:
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=UTC)

            if locked_until > now:
                raise PhoneApprovalError("Phone approvals are temporarily locked.")

            enrolment.locked_until = None
            enrolment.failed_attempts = 0

        if verify_pin(enrolment.pin_hash, pin):
            enrolment.failed_attempts = 0
            await session.commit()
            return True

        enrolment.failed_attempts += 1

        if enrolment.failed_attempts >= self.settings.phone_lock_wrong_tries:
            enrolment.locked_until = now + timedelta(
                seconds=self.settings.phone_lock_seconds
            )

        await session.commit()
        return False

    async def decline_call(
        self,
        session: AsyncSession,
        public_id: str,
    ):
        """Decline through the existing consent state machine."""

        call = await self.get_call_by_public_id(session, public_id, lock=True)
        request_uuid = self._as_uuid(call.request_id)

        result = await session.execute(
            select(PaymentRequest).where(PaymentRequest.id == request_uuid)
        )
        request = result.scalar_one_or_none()

        if request is None or request.customer_id is None:
            raise PhoneApprovalError("Request not found.")

        view = await self.consent.decline(
            session,
            request.customer_id,
            request_uuid,
        )

        call.status = "completed"
        call.outcome = "declined"
        call.ended_at = self._now()
        await session.commit()

        return view
