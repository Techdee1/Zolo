import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query

from zolo.api import docs
from zolo.api.deps import CustomerDep, DbDep, ServicesDep, UserDep
from zolo.api.schemas import AssertionIn, ClaimIn, ReadbackOut, RequestOut
from zolo.consent.service import ReadbackView, RequestView, Viewer
from zolo.core.errors import ApiError, ErrorCode

router = APIRouter(prefix="/requests", tags=["requests"])


def _out(view: RequestView) -> RequestOut:
    return RequestOut(**view.__dict__)


@router.post(
    "/claim",
    response_model=RequestOut,
    summary="The customer links a request by its code or QR payload",
    responses=docs.problems(
        docs.UNAUTHENTICATED,
        docs.FORBIDDEN,
        (404, "CODE_NOT_FOUND: no live request has that code"),
        (410, "REQUEST_EXPIRED"),
        docs.RATE_LIMITED,
    ),
)
async def claim(
    body: ClaimIn, principal: CustomerDep, session: DbDep, services: ServicesDep
) -> RequestOut:
    settings, limiter, key = services.settings, services.limiter, str(principal.id)
    # Keyed by the customer, not the session, so logging in again does not reset the count.
    limiter.assert_unlocked("claim", key)
    limiter.check("claim", key, settings.claim_attempts_per_minute)
    code = body.code()
    if code is None:
        raise ApiError(422, ErrorCode.VALIDATION_ERROR, "Invalid request", "no 4-digit code found")
    try:
        view = await services.consent.claim(session, principal.id, code)
    except ApiError as exc:
        if exc.code is ErrorCode.CODE_NOT_FOUND:  # only wrong codes count toward the lock
            limiter.fail(
                "claim", key,
                max_failures=settings.claim_lock_wrong_tries,
                lock_seconds=settings.claim_lock_seconds,
            )  # fmt: skip
        raise
    limiter.succeed("claim", key)
    return _out(view)


@router.get(
    "/{request_id}/readback",
    response_model=ReadbackOut,
    summary="The readback text (and audio if pre-rendered); moves the request to READ_BACK",
    responses=docs.problems(
        docs.UNAUTHENTICATED,
        docs.FORBIDDEN,
        docs.NOT_FOUND,
        (409, "STATE_CONFLICT or INTENT_CHANGED: it changed after you heard it"),
        (410, "REQUEST_EXPIRED"),
        (422, "VALIDATION_ERROR: language must be en or pcm"),
    ),
)
async def readback(
    request_id: uuid.UUID,
    principal: CustomerDep,
    session: DbDep,
    services: ServicesDep,
    lang: Annotated[str, Query(description="en or pcm")] = "pcm",
) -> ReadbackOut:
    view: ReadbackView = await services.consent.get_readback(
        session, principal.id, request_id, lang
    )
    return ReadbackOut(**view.__dict__)


@router.post(
    "/{request_id}/challenge",
    summary="WebAuthn options whose challenge is the request's intent hash",
    responses=docs.problems(
        docs.UNAUTHENTICATED,
        docs.FORBIDDEN,
        docs.NOT_FOUND,
        (409, "STATE_CONFLICT, INTENT_CHANGED or NO_PASSKEY"),
        (410, "REQUEST_EXPIRED"),
        docs.RATE_LIMITED,
    ),
)
async def challenge(
    request_id: uuid.UUID, principal: CustomerDep, session: DbDep, services: ServicesDep
) -> dict[str, Any]:
    services.limiter.check(
        "challenge", str(principal.id), services.settings.challenge_attempts_per_minute
    )
    return await services.consent.issue_challenge(session, principal.id, request_id)


@router.post(
    "/{request_id}/approve",
    response_model=RequestOut,
    summary="Verify the passkey assertion; returns the final or pending state",
    responses=docs.problems(
        (401, "UNAUTHENTICATED, or SIGNATURE_INVALID (the reason is never given)"),
        docs.FORBIDDEN,
        docs.NOT_FOUND,
        (409, "STATE_CONFLICT, INTENT_CHANGED, ALREADY_USED or CHALLENGE_NOT_FOUND"),
        (410, "REQUEST_EXPIRED"),
        (422, "LIMIT_EXCEEDED: over your daily or per-payment limit"),
        docs.RATE_LIMITED,
    ),
)
async def approve(
    request_id: uuid.UUID,
    assertion: AssertionIn,
    principal: CustomerDep,
    session: DbDep,
    services: ServicesDep,
) -> RequestOut:
    services.limiter.check(
        "approve", str(principal.id), services.settings.approve_attempts_per_minute
    )
    payload = assertion.model_dump()
    view = await services.consent.approve(session, principal.id, request_id, payload)
    if services.demo is not None:  # demo only: kept so the console can replay it
        services.demo.remember_assertion(request_id, payload)
    return _out(view)


@router.post(
    "/{request_id}/decline",
    response_model=RequestOut,
    summary="The customer declines; nothing moves",
    responses=docs.problems(
        docs.UNAUTHENTICATED,
        docs.FORBIDDEN,
        docs.NOT_FOUND,
        (409, "STATE_CONFLICT: it must be read back first"),
        (410, "REQUEST_EXPIRED"),
    ),
)
async def decline(
    request_id: uuid.UUID, principal: CustomerDep, session: DbDep, services: ServicesDep
) -> RequestOut:
    return _out(await services.consent.decline(session, principal.id, request_id))


@router.get(
    "/{request_id}",
    response_model=RequestOut,
    summary="Current state, for the agent's page and the customer's app",
    responses=docs.problems(docs.UNAUTHENTICATED, docs.NOT_FOUND),
)
async def get_request(
    request_id: uuid.UUID, principal: UserDep, session: DbDep, services: ServicesDep
) -> RequestOut:
    viewer = Viewer(principal.role, principal.id)
    return _out(await services.consent.get_request(session, viewer, request_id))
