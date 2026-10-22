"""The call: who is rung, what they hear, and what the keypad can do.

One state machine drives the call whatever carries it (a telephony provider or the in-app call
screen): menu, then PIN, then done. A call can only reach the PIN step after the readback was
played in it, and it gets one PIN try. Payment state is never touched here; the consent module
does that.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from zolo.consent.audio import AudioLookup
from zolo.consent.service import ConsentService
from zolo.core.config import Settings
from zolo.core.errors import ApiError, ErrorCode
from zolo.phone import pin as pins
from zolo.phone.models import PhoneCall, PhoneEnrolment
from zolo.phone.prompts import CallLang, Expects, Prompt, prompt


@dataclass
class CallView:
    call_id: uuid.UUID
    stage: str
    expects: Expects
    prompts: list[Prompt]
    done: bool
    outcome: str | None = None  # approved | declined | ended (nothing was sent)
    request_state: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EnrolmentView:
    enrolled: bool
    language: CallLang = "en"
    phone_last4: str = ""
    locked: bool = False
    paused: bool = False  # the number was changed recently


def _lang(value: str) -> CallLang:
    return "pcm" if value == "pcm" else "yo" if value == "yo" else "en"


class PhoneService:
    def __init__(self, settings: Settings, consent: ConsentService, audio: AudioLookup) -> None:
        self.settings, self.consent, self.audio = settings, consent, audio

    def _now(self) -> datetime:
        return self.consent.clock()

    # ------------------------------------------------------------------ enrolment

    async def enrol(
        self, session: AsyncSession, customer_id: uuid.UUID, phone: str, pin: str, language: str
    ) -> EnrolmentView:
        if pins.is_weak(pin, phone):
            raise ApiError(
                422, ErrorCode.VALIDATION_ERROR, "Choose a stronger PIN",
                "Use four digits that are not repeated, in a row, or the end of your number",
            )  # fmt: skip
        now = self._now()
        row = (
            await session.execute(
                select(PhoneEnrolment)
                .where(PhoneEnrolment.customer_id == customer_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        taken = (
            await session.execute(
                select(PhoneEnrolment.customer_id).where(
                    PhoneEnrolment.phone_e164 == phone, PhoneEnrolment.customer_id != customer_id
                )
            )
        ).first()
        if taken is not None:
            raise ApiError(409, ErrorCode.STATE_CONFLICT, "That number is already in use")
        if row is None:
            session.add(
                PhoneEnrolment(
                    customer_id=customer_id, phone_e164=phone, language=language,
                    pin_hash=pins.hash_pin(pin),
                )
            )  # fmt: skip
        else:
            if row.phone_e164 != phone:
                row.phone_e164, row.phone_changed_at = phone, now  # starts the cooling-off period
            row.language, row.pin_hash = language, pins.hash_pin(pin)
            row.failed_attempts, row.locked_until = 0, None
        await session.commit()
        return await self.enrolment(session, customer_id)

    async def enrolment(self, session: AsyncSession, customer_id: uuid.UUID) -> EnrolmentView:
        row = await session.get(PhoneEnrolment, customer_id)
        if row is None:
            return EnrolmentView(enrolled=False)
        now = self._now()
        return EnrolmentView(
            enrolled=True,
            language=_lang(row.language),
            phone_last4=row.phone_e164[-4:],
            locked=bool(row.locked_until and row.locked_until > now),
            paused=self._cooling_off(row),
        )

    def _cooling_off(self, row: PhoneEnrolment) -> bool:
        if row.phone_changed_at is None:
            return False
        return self._now() - row.phone_changed_at < timedelta(
            hours=self.settings.phone_cooling_off_hours
        )

    # ------------------------------------------------------------------ the call

    async def start(
        self, session: AsyncSession, customer_id: uuid.UUID, request_id: uuid.UUID
    ) -> CallView:
        enrol = await session.get(PhoneEnrolment, customer_id)
        if enrol is None:
            raise ApiError(409, ErrorCode.STATE_CONFLICT, "Set up phone approval first")
        now = self._now()
        if self._cooling_off(enrol):
            raise ApiError(
                409, ErrorCode.STATE_CONFLICT, "Phone approval is paused after a number change"
            )
        if enrol.locked_until and enrol.locked_until > now:
            raise ApiError(409, ErrorCode.STATE_CONFLICT, "Phone approval is locked for now")
        recent = (
            await session.execute(
                select(func.count(PhoneCall.id)).where(
                    PhoneCall.customer_id == customer_id,
                    PhoneCall.started_at > now - timedelta(hours=1),
                )
            )
        ).scalar_one()
        if recent >= self.settings.phone_calls_per_hour:
            raise ApiError(429, ErrorCode.RATE_LIMITED, "Too many calls", retry_after=600)

        lang = _lang(enrol.language)
        await self.consent.use_call_channel(session, customer_id, request_id)
        spoken = await self.consent.get_readback(session, customer_id, request_id, lang)
        heard = await self.consent.heard_hash(session, customer_id, request_id)

        await session.execute(  # one live call per request: a new call replaces an old one
            update(PhoneCall)
            .where(PhoneCall.request_id == request_id, PhoneCall.stage != "done")
            .values(stage="done", outcome="ended", ended_at=now)
        )
        call = PhoneCall(request_id=request_id, customer_id=customer_id, heard_hash=heard)
        session.add(call)
        await session.commit()
        return CallView(
            call.id, "menu", "choice",
            [
                prompt("intro", lang, self.audio),
                Prompt("readback", spoken.text, spoken.audio_url),
                prompt("menu", lang, self.audio),
            ],
            done=False,
        )  # fmt: skip

    def _end(
        self, call: PhoneCall, lang: CallLang, key: str, outcome: str, state: str | None
    ) -> CallView:
        call.stage, call.outcome, call.ended_at = "done", outcome, self._now()
        return CallView(
            call.id, "done", "none", [prompt(key, lang, self.audio)], done=True,
            outcome=outcome, request_state=state,
        )  # fmt: skip

    async def press(
        self, session: AsyncSession, customer_id: uuid.UUID, call_id: uuid.UUID, digits: str
    ) -> CallView:
        call = (
            await session.execute(
                select(PhoneCall)
                .where(PhoneCall.id == call_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if call is None or call.customer_id != customer_id:
            raise ApiError(404, ErrorCode.NOT_FOUND, "Not found")
        enrol = await session.get(PhoneEnrolment, customer_id)
        lang = _lang(enrol.language if enrol else "en")
        if call.stage == "done" or enrol is None:
            await session.commit()
            return CallView(call.id, "done", "none", [], done=True, outcome=call.outcome)

        try:
            view = (
                await self._menu(session, call, lang, digits)
                if call.stage == "menu"
                else await self._pin(session, call, enrol, lang, digits)
            )
        except ApiError as err:
            await session.rollback()
            ended = {
                ErrorCode.REQUEST_EXPIRED: "expired",
                ErrorCode.INTENT_CHANGED: "changed",
                ErrorCode.LIMIT_EXCEEDED: "limit",
                ErrorCode.STATE_CONFLICT: "none",
            }.get(err.code)
            if ended is None:
                raise
            call = await session.get(PhoneCall, call_id, populate_existing=True)
            assert call is not None
            view = self._end(call, lang, ended, "ended", None)
        await session.commit()
        return view

    async def _menu(
        self, session: AsyncSession, call: PhoneCall, lang: CallLang, digit: str
    ) -> CallView:
        if digit == "1":
            call.stage = "pin"
            return CallView(
                call.id, "pin", "pin",
                [prompt("privacy", lang, self.audio), prompt("pin", lang, self.audio)], done=False,
            )  # fmt: skip
        if digit == "2":
            await self.consent.decline(session, call.customer_id, call.request_id)
            return self._end(call, lang, "declined", "declined", "DECLINED")
        if digit == "9":
            spoken = await self.consent.get_readback(
                session, call.customer_id, call.request_id, lang
            )
            if (
                await self.consent.heard_hash(session, call.customer_id, call.request_id)
                != call.heard_hash
            ):
                raise ApiError(
                    409, ErrorCode.INTENT_CHANGED, "This payment changed after you heard it"
                )
            return CallView(
                call.id, "menu", "choice",
                [
                    Prompt("readback", spoken.text, spoken.audio_url),
                    prompt("menu", lang, self.audio),
                ],
                done=False,
            )  # fmt: skip
        return self._end(call, lang, "none", "ended", None)  # anything else never approves

    async def _pin(
        self,
        session: AsyncSession,
        call: PhoneCall,
        enrol: PhoneEnrolment,
        lang: CallLang,
        digits: str,
    ) -> CallView:
        if call.pin_used:
            return self._end(call, lang, "none", "ended", None)
        call.pin_used = True  # one try per call
        now = self._now()
        if enrol.locked_until and enrol.locked_until > now:
            return self._end(call, lang, "locked", "ended", None)
        if not pins.verify_pin(enrol.pin_hash, digits):
            enrol.failed_attempts += 1
            if enrol.failed_attempts >= self.settings.phone_lock_wrong_tries:
                enrol.failed_attempts = 0
                enrol.locked_until = now + timedelta(seconds=self.settings.phone_lock_seconds)
            return self._end(call, lang, "wrong_pin", "ended", None)
        enrol.failed_attempts, enrol.locked_until = 0, None
        await session.commit()  # the PIN is spent whatever happens next
        assert call.heard_hash is not None
        done = await self.consent.approve_by_phone(
            session, call.customer_id, call.request_id, bytes(call.heard_hash)
        )
        call = await session.get(PhoneCall, call.id, populate_existing=True)  # type: ignore[assignment]
        assert call is not None
        view = self._end(call, lang, "approved", "approved", done.state)
        return view
