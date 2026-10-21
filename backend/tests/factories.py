"""Small helpers that build valid rows, so tests only spell out what they are testing."""

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from zolo.agents.models import Agent
from zolo.bank.models import BankAccount
from zolo.consent.models import PaymentRequest
from zolo.core.models import Customer, SavedRecipient


async def customer(s: AsyncSession, n: int = 1, **kw: Any) -> Customer:
    row = Customer(display_name=f"Test Customer {n}", phone=f"+234800000{n:04d}", **kw)
    s.add(row)
    await s.flush()
    return row


async def account(
    s: AsyncSession, number: str = "0123456789", bank: str = "057", **kw: Any
) -> BankAccount:
    row = BankAccount(account_number=number, bank_code=bank, verified_name="TEST PAYEE", **kw)
    s.add(row)
    await s.flush()
    return row


async def agent_with_account(s: AsyncSession, number: str = "0987654321") -> Agent:
    """An agent and its account reference each other: insert both, check at commit."""
    agent_id, account_id = uuid.uuid4(), uuid.uuid4()
    s.add(
        BankAccount(
            id=account_id,
            agent_id=None,
            account_number=number,
            bank_code="057",
            verified_name="AGENT",
        )
    )
    s.add(
        Agent(
            id=agent_id, account_id=account_id, business_name="Test Agent", phone=f"+23480{number}"
        )
    )
    await s.flush()
    return await s.get(Agent, agent_id)  # type: ignore[return-value]


def request_kwargs(payee_account_id: uuid.UUID, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "initiator": "agent",
        "payee_account_id": payee_account_id,
        "payee_verified_name": "TEST PAYEE",
        "amount_kobo": 1_500_000,
        "claim_code": "1234",
        "nonce": os.urandom(16),
        "idempotency_key": uuid.uuid4(),
        "state": "CREATED",
        "expires_at": datetime.now(UTC) + timedelta(minutes=2),
    }
    return {**base, **kw}


async def payment_request(
    s: AsyncSession, payee_account_id: uuid.UUID, **kw: Any
) -> PaymentRequest:
    row = PaymentRequest(**request_kwargs(payee_account_id, **kw))
    s.add(row)
    await s.flush()
    return row


async def recipient(s: AsyncSession, customer_id: uuid.UUID, **kw: Any) -> SavedRecipient:
    base: dict[str, Any] = {
        "display_name": "Tunde Bakare", "bank_code": "100004",
        "account_number": "8023456789", "account_name": "TUNDE BAKARE",
    }  # fmt: skip
    row = SavedRecipient(customer_id=customer_id, **{**base, **kw})
    s.add(row)
    await s.flush()
    return row
