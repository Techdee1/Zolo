import hmac
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from zolo.api.services import Services, build_services
from zolo.core.errors import ApiError, ErrorCode
from zolo.core.security import COOKIE_NAME, Principal


def get_services(request: Request) -> Services:
    services: Services | None = getattr(request.app.state, "services", None)
    if services is None:
        services = request.app.state.services = build_services(request.app)
    return services


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


ServicesDep = Annotated[Services, Depends(get_services)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


def get_principal(request: Request, services: ServicesDep) -> Principal | None:
    return services.codec.loads(request.cookies.get(COOKIE_NAME))


def require_user(principal: Annotated[Principal | None, Depends(get_principal)]) -> Principal:
    if principal is None:
        raise ApiError(401, ErrorCode.UNAUTHENTICATED, "Log in first")
    return principal


def require_customer(principal: Annotated[Principal, Depends(require_user)]) -> Principal:
    if principal.role != "customer":
        raise ApiError(403, ErrorCode.FORBIDDEN, "Only a customer can do this")
    return principal


def require_agent(principal: Annotated[Principal, Depends(require_user)]) -> Principal:
    if principal.role != "agent":
        raise ApiError(403, ErrorCode.FORBIDDEN, "Only an agent can do this")
    return principal


UserDep = Annotated[Principal, Depends(require_user)]
CustomerDep = Annotated[Principal, Depends(require_customer)]
AgentDep = Annotated[Principal, Depends(require_agent)]


def client_ip(request: Request, services: Services) -> str:
    """The caller's address for rate limits. Behind a proxy or tunnel every request comes from
    the proxy, so X-Forwarded-For is trusted only when TRUST_FORWARDED_FOR is set."""
    if services.settings.trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


DEMO_TOKEN_MAX_FAILURES = 10
DEMO_TOKEN_LOCK_SECONDS = 300


def require_demo(
    request: Request,
    services: ServicesDep,
    x_demo_token: Annotated[
        str | None, Header(description="The demo token (DEMO_TOKEN). Demo mode only.")
    ] = None,
) -> None:
    """Guards every /demo endpoint: demo mode must be on AND the right token sent in a header.

    A header only: not a query string (that lands in logs) and not a cookie (a logged-in
    customer or agent is not the demo operator). Wrong tokens are counted and locked out.
    """
    settings = services.settings
    if not settings.demo_mode:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Not found")
    who = client_ip(request, services)
    services.limiter.assert_unlocked("demo-token", who)
    given = (x_demo_token or "").encode()
    if not x_demo_token or not hmac.compare_digest(given, settings.demo_token.encode()):
        services.limiter.fail(
            "demo-token",
            who,
            max_failures=DEMO_TOKEN_MAX_FAILURES,
            lock_seconds=DEMO_TOKEN_LOCK_SECONDS,
        )
        raise ApiError(401, ErrorCode.UNAUTHENTICATED, "A valid demo token is required")
    services.limiter.succeed("demo-token", who)
