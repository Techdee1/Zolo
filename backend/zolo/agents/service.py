import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zolo.agents.models import Agent


async def get_agent(session: AsyncSession, agent_id: uuid.UUID) -> Agent | None:
    return await session.get(Agent, agent_id)


async def agent_by_phone(session: AsyncSession, phone: str) -> Agent | None:
    return (await session.execute(select(Agent).where(Agent.phone == phone))).scalar_one_or_none()
