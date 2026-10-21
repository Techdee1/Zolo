from fastapi import APIRouter

from zolo.api import docs
from zolo.api.deps import CustomerDep, DbDep, ServicesDep
from zolo.api.schemas import ActivityItemOut, ActivityOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get(
    "/activity",
    response_model=ActivityOut,
    summary="The last 20 payments, each with a readable line",
    responses=docs.problems(docs.UNAUTHENTICATED, docs.FORBIDDEN),
)
async def activity(principal: CustomerDep, session: DbDep, services: ServicesDep) -> ActivityOut:
    items = await services.consent.activity(session, principal.id, limit=20)
    return ActivityOut(items=[ActivityItemOut(**i.__dict__) for i in items])
