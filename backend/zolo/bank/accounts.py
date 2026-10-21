"""Zolo's own record of bank accounts (bank_accounts), as service functions other modules call
instead of reading the table directly."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zolo.bank.models import BankAccount


async def get_account(session: AsyncSession, account_id: uuid.UUID) -> BankAccount | None:
    return await session.get(BankAccount, account_id)


async def customer_account(session: AsyncSession, customer_id: uuid.UUID) -> BankAccount | None:
    """The customer's account (Phase 1: one per customer)."""
    return (
        await session.execute(
            select(BankAccount).where(BankAccount.customer_id == customer_id).limit(1)
        )
    ).scalar_one_or_none()
