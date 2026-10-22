import uuid
from typing import Annotated

from fastapi import APIRouter, Header

from zolo.api import docs
from zolo.api.deps import AgentDep, DbDep, ServicesDep
from zolo.api.schemas import AgentRequestIn, AgentRequestOut
from zolo.core.errors import ApiError, ErrorCode

router = APIRouter(prefix="/agent", tags=["agent"])


def _idempotency_key(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        raise ApiError(
            422, ErrorCode.VALIDATION_ERROR, "Invalid request", "Idempotency-Key must be a UUID"
        ) from None


@router.post(
    "/requests",
    status_code=201,
    response_model=AgentRequestOut,
    summary="The agent creates a payment request (a cash-out)",
    responses=docs.problems(
        docs.UNAUTHENTICATED,
        docs.FORBIDDEN,
        (409, "STATE_CONFLICT: that Idempotency-Key was used for a different request"),
        (422, "LIMIT_EXCEEDED: over the payment limit; VALIDATION_ERROR; NAME_ENQUIRY_FAILED"),
        docs.RATE_LIMITED,
    ),
)
async def create_request(
    body: AgentRequestIn,
    principal: AgentDep,
    session: DbDep,
    services: ServicesDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AgentRequestOut:
    services.limiter.check(
        "create", str(principal.id), services.settings.create_requests_per_minute
    )
    created = await services.consent.create_agent_request(
        session, principal.id, body.amount_kobo, _idempotency_key(idempotency_key)
    )
    if services.audio_prep is not None:
        # Start the voice now: the customer takes a few seconds to claim and open the request.
        services.audio_prep.schedule(created.payee_name, created.amount_kobo)
    return AgentRequestOut(
        id=created.id,
        claim_code=created.claim_code,
        qr_payload=created.qr_payload,
        expires_at=created.expires_at,
        payee_name=created.payee_name,
    )
