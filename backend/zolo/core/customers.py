import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zolo.core.models import Customer


async def get_customer(session: AsyncSession, customer_id: uuid.UUID) -> Customer | None:
    return await session.get(Customer, customer_id)


async def customer_by_phone(session: AsyncSession, phone: str) -> Customer | None:
    return (
        await session.execute(select(Customer).where(Customer.phone == phone))
    ).scalar_one_or_none()
