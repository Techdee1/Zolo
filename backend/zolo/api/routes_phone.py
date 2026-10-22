
"""Phone-call approval routes.

All Twilio webhooks validate X-Twilio-Signature before accessing call state.
"""

from datetime import UTC, datetime
from urllib.parse import urlencode
from uuid import UUID
from xml.sax.saxutils import escape

from argon2 import PasswordHasher
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zolo.api.deps import CustomerDep, DbDep, ServicesDep
from zolo.consent.models import PaymentRequest
from zolo.phone_approval.clips import get_call_clip_url
from zolo.phone_approval.models import PhoneApprovalEnrolment, PhoneCall
from zolo.phone_approval.pin import is_weak_pin
from zolo.phone_approval.service import PhoneApprovalService
from zolo.phone_approval.twilio import TwilioProvider
from zolo.phone_approval.twiml import (
    twiml_gather_menu,
    twiml_gather_pin,
    twiml_play_and_hangup,
)

router = APIRouter(tags=["phone-approval"])
_password_hasher = PasswordHasher()


class EnrolRequest(BaseModel):
    phone_number: str = Field(
        pattern=r"^\+[1-9]\d{7,14}$",
        description="Phone number in E.164 format, e.g. +2348012345678",
    )
    pin: str = Field(min_length=4, max_length=8)
    language: str = Field(default="en", min_length=2, max_length=10)


def _phone_service(services: ServicesDep) -> PhoneApprovalService:
    return PhoneApprovalService(services.settings, services.consent)


def _public_url(services: ServicesDep, request: Request) -> str:
    """Build the same public URL configured for Twilio, including query parameters."""
    base = services.settings.public_base_url.rstrip("/")
    url = f"{base}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    return url


async def _validate_twilio_webhook(
    request: Request,
    services: ServicesDep,
) -> dict[str, str]:
    """Reject invalid provider requests before any call lookup or state mutation."""
    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature",
        )

    try:
        form = await request.form()
        params = {str(key): str(value) for key, value in form.multi_items()}
        provider = TwilioProvider()
        valid = provider.validate_signature(
            _public_url(services, request),
            params,
            signature,
        )
    except Exception:
        # Do not return provider details or form values to the caller.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature",
        ) from None

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature",
        )

    return params


def _xml_response(body: str) -> Response:
    return Response(content=body, media_type="application/xml")


def _absolute_audio_url(services: ServicesDep, clip_key: str, language: str) -> str:
    path = get_call_clip_url(clip_key, language)
    return f"{services.settings.public_base_url.rstrip('/')}/{path.lstrip('/')}"


