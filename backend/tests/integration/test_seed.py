import subprocess
import sys

from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests import factories as f
from tests.conftest import TEST_DB_URL
from zolo.audit.models import AuditEvent
from zolo.bank.mock import Latency, MockBankAdapter
from zolo.bank.models import BankAccount, MockAccount
from zolo.core.config import Settings
from zolo.core.models import Customer, SavedRecipient
from zolo.demo import seed_data as seed
from zolo.demo.seed import reset_demo
from zolo.passkeys.models import PasskeyCredential
from zolo.risk.models import RiskLimit

SM = async_sessionmaker[AsyncSession]


async def snapshot(sm: SM) -> dict[str, list[tuple[object, ...]]]:
    tables = [
        "customers",
        "agents",
        "bank_accounts",
        "mock_accounts",
        "saved_recipients",
        "risk_limits",
    ]
    async with sm() as s:
        return {
            t: sorted((await s.execute(text(f"SELECT * FROM {t}"))).all(), key=str)  # noqa: S608
            for t in tables
        }  # type: ignore[misc]


async def test_seed_creates_the_named_demo_world(sessionmaker: SM, settings: Settings) -> None:
    summary = await reset_demo(sessionmaker, settings)
    assert (summary.customers, summary.agents, summary.accounts, summary.recipients) == (1, 2, 7, 4)
    async with sessionmaker() as s:
        assert (await s.get(Customer, seed.AMAKA.id)).display_name == "Amaka Obi"  # type: ignore[union-attr]
        names = (
            (
                await s.execute(
                    select(SavedRecipient.display_name).order_by(SavedRecipient.display_name)
                )
            )
            .scalars()
            .all()
        )
        assert names == ["Mama Chi Stores", "My sister", "Tunde Adeyemi", "Tunde Bakare"]
        banks = {
            r.bank_code
            for r in (
                await s.execute(
                    select(SavedRecipient).where(SavedRecipient.display_name.like("Tunde%"))
                )
            ).scalars()
        }
        assert banks == {"100004", "058"}  # two Tundes, two banks
        limits = await s.get(RiskLimit, seed.AMAKA.id)
        assert (limits.per_payment_kobo, limits.daily_kobo) == (
            settings.per_payment_cap_kobo,
            settings.daily_cap_kobo,
        )  # type: ignore[union-attr]


async def test_seeding_twice_gives_exactly_the_same_world(
    sessionmaker: SM, settings: Settings
) -> None:
    await reset_demo(sessionmaker, settings)
    first = await snapshot(sessionmaker)
    await reset_demo(sessionmaker, settings)
    assert await snapshot(sessionmaker) == first


async def test_every_zolo_account_agrees_with_the_banks_own_records(
    sessionmaker: SM, settings: Settings
) -> None:
    await reset_demo(sessionmaker, settings)
    bank = MockBankAdapter(sessionmaker, latency=Latency(0, 0))
    async with sessionmaker() as s:
        accounts = (await s.execute(select(BankAccount))).scalars().all()
    assert len(accounts) == 7
    for a in accounts:
        r = await bank.name_enquiry(a.account_number, a.bank_code)
        assert r.account_name == a.verified_name, a.account_number


async def test_reset_puts_back_balances_and_clears_requests_and_the_audit_trail(
    sessionmaker: SM, settings: Settings
) -> None:
    await reset_demo(sessionmaker, settings)
    async with sessionmaker() as s:
        await s.execute(text("UPDATE mock_accounts SET balance_kobo = 1"))
        payee = (await s.execute(select(BankAccount.id).limit(1))).scalar_one()
        await f.payment_request(s, payee)
        s.add(AuditEvent(event="x", actor="y"))
        await s.commit()
    await reset_demo(sessionmaker, settings)
    async with sessionmaker() as s:
        assert (await s.execute(select(func.sum(MockAccount.balance_kobo)))).scalar_one() == sum(
            a.balance_kobo for a in seed.ACCOUNTS
        )
        for table in ("payment_requests", "audit_events", "mock_transfers", "webauthn_challenges"):
            assert (await s.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0  # noqa: S608


async def test_reset_keeps_the_passkey_registered_on_the_demo_phone(
    sessionmaker: SM, settings: Settings
) -> None:
    await reset_demo(sessionmaker, settings)
    async with sessionmaker() as s:
        s.add(
            PasskeyCredential(
                customer_id=seed.AMAKA.id,
                credential_id=b"demo-phone",
                public_key=b"pk",
                sign_count=3,
            )
        )
        await s.commit()
    await reset_demo(sessionmaker, settings)
    async with sessionmaker() as s:
        cred = (await s.execute(select(PasskeyCredential))).scalar_one()
        assert (
            cred.credential_id == b"demo-phone"
            and cred.sign_count == 3
            and cred.customer_id == seed.AMAKA.id
        )


async def test_readyz_turns_green_after_seeding(
    client: AsyncClient, sessionmaker: SM, settings: Settings
) -> None:
    assert (await client.get("/readyz")).status_code == 503
    await reset_demo(sessionmaker, settings)
    r = await client.get("/readyz")
    assert r.status_code == 200 and r.json()["seed"] is True


async def test_the_seed_command_runs_and_prints_counts_only(
    sessionmaker: SM, settings: Settings
) -> None:
    out = subprocess.run(
        [sys.executable, "-m", "zolo.seed"], capture_output=True, text=True, timeout=60,
        env={"DATABASE_URL": TEST_DB_URL, "SESSION_SECRET": "x" * 40, "PATH": "/usr/bin:/bin"},
    )  # fmt: skip
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip() == "seeded 1 customer, 2 agents, 7 accounts, 4 saved recipients"
    for private in ("Amaka", "BISI", "0123456789", "+234"):
        assert private not in out.stdout
