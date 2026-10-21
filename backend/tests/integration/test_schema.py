"""The database refuses what code could get wrong. Each test goes straight to Postgres."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests import factories as f
from zolo.agents.models import Agent
from zolo.audit.models import AuditEvent
from zolo.bank.models import BankAccount
from zolo.core.models import Customer, SavedRecipient
from zolo.models import Base
from zolo.passkeys.models import PasskeyCredential, WebAuthnChallenge
from zolo.risk.models import CardGuardWindow, RiskLimit

SM = async_sessionmaker[AsyncSession]


async def test_the_models_match_the_migration_exactly(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        diff = await conn.run_sync(
            lambda c: compare_metadata(MigrationContext.configure(c), Base.metadata)
        )
    assert diff == []  # no table, column, index or constraint drift


async def test_every_prd_table_exists(sessionmaker: SM) -> None:
    async with sessionmaker() as s:
        names = set(
            (
                await s.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
            ).scalars()
        )
    assert names >= {
        "customers", "bank_accounts", "agents", "payment_requests", "passkey_credentials",
        "webauthn_challenges", "risk_limits", "card_guard_windows", "audit_events", "saved_recipients",
    }  # fmt: skip


async def _rejects(sessionmaker: SM, build: Any, what: str) -> None:
    """The statement built by `build(session)` must fail with an integrity error."""
    async with sessionmaker() as s:
        with pytest.raises((IntegrityError, DBAPIError)) as exc:
            await build(s)
            await s.commit()
        assert what in str(exc.value), str(exc.value)[:300]


# --- saved_recipients ---


async def test_saved_recipients_holds_two_tundes_for_one_customer(sessionmaker: SM) -> None:
    async with sessionmaker() as s:
        c = await f.customer(s)
        await f.recipient(
            s, c.id, display_name="Tunde Bakare", bank_code="100004", account_number="8023456789"
        )
        await f.recipient(
            s, c.id, display_name="Tunde Adeyemi", bank_code="058", account_number="0456789012"
        )
        await s.commit()
        rows = (
            (await s.execute(select(SavedRecipient).where(SavedRecipient.customer_id == c.id)))
            .scalars()
            .all()
        )
    assert sorted(r.display_name for r in rows) == ["Tunde Adeyemi", "Tunde Bakare"]
    assert all(r.created_at is not None and r.id is not None for r in rows)


async def test_a_recipient_cannot_be_saved_twice_per_customer(sessionmaker: SM) -> None:
    async def build(s: AsyncSession) -> None:
        c = await f.customer(s)
        await f.recipient(s, c.id)
        await f.recipient(s, c.id, display_name="Again")

    await _rejects(sessionmaker, build, "uq_saved_recipients_customer_id")


async def test_two_customers_can_save_the_same_account(sessionmaker: SM) -> None:
    async with sessionmaker() as s:
        a, b = await f.customer(s, 1), await f.customer(s, 2)
        await f.recipient(s, a.id)
        await f.recipient(s, b.id)
        await s.commit()


async def test_saved_recipient_needs_a_real_customer_and_a_10_digit_account(
    sessionmaker: SM,
) -> None:
    async def orphan(s: AsyncSession) -> None:
        await f.recipient(s, uuid.uuid4())

    async def short(s: AsyncSession) -> None:
        c = await f.customer(s)
        await f.recipient(s, c.id, account_number="12345")

    await _rejects(sessionmaker, orphan, "fk_saved_recipients_customer_id_customers")
    await _rejects(sessionmaker, short, "account_number_10_digits")


async def test_saved_recipients_are_indexed_by_customer_and_deleted_with_them(
    sessionmaker: SM,
) -> None:
    async with sessionmaker() as s:
        idx = set(
            (
                await s.execute(
                    text("SELECT indexname FROM pg_indexes WHERE tablename='saved_recipients'")
                )
            ).scalars()
        )
        assert "ix_saved_recipients_customer_id" in idx
        c = await f.customer(s)
        await f.recipient(s, c.id)
        await s.commit()
        await s.execute(text("DELETE FROM customers WHERE id = :i"), {"i": c.id})
        await s.commit()
        assert (await s.execute(select(SavedRecipient))).first() is None


# --- payment_requests: money and state ---


async def _payee(s: AsyncSession) -> uuid.UUID:
    return (await f.account(s)).id


@pytest.mark.parametrize(
    "overrides,constraint",
    [
        ({"amount_kobo": 0}, "ck_payment_requests_amount_positive"),
        ({"amount_kobo": -1}, "ck_payment_requests_amount_positive"),
        ({"currency": "USD"}, "ck_payment_requests_currency_ngn"),
        ({"claim_code": "12a4"}, "ck_payment_requests_claim_code_4_digits"),
        ({"claim_code": "123"}, "ck_payment_requests_claim_code_4_digits"),
        ({"nonce": b"short"}, "ck_payment_requests_nonce_16_bytes"),
        ({"intent_hash": b"x" * 31}, "ck_payment_requests_intent_hash_sha256"),
        ({"state": "PAID"}, "ck_payment_requests_state_known"),
        ({"initiator": "stranger"}, "ck_payment_requests_initiator_known"),
        ({"channel": "sms"}, "ck_payment_requests_channel_known"),
        ({"state": "READ_BACK", "intent_hash": b"h" * 32}, "ck_payment_requests_heard_has_customer"),
        ({"state": "APPROVED", "intent_hash": b"h" * 32, "approved_at": datetime.now(UTC)}, "ck_payment_requests_heard_has_customer"),
        ({"state": "SETTLED", "bank_reference": "ref", "settled_at": datetime.now(UTC)}, "ck_payment_requests_heard_has_customer"),
        ({"state": "FAILED"}, "ck_payment_requests_failed_has_reason"),
    ],
)  # fmt: skip
async def test_payment_request_constraints(
    sessionmaker: SM, overrides: dict[str, Any], constraint: str
) -> None:
    async def build(s: AsyncSession) -> None:
        await f.payment_request(s, await _payee(s), **overrides)

    await _rejects(sessionmaker, build, constraint)


@pytest.mark.parametrize(
    "overrides,constraint",
    [
        ({"state": "READ_BACK"}, "ck_payment_requests_heard_has_hash"),
        ({"state": "APPROVED", "intent_hash": b"h" * 32}, "ck_payment_requests_signed_has_time"),
        ({"state": "SETTLED", "intent_hash": b"h" * 32, "approved_at": datetime.now(UTC)}, "ck_payment_requests_settled_has_reference"),
    ],
)  # fmt: skip
async def test_a_claimed_request_must_carry_what_it_claims(
    sessionmaker: SM, overrides: dict[str, Any], constraint: str
) -> None:
    async def build(s: AsyncSession) -> None:
        c = await f.customer(s)
        await f.payment_request(s, await _payee(s), customer_id=c.id, **overrides)

    await _rejects(sessionmaker, build, constraint)


async def test_a_complete_settled_request_is_accepted(sessionmaker: SM) -> None:
    async with sessionmaker() as s:
        c = await f.customer(s)
        now = datetime.now(UTC)
        row = await f.payment_request(
            s, await _payee(s), customer_id=c.id, state="SETTLED", intent_hash=b"h" * 32,
            approved_at=now, settled_at=now, bank_reference="MOCK-1", amount_kobo=10**15,
        )  # fmt: skip
        await s.commit()
        assert row.amount_kobo == 10**15  # BIGINT holds far more than a 32-bit kobo amount


async def test_only_one_live_request_may_hold_a_claim_code(sessionmaker: SM) -> None:
    async with sessionmaker() as s:
        payee = await _payee(s)
        await f.payment_request(s, payee, claim_code="4321", state="CREATED")
        await s.commit()
    async with sessionmaker() as s:
        with pytest.raises(IntegrityError) as exc:
            await f.payment_request(s, payee, claim_code="4321", state="CREATED")
        assert "ux_payment_requests_live_claim_code" in str(exc.value)


async def test_a_claim_code_is_free_again_once_the_request_is_no_longer_live(
    sessionmaker: SM,
) -> None:
    async with sessionmaker() as s:
        payee = await _payee(s)
        await f.payment_request(s, payee, claim_code="4321", state="EXPIRED")
        await f.payment_request(s, payee, claim_code="4321", state="DECLINED")
        await f.payment_request(s, payee, claim_code="4321", state="CREATED")
        await s.commit()


async def test_nonce_and_idempotency_key_are_unique(sessionmaker: SM) -> None:
    async def same_nonce(s: AsyncSession) -> None:
        p = await _payee(s)
        await f.payment_request(s, p, claim_code="1111", nonce=b"n" * 16)
        await f.payment_request(s, p, claim_code="2222", nonce=b"n" * 16)

    async def same_key(s: AsyncSession) -> None:
        p, key = await _payee(s), uuid.uuid4()
        await f.payment_request(s, p, claim_code="1111", idempotency_key=key)
        await f.payment_request(s, p, claim_code="2222", idempotency_key=key)

    await _rejects(sessionmaker, same_nonce, "uq_payment_requests_nonce")
    await _rejects(sessionmaker, same_key, "uq_payment_requests_idempotency_key")


async def test_history_index_exists(sessionmaker: SM) -> None:
    async with sessionmaker() as s:
        defs = (
            (
                await s.execute(
                    text("SELECT indexdef FROM pg_indexes WHERE tablename='payment_requests'")
                )
            )
            .scalars()
            .all()
        )
    assert any("customer_id, created_at DESC" in d for d in defs)


# --- accounts, agents ---


async def test_an_account_has_at_most_one_owner_and_a_real_number(sessionmaker: SM) -> None:
    async def two_owners(s: AsyncSession) -> None:
        c = await f.customer(s)
        a = await f.agent_with_account(s)
        await f.account(s, "1111111111", customer_id=c.id, agent_id=a.id)

    async def bad_number(s: AsyncSession) -> None:
        await f.account(s, "12-345")

    async def duplicate(s: AsyncSession) -> None:
        await f.account(s, "2222222222", "057")
        await f.account(s, "2222222222", "057")

    await _rejects(sessionmaker, two_owners, "ck_bank_accounts_one_owner")
    await _rejects(sessionmaker, bad_number, "ck_bank_accounts_account_number_10_digits")
    await _rejects(sessionmaker, duplicate, "uq_bank_accounts_account_number")


async def test_the_same_number_at_two_banks_is_two_accounts(sessionmaker: SM) -> None:
    async with sessionmaker() as s:
        await f.account(s, "3333333333", "057")
        await f.account(s, "3333333333", "058")
        await s.commit()


async def test_an_agent_and_its_account_can_reference_each_other(sessionmaker: SM) -> None:
    async with sessionmaker() as s:
        a = await f.agent_with_account(s)
        acc = await s.get(BankAccount, a.account_id)
        assert acc is not None
        acc.agent_id = a.id  # both directions: checked at commit
        await s.commit()
        assert (await s.get(BankAccount, a.account_id)).agent_id == a.id  # type: ignore[union-attr]


async def test_an_agent_must_have_an_account_by_commit_time(sessionmaker: SM) -> None:
    async def build(s: AsyncSession) -> None:
        s.add(Agent(account_id=uuid.uuid4(), business_name="Ghost", phone="+2348099999999"))
        await s.flush()

    await _rejects(sessionmaker, build, "fk_agents_account_id_bank_accounts")


# --- passkeys, risk, card guard ---


async def test_passkey_and_challenge_constraints(sessionmaker: SM) -> None:
    async def negative_count(s: AsyncSession) -> None:
        c = await f.customer(s)
        s.add(
            PasskeyCredential(customer_id=c.id, credential_id=b"c", public_key=b"k", sign_count=-1)
        )
        await s.flush()

    async def bad_purpose(s: AsyncSession) -> None:
        c = await f.customer(s)
        s.add(
            WebAuthnChallenge(
                customer_id=c.id, challenge=b"x", purpose="login", expires_at=datetime.now(UTC)
            )
        )
        await s.flush()

    async def duplicate_credential(s: AsyncSession) -> None:
        a, b = await f.customer(s, 1), await f.customer(s, 2)
        s.add(PasskeyCredential(customer_id=a.id, credential_id=b"same", public_key=b"k"))
        s.add(PasskeyCredential(customer_id=b.id, credential_id=b"same", public_key=b"k"))
        await s.flush()

    await _rejects(sessionmaker, negative_count, "sign_count_non_negative")
    await _rejects(sessionmaker, bad_purpose, "purpose_known")
    await _rejects(sessionmaker, duplicate_credential, "uq_passkey_credentials_credential_id")


async def test_risk_limits_must_be_positive_and_card_windows_must_close_after_opening(
    sessionmaker: SM,
) -> None:
    async def zero_cap(s: AsyncSession) -> None:
        c = await f.customer(s)
        s.add(
            RiskLimit(
                customer_id=c.id,
                per_payment_kobo=0,
                daily_kobo=1,
                new_payee_kobo=1,
                call_channel_kobo=1,
            )
        )
        await s.flush()

    async def backwards_window(s: AsyncSession) -> None:
        c = await f.customer(s)
        now = datetime.now(UTC)
        s.add(
            CardGuardWindow(
                customer_id=c.id,
                card_ref="card",
                max_amount_kobo=1,
                opens_at=now,
                closes_at=now - timedelta(minutes=1),
            )
        )
        await s.flush()

    await _rejects(sessionmaker, zero_cap, "ck_risk_limits_per_payment_positive")
    await _rejects(sessionmaker, backwards_window, "closes_after_opens")


async def test_customer_language_must_be_known_and_phone_unique(sessionmaker: SM) -> None:
    async def bad_language(s: AsyncSession) -> None:
        s.add(Customer(display_name="X", phone="+2348000000001", language="fr"))
        await s.flush()

    async def same_phone(s: AsyncSession) -> None:
        s.add(Customer(display_name="X", phone="+2348000000002"))
        s.add(Customer(display_name="Y", phone="+2348000000002"))
        await s.flush()

    await _rejects(sessionmaker, bad_language, "language_known")
    await _rejects(sessionmaker, same_phone, "uq_customers_phone")


# --- audit trail ---


async def test_audit_events_can_be_added_but_never_changed_or_deleted(sessionmaker: SM) -> None:
    async with sessionmaker() as s:
        s.add(AuditEvent(event="request.created", actor="agent", details={"state": "CREATED"}))
        await s.commit()
        row = (await s.execute(select(AuditEvent))).scalar_one()
        assert row.id == 1 and row.at is not None and row.details == {"state": "CREATED"}
    for sql in ("UPDATE audit_events SET event = 'x'", "DELETE FROM audit_events"):
        async with sessionmaker() as s:
            with pytest.raises(DBAPIError) as exc:
                await s.execute(text(sql))
            assert "append-only" in str(exc.value)


async def test_the_demo_reset_can_still_truncate_the_audit_trail(sessionmaker: SM) -> None:
    async with sessionmaker() as s:
        s.add(AuditEvent(event="e", actor="a"))
        await s.commit()
        await s.execute(text("TRUNCATE audit_events RESTART IDENTITY"))
        await s.commit()
        assert (await s.execute(select(AuditEvent))).first() is None
