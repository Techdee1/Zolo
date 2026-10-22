"""Mock login: a seeded customer or agent signs in with a phone number and the fixed OTP.

This router is mounted ONLY when DEMO_MODE=true (see create_app), and the handler checks again.
In any other environment the route does not exist, so there is nothing to switch on by accident.
"""

import hmac

from fastapi import APIRouter, Request, Response

from zolo.agents.service import agent_by_phone
from zolo.api import docs
from zolo.api.deps import DbDep, ServicesDep, client_ip
from zolo.api.schemas import MockLoginIn, SessionOut
from zolo.core.customers import customer_by_phone
from zolo.core.errors import ApiError, ErrorCode
from zolo.core.security import COOKIE_NAME, Role

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/mock-login",
    response_model=SessionOut,
    summary="Mock login (demo only)",
    responses=docs.problems(
        (401, "UNAUTHENTICATED: unknown phone or wrong code"), docs.RATE_LIMITED
    ),
)
async def mock_login(
    body: MockLoginIn, request: Request, response: Response, session: DbDep, services: ServicesDep
) -> SessionOut:
    settings = services.settings
    if not settings.demo_mode:  # defence in depth: the route is not mounted without it
        raise ApiError(404, ErrorCode.NOT_FOUND, "Not found")
    limit = settings.login_attempts_per_minute
    services.limiter.check("login-ip", client_ip(request, services), limit)
    services.limiter.check("login-phone", body.phone, limit)

    # One answer for an unknown phone and a wrong code, so the form cannot be used to find numbers.
    code_ok = hmac.compare_digest(body.otp.encode(), settings.mock_otp.encode())
    customer = await customer_by_phone(session, body.phone)
    agent = None if customer else await agent_by_phone(session, body.phone)
    if not code_ok or (customer is None and agent is None):
        raise ApiError(401, ErrorCode.UNAUTHENTICATED, "Invalid phone number or code")

    role: Role
    if customer is not None:
        role, subject, name = "customer", customer.id, customer.display_name
    else:
        assert agent is not None
        role, subject, name = "agent", agent.id, agent.business_name
    token = services.codec.dumps(role, subject)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return SessionOut(role=role, id=subject, display_name=name)