async def _get_call_context(
    db: AsyncSession,
    public_id: str,
) -> tuple[PhoneCall, PaymentRequest, PhoneApprovalEnrolment]:
    result = await db.execute(
        select(PhoneCall).where(PhoneCall.public_id == public_id)
    )
    call = result.scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    try:
        request_id = UUID(str(call.request_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Call not found") from None

    request_result = await db.execute(
        select(PaymentRequest).where(PaymentRequest.id == request_id)
    )
    payment_request = request_result.scalar_one_or_none()
    if payment_request is None or payment_request.customer_id is None:
        raise HTTPException(status_code=404, detail="Request not found")

    enrolment_result = await db.execute(
        select(PhoneApprovalEnrolment).where(
            PhoneApprovalEnrolment.customer_id == str(payment_request.customer_id)
        )
    )
    enrolment = enrolment_result.scalar_one_or_none()
    if enrolment is None:
        raise HTTPException(status_code=404, detail="Phone enrolment not found")

    return call, payment_request, enrolment


@router.post(
    "/phone-approval/enrol",
    status_code=status.HTTP_201_CREATED,
)
async def enrol_phone(
    payload: EnrolRequest,
    customer: CustomerDep,
    db: DbDep,
    services: ServicesDep,
) -> dict[str, str]:
    """Create or update the authenticated customer's phone approval enrolment."""
    if not services.settings.feature_phone_call:
        raise HTTPException(status_code=404, detail="Not found")

    if not payload.pin.isdigit() or is_weak_pin(payload.pin):
        raise HTTPException(
            status_code=422,
            detail="Choose a stronger numeric PIN.",
        )

    customer_id = str(customer.id)
    result = await db.execute(
        select(PhoneApprovalEnrolment)
        .where(PhoneApprovalEnrolment.customer_id == customer_id)
        .with_for_update()
    )
    enrolment = result.scalar_one_or_none()

    now = datetime.now(UTC)
    if enrolment is None:
        enrolment = PhoneApprovalEnrolment(
            customer_id=customer_id,
            phone_e164=payload.phone_number,
            language=payload.language,
            pin_hash=_password_hasher.hash(payload.pin),
            failed_attempts=0,
            locked_until=None,
            phone_changed_at=now,
        )
        db.add(enrolment)
    else:
        if enrolment.phone_e164 != payload.phone_number:
            # A number change starts the cooling-off period.
            enrolment.phone_e164 = payload.phone_number
            enrolment.phone_changed_at = now

        enrolment.language = payload.language
        enrolment.pin_hash = _password_hasher.hash(payload.pin)
        enrolment.failed_attempts = 0
        enrolment.locked_until = None

    await db.commit()
    return {"status": "success", "message": "Phone approval enrolment saved."}


@router.post("/phone/{public_id}/start")
async def call_start(
    public_id: str,
    request: Request,
    db: DbDep,
    services: ServicesDep,
) -> Response:
    await _validate_twilio_webhook(request, services)

    if not services.settings.feature_phone_call:
        raise HTTPException(status_code=404, detail="Not found")

    phone_service = _phone_service(services)
    try:
        await phone_service.prepare_readback(db, public_id)
        call, payment_request, enrolment = await _get_call_context(db, public_id)
    except HTTPException:
        raise
    except (ValueError, LookupError):
        raise HTTPException(status_code=404, detail="Call not found") from None

    intro_url = _absolute_audio_url(services, "call_intro", enrolment.language)
    readback_url = (
        f"{services.settings.public_base_url.rstrip('/')}"
        f"/voice/audio/{escape(enrolment.language)}_readback_{payment_request.id}.mp3"
    )
    menu_url = _absolute_audio_url(services, "call_menu", enrolment.language)
    action_url = (
        f"{services.settings.public_base_url.rstrip('/')}/phone/{public_id}/menu"
    )

    # Return absolute URLs so Twilio does not resolve actions against an
    # unexpected hostname when the application is behind a reverse proxy.
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Play>{escape(intro_url)}</Play>
  {twiml_gather_menu(action_url, readback_url, menu_url)}
</Response>"""
    return _xml_response(xml)


@router.post("/phone/{public_id}/menu")
async def call_menu(
    public_id: str,
    request: Request,
    db: DbDep,
    services: ServicesDep,
) -> Response:
    params = await _validate_twilio_webhook(request, services)

    if not services.settings.feature_phone_call:
        raise HTTPException(status_code=404, detail="Not found")

    call, payment_request, enrolment = await _get_call_context(db, public_id)
    language = enrolment.language
    digit = params.get("Digits", "")

    if digit == "1":
        return _xml_response(
            twiml_gather_pin(
                f"{services.settings.public_base_url.rstrip('/')}/phone/{public_id}/pin",
                _absolute_audio_url(services, "call_privacy", language),
                _absolute_audio_url(services, "call_pin", language),
            )
        )

    if digit == "2":
        await _phone_service(services).decline_call(db, public_id)
        return _xml_response(
            twiml_play_and_hangup(
                _absolute_audio_url(services, "call_bye", language)
            )
        )

    if digit == "9":
        readback_url = (
            f"{services.settings.public_base_url.rstrip('/')}"
            f"/voice/audio/{escape(language)}_readback_{payment_request.id}.mp3"
        )
        menu_url = _absolute_audio_url(services, "call_menu", language)
        return _xml_response(
            twiml_gather_menu(
                f"{services.settings.public_base_url.rstrip('/')}/phone/{public_id}/menu",
                readback_url,
                menu_url,
            )
        )

    # An invalid or missing choice must never approve a payment.
    return _xml_response(
        twiml_play_and_hangup(
            _absolute_audio_url(services, "call_bye", language)
        )
    )



@router.post("/phone/{public_id}/pin")
async def call_pin(
    public_id: str,
    request: Request,
    db: DbDep,
    services: ServicesDep,
) -> Response:
    params = await _validate_twilio_webhook(request, services)

    if not services.settings.feature_phone_call:
        raise HTTPException(status_code=404, detail="Not found")

    call, payment_request, enrolment = await _get_call_context(db, public_id)
    language = enrolment.language

    # Lock the call row and recheck the consumed flag before proceeding.
    locked_result = await db.execute(
        select(PhoneCall)
        .where(PhoneCall.id == call.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    call = locked_result.scalar_one()

    if call.pin_consumed:
        return _xml_response(
            twiml_play_and_hangup(
                _absolute_audio_url(services, "call_bye", language)
            )
        )

    entered_pin = params.get("Digits", "")
    if len(entered_pin) != 4 or not entered_pin.isdigit():
        return _xml_response(
            twiml_play_and_hangup(
                _absolute_audio_url(services, "call_bye", language)
            )
        )

    phone_service = _phone_service(services)
    is_valid = await phone_service.verify_customer_pin(
        db,
        payment_request.customer_id,
        entered_pin,
    )

    if not is_valid:
        return _xml_response(
            twiml_play_and_hangup(
                _absolute_audio_url(services, "call_wrong_pin", language)
            )
        )

    # Only the consent engine may approve and settle the payment.
    try:
        result = await services.consent.approve_phone_pin(
            db,
            payment_request.customer_id,
            UUID(str(payment_request.id)),
        )
    except Exception:
        # Do not claim that a payment succeeded if approval or settlement failed.
        await db.rollback()
        raise

    # The consent service has committed the payment transition. Record the
    # callback outcome separately; consent settlement uses its own idempotency key.
    call.pin_consumed = True
    call.status = "approved"
    call.outcome = str(result.state).lower()
    call.ended_at = datetime.now(UTC)
    await db.commit()

    return _xml_response(
        twiml_play_and_hangup(
            _absolute_audio_url(services, "call_bye", language)
        )
    )


@router.post("/phone/{public_id}/status")
async def call_status(
    public_id: str,
    request: Request,
    db: DbDep,
    services: ServicesDep,
) -> dict[str, str]:
    params = await _validate_twilio_webhook(request, services)

    if not services.settings.feature_phone_call:
        raise HTTPException(status_code=404, detail="Not found")

    result = await db.execute(
        select(PhoneCall)
        .where(PhoneCall.public_id == public_id)
        .with_for_update()
    )
    call = result.scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    provider_status = params.get("CallStatus", "").lower()
    allowed_statuses = {
        "queued",
        "initiated",
        "ringing",
        "in-progress",
        "completed",
        "busy",
        "failed",
        "no-answer",
        "canceled",
    }

    if provider_status in allowed_statuses:
        # Preserve terminal application outcomes such as declined/approved.
        if call.status not in {"completed", "declined", "approved"}:
            call.status = provider_status.replace("-", "_")

        if provider_status in {
            "completed",
            "busy",
            "failed",
            "no-answer",
            "canceled",
        }:
            call.ended_at = datetime.now(UTC)

        await db.commit()

    return {"status": "received"}
