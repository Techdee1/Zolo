from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
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
