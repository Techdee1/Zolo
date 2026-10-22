from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import text

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str


class Readiness(BaseModel):
    status: str
    database: bool
    seed: bool


@router.get("/healthz", response_model=Health)
async def healthz() -> Health:
    """The process is up. Does not touch the database."""
    return Health(status="ok")


@router.get("/readyz", response_model=Readiness, responses={503: {"model": Readiness}})
async def readyz(request: Request, response: Response) -> Readiness:
    """The database is reachable and the demo seed is present. Check before going on stage."""
    database = seed = False
    try:
        async with request.app.state.sessionmaker() as session:
            await session.execute(text("SELECT 1"))
            database = True
            seed = bool((await session.execute(text("SELECT count(*) FROM agents"))).scalar_one())
    except Exception:  # noqa: BLE001 - any failure means "not ready"; details stay out of the reply
        pass
    ready = database and seed
    if not ready:
        response.status_code = 503
    return Readiness(status="ready" if ready else "not_ready", database=database, seed=seed)
