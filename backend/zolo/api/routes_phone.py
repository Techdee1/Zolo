"""Phone-call approval. Off unless FEATURE_PHONE_CALL is set; then every route is a customer's own.

The call is carried by the app's call screen. The same two calls (start, press keys) are all a
telephony provider needs to drive, because the logic lives in `zolo.phone`.
"""

import uuid

from fastapi import APIRouter

from zolo.api import docs
from zolo.api.deps import CustomerDep, DbDep, ServicesDep
from zolo.api.schemas import (
    CallPromptOut,
    PhoneCallIn,
    PhoneCallOut,
    PhoneEnrolIn,
    PhoneEnrolmentOut,
    PhoneKeysIn,
)
from zolo.core.errors import ApiError, ErrorCode
from zolo.phone.service import CallView, PhoneService

router = APIRouter(prefix="/phone", tags=["phone-approval"])


def _service(services: ServicesDep) -> PhoneService:
    if not services.settings.feature_phone_call:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Not found")
    return PhoneService(services.settings, services.consent, services.consent.audio)


def _out(view: CallView, lang: str) -> PhoneCallOut:
    return PhoneCallOut(
        call_id=view.call_id,
        stage=view.stage,
        expects=view.expects,
        prompts=[
            CallPromptOut(key=p.key, text=p.text, audio_url=p.audio_url) for p in view.prompts
        ],
        done=view.done,
        outcome=view.outcome,
        lang=lang,
    )


@router.get(
    "/enrolment",
    response_model=PhoneEnrolmentOut,
    summary="Is phone approval set up for this customer?",
    responses=docs.problems(docs.UNAUTHENTICATED, docs.FORBIDDEN),
)
async def enrolment(
    principal: CustomerDep, session: DbDep, services: ServicesDep
) -> PhoneEnrolmentOut:
    if not services.settings.feature_phone_call:
        return PhoneEnrolmentOut(enabled=False, enrolled=False)  # a 200, so a browser logs no error
    view = await _service(services).enrolment(session, principal.id)
    return PhoneEnrolmentOut(**view.__dict__)


@router.post(
    "/enrol",
    response_model=PhoneEnrolmentOut,
    summary="Set the number to ring and a four digit Zolo PIN",
    responses=docs.problems(
        docs.UNAUTHENTICATED,
        docs.FORBIDDEN,
        (404, "NOT_FOUND: the feature is off"),
        (409, "STATE_CONFLICT: the number belongs to another customer"),
        (422, "VALIDATION_ERROR: the PIN is too easy to guess"),
        docs.RATE_LIMITED,
    ),
)
async def enrol(
    body: PhoneEnrolIn, principal: CustomerDep, session: DbDep, services: ServicesDep
) -> PhoneEnrolmentOut:
    service = _service(services)
    services.limiter.check("phone-enrol", str(principal.id), 5)
    view = await service.enrol(session, principal.id, body.phone, body.pin, body.language)
    return PhoneEnrolmentOut(**view.__dict__)


@router.post(
    "/calls",
    status_code=201,
    response_model=PhoneCallOut,
    summary="Ring the customer to approve one of their own requests",
    responses=docs.problems(
        docs.UNAUTHENTICATED,
        docs.FORBIDDEN,
        docs.NOT_FOUND,
        (409, "STATE_CONFLICT: not set up, paused, locked, or the request cannot be called"),
        (410, "REQUEST_EXPIRED"),
        docs.RATE_LIMITED,
    ),
)
async def start_call(
    body: PhoneCallIn, principal: CustomerDep, session: DbDep, services: ServicesDep
) -> PhoneCallOut:
    service = _service(services)
    view = await service.start(session, principal.id, body.request_id)
    return _out(view, (await service.enrolment(session, principal.id)).language)


@router.post(
    "/calls/{call_id}/keys",
    response_model=PhoneCallOut,
    summary="The keys pressed on the call: 1 approve, 2 decline, 9 repeat, then the PIN",
    responses=docs.problems(
        docs.UNAUTHENTICATED, docs.FORBIDDEN, docs.NOT_FOUND, docs.RATE_LIMITED
    ),
)
async def press_keys(
    call_id: str, body: PhoneKeysIn, principal: CustomerDep, session: DbDep, services: ServicesDep
) -> PhoneCallOut:
    service = _service(services)
    services.limiter.check("phone-keys", str(principal.id), 20)
    try:
        cid = uuid.UUID(call_id)
    except ValueError:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Not found") from None
    view = await service.press(session, principal.id, cid, body.digits)
    return _out(view, (await service.enrolment(session, principal.id)).language)
