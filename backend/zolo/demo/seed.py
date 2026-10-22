"""Seed and reset the demo. Same named people, accounts and balances every time.

`reset_demo` is what `POST /demo/reset` and `python -m zolo.seed` both run:
- clears requests, challenges, the audit trail, mock transfers and card windows;
- re-writes customers, agents, accounts, balances, recipients and limits to the seed values;
- KEEPS passkey_credentials, so a passkey registered on the demo phone survives every reset
  (the seed uses fixed ids, so the credentials still point at the same customer).
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zolo.agents.models import Agent
from zolo.bank.models import BankAccount, MockAccount
from zolo.core.base import Base
from zolo.core.config import NAIRA, Settings
from zolo.core.models import Customer, SavedRecipient
from zolo.demo import seed_data as data
from zolo.risk.models import RiskLimit

# Order matters only for readability: TRUNCATE takes them together.
_STATE_TABLES = ", ".join(
    (
        "phone_calls",
        "phone_enrolments",
        "webauthn_challenges",
        "payment_requests",
        "audit_events",
        "mock_transfers",
        "card_guard_windows",
    )  # fmt: skip
)


@dataclass(frozen=True)
class SeedSummary:
    customers: int
    agents: int
    accounts: int
    recipients: int


async def reset_demo(
    sessionmaker: async_sessionmaker[AsyncSession], settings: Settings
) -> SeedSummary:
    async with sessionmaker() as s, s.begin():
        await s.execute(text(f"TRUNCATE {_STATE_TABLES} RESTART IDENTITY"))
        await _upsert_reference_data(s, settings)
    return SeedSummary(1, 2, len(data.ACCOUNTS), len(data.RECIPIENTS))


async def _upsert(
    s: AsyncSession, model: type[Base], rows: list[dict[str, object]], key: list[str]
) -> None:
    stmt = pg_insert(model).values(rows)
    update = {
        c.name: stmt.excluded[c.name]
        for c in model.__table__.columns
        if c.name not in key and c.name != "created_at"
    }
    await s.execute(stmt.on_conflict_do_update(index_elements=key, set_=update))


async def _upsert_reference_data(s: AsyncSession, settings: Settings) -> None:
    c = data.AMAKA
    await _upsert(
        s,
        Customer,
        [{"id": c.id, "display_name": c.display_name, "phone": c.phone, "language": c.language}],
        ["id"],
    )
    # An agent and its account reference each other. agents.account_id is deferred, so the
    # agents go first and the check happens at commit.
    agents = [data.BISI, data.MAMA_CHI]
    await _upsert(
        s,
        Agent,
        [
            {
                "id": a.id,
                "account_id": a.account_id,
                "business_name": a.business_name,
                "phone": a.phone,
            }
            for a in agents
        ],
        ["id"],
    )
    await _upsert(
        s,
        BankAccount,
        [
            {
                "id": a.id,
                "customer_id": a.customer_id,
                "agent_id": a.agent_id,
                "account_number": a.account_number,
                "bank_code": a.bank_code,
                "verified_name": a.verified_name,
            }
            for a in data.ACCOUNTS
        ],
        ["id"],
    )
    await _upsert(
        s,
        MockAccount,
        [
            {
                "account_number": a.account_number,
                "bank_code": a.bank_code,
                "account_name": a.verified_name,
                "balance_kobo": a.balance_kobo,
            }
            for a in data.ACCOUNTS
        ],
        ["account_number", "bank_code"],
    )
    await _upsert(
        s,
        SavedRecipient,
        [
            {
                "id": r.id,
                "customer_id": r.customer_id,
                "display_name": r.display_name,
                "bank_code": r.bank_code,
                "account_number": r.account_number,
                "account_name": r.account_name,
            }
            for r in data.RECIPIENTS
        ],
        ["id"],
    )
    await _upsert(
        s,
        RiskLimit,
        [
            {
                "customer_id": c.id,
                "per_payment_kobo": settings.per_payment_cap_kobo,
                "daily_kobo": settings.daily_cap_kobo,
                "new_payee_kobo": 20_000 * NAIRA,
                "call_channel_kobo": 20_000 * NAIRA,
            }
        ],
        ["customer_id"],
    )
