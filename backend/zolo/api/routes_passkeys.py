from typing import Any

from fastapi import APIRouter

from zolo.api import docs
from zolo.api.deps import CustomerDep, DbDep, ServicesDep
from zolo.api.schemas import PasskeyOut, RegisterVerifyIn
from zolo.core.customers import get_customer
from zolo.core.errors import ApiError, ErrorCode

router = APIRouter(prefix="/passkeys", tags=["passkeys"])


@router.post(
    "/register/options",
    summary="WebAuthn creation options for navigator.credentials.create()",
    responses=docs.problems(docs.UNAUTHENTICATED, docs.FORBIDDEN),
)
async def register_options(
    principal: CustomerDep, session: DbDep, services: ServicesDep
) -> dict[str, Any]:
    customer = await get_customer(session, principal.id)
    if customer is None:
        raise ApiError(401, ErrorCode.UNAUTHENTICATED, "Log in first")
    return await services.passkeys.registration_options(
        session, customer.id, customer.phone, customer.display_name
    )


@router.post(
    "/register/verify",
    status_code=201,
    response_model=PasskeyOut,
    summary="Verify the browser's answer and store the passkey",
    responses=docs.problems(
        docs.UNAUTHENTICATED,
        docs.FORBIDDEN,
        (400, "PASSKEY_REGISTRATION_FAILED: the browser's answer did not verify"),
        (409, "CHALLENGE_NOT_FOUND: start registration first"),
    ),
)
async def register_verify(
    body: RegisterVerifyIn, principal: CustomerDep, session: DbDep, services: ServicesDep
) -> PasskeyOut:
    result = await services.passkeys.verify_registration(
        session, principal.id, body.credential, body.device_label
    )
    return PasskeyOut(
        id=result.id, device_label=result.device_label, replaced_previous=result.replaced_previous
    )
