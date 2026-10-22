"""The demo console: everything the stage demo needs to make a failure repeatable.

Mounted ONLY when DEMO_MODE=true, and every endpoint also needs the X-Demo-Token header. These
call the consent service (which alone may change request data) and the seed; they never touch
tables themselves.
"""

import uuid

from fastapi import APIRouter, Depends

from zolo.api import docs
from zolo.api.deps import DbDep, ServicesDep, require_demo
from zolo.api.routes_requests import _out
from zolo.api.schemas import DemoResetOut, RequestOut, TamperIn, TimelineEventOut, TimelineOut
from zolo.demo.seed import reset_demo

router = APIRouter(
    prefix="/demo",
    tags=["demo"],
    dependencies=[Depends(require_demo)],
    responses=docs.problems(
        (401, "UNAUTHENTICATED: missing or wrong X-Demo-Token"),
        (404, "NOT_FOUND: DEMO_MODE is off, or no such request"),
        docs.RATE_LIMITED,
    ),
)


@router.post(
    "/reset",
    response_model=DemoResetOut,
    summary="Put the demo back to its starting state",
    description=(
        "Re-seeds customers, agents, accounts and balances and clears requests, challenges, the "
        "audit trail and transfers. **Registered passkeys are kept**, so the passkey on the demo "
        "phone survives every reset. Also forgets rate-limit counts and captured assertions."
    ),
)
async def reset(services: ServicesDep) -> DemoResetOut:
    summary = await reset_demo(services.sessionmaker, services.settings)
    services.limiter.clear()
    if services.demo is not None:
        services.demo.clear()
    return DemoResetOut(**summary.__dict__)


@router.post(
    "/requests/{request_id}/tamper",
    response_model=RequestOut,
    summary="Change the amount after the readback",
    description="Approval then fails with INTENT_CHANGED and nothing is sent.",
    responses=docs.problems(
        (409, "STATE_CONFLICT: the request is not in READ_BACK"), (422, "VALIDATION_ERROR")
    ),
)
async def tamper(
    request_id: uuid.UUID, session: DbDep, services: ServicesDep, body: TamperIn | None = None
) -> RequestOut:
    amount = (body or TamperIn()).amount_kobo
    return _out(await services.consent.demo_tamper(session, request_id, amount))


@router.post(
    "/requests/{request_id}/replay",
    response_model=RequestOut,
    summary="Re-submit the last valid approval",
    description=(
        "Sends the last accepted assertion through the normal approve path again. After a real "
        "approval the answer is 409 ALREADY_USED, and no money moves a second time."
    ),
    responses=docs.problems(
        (409, "ALREADY_USED, or STATE_CONFLICT when there is nothing to replay")
    ),
)
async def replay(request_id: uuid.UUID, session: DbDep, services: ServicesDep) -> RequestOut:
    assertion = services.demo.last_assertion(request_id) if services.demo is not None else None
    return _out(await services.consent.demo_replay(session, request_id, assertion))


@router.post(
    "/requests/{request_id}/expire",
    response_model=RequestOut,
    summary="Set the request's expiry to now",
    description="It becomes EXPIRED the next time anything reads or acts on it (lazy expiry).",
    responses=docs.problems((409, "STATE_CONFLICT: only a live request can be expired")),
)
async def expire(request_id: uuid.UUID, session: DbDep, services: ServicesDep) -> RequestOut:
    return _out(await services.consent.demo_expire(session, request_id))


@router.get(
    "/requests/{request_id}/timeline",
    response_model=TimelineOut,
    summary="State changes and audit events, for the projector",
)
async def timeline(request_id: uuid.UUID, session: DbDep, services: ServicesDep) -> TimelineOut:
    result = await services.consent.demo_timeline(session, request_id)
    return TimelineOut(
        request=_out(result.request),
        events=[
            TimelineEventOut(id=e.id, at=e.at, event=e.event, actor=e.actor, details=e.details)
            for e in result.events
        ],
    )
