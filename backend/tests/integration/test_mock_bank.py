import asyncio
import random
import uuid

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zolo.bank.adapter import BankAdapter
from zolo.bank.mock import Latency, MockBankAdapter
from zolo.bank.models import MockAccount, MockTransfer
from zolo.core.config import Settings
from zolo.demo import seed_data as seed
from zolo.demo.seed import reset_demo

SM = async_sessionmaker[AsyncSession]
NAIRA = 100
AMAKA = seed.ACCOUNTS[0]  # the customer, at the home bank (057)
BISI = seed.ACCOUNTS[1]  # an agent, also at 057
TUNDE = seed.ACCOUNTS[4]  # Tunde Bakare at Opay


@pytest.fixture
async def bank(sessionmaker: SM, settings: Settings) -> BankAdapter:
    await reset_demo(sessionmaker, settings)
    return MockBankAdapter(sessionmaker, latency=Latency(0, 0))


async def balance(sm: SM, number: str, bank_code: str) -> int:
    async with sm() as s:
        return (
            await s.execute(
                select(MockAccount.balance_kobo).where(
                    MockAccount.account_number == number, MockAccount.bank_code == bank_code
                )
            )
        ).scalar_one()


async def total(sm: SM) -> int:
    async with sm() as s:
        return (await s.execute(select(func.sum(MockAccount.balance_kobo)))).scalar_one()


async def pay(bank: BankAdapter, amount: int, key: uuid.UUID | None = None, to=BISI):  # type: ignore[no-untyped-def]
    return await bank.transfer(
        idempotency_key=key or uuid.uuid4(), from_account=AMAKA.account_number,
        to_account=to.account_number, to_bank=to.bank_code, amount_kobo=amount, narration="cash out",
    )  # fmt: skip


# --- name enquiry ---


async def test_name_enquiry_returns_the_bank_verified_name(bank: BankAdapter) -> None:
    r = await bank.name_enquiry(BISI.account_number, BISI.bank_code)
    assert r.found and r.account_name == "BISI VENTURES"


async def test_name_enquiry_for_an_unknown_account_or_the_wrong_bank_finds_nothing(
    bank: BankAdapter,
) -> None:
    assert not (await bank.name_enquiry("9999999999", "057")).found
    assert not (
        await bank.name_enquiry(BISI.account_number, "058")
    ).found  # right number, wrong bank
    assert (await bank.name_enquiry("9999999999", "057")).account_name is None


async def test_the_wrong_recipient_account_has_a_different_name(bank: BankAdapter) -> None:
    a = seed.WRONG_RECIPIENT_ACCOUNT
    r = await bank.name_enquiry(a.account_number, a.bank_code)
    assert r.account_name == "OKONKWO PETER" != "BISI VENTURES"


# --- transfers ---


async def test_a_transfer_moves_exactly_the_amount(bank: BankAdapter, sessionmaker: SM) -> None:
    before = await total(sessionmaker)
    r = await pay(bank, 15_000 * NAIRA)
    assert (
        r.status == "SUCCESS" and r.reference and r.reference.startswith("MOCK-") and not r.replayed
    )
    assert (
        await balance(sessionmaker, AMAKA.account_number, "057")
        == AMAKA.balance_kobo - 15_000 * NAIRA
    )
    assert (
        await balance(sessionmaker, BISI.account_number, "057")
        == BISI.balance_kobo + 15_000 * NAIRA
    )
    assert await total(sessionmaker) == before  # money is conserved


async def test_a_transfer_to_another_bank(bank: BankAdapter, sessionmaker: SM) -> None:
    assert (await pay(bank, 5_000 * NAIRA, to=TUNDE)).status == "SUCCESS"
    assert (
        await balance(sessionmaker, TUNDE.account_number, TUNDE.bank_code)
        == TUNDE.balance_kobo + 5_000 * NAIRA
    )


async def test_retrying_with_the_same_key_never_debits_twice(
    bank: BankAdapter, sessionmaker: SM
) -> None:
    key = uuid.uuid4()
    first = await pay(bank, 15_000 * NAIRA, key)
    for _ in range(3):
        again = await pay(bank, 15_000 * NAIRA, key)
        assert again.status == "SUCCESS" and again.reference == first.reference and again.replayed
    assert (
        await balance(sessionmaker, AMAKA.account_number, "057")
        == AMAKA.balance_kobo - 15_000 * NAIRA
    )


async def test_a_reused_key_with_different_details_is_refused_and_moves_nothing(
    bank: BankAdapter, sessionmaker: SM
) -> None:
    key = uuid.uuid4()
    await pay(bank, 1_000 * NAIRA, key)
    r = await pay(bank, 9_000 * NAIRA, key)  # same key, different amount
    assert r.status == "REJECTED" and r.reason == "IDEMPOTENCY_MISMATCH"
    assert (
        await balance(sessionmaker, AMAKA.account_number, "057")
        == AMAKA.balance_kobo - 1_000 * NAIRA
    )
    async with sessionmaker() as s:  # the original record is untouched
        assert (await s.get(MockTransfer, key)).amount_kobo == 1_000 * NAIRA  # type: ignore[union-attr]


async def test_insufficient_funds_rejects_and_the_rejection_is_what_a_retry_gets(
    bank: BankAdapter, sessionmaker: SM
) -> None:
    key = uuid.uuid4()
    r = await pay(bank, AMAKA.balance_kobo + 1, key)
    assert (r.status, r.reason, r.reference) == ("REJECTED", "INSUFFICIENT_FUNDS", None)
    assert await balance(sessionmaker, AMAKA.account_number, "057") == AMAKA.balance_kobo
    async with (
        sessionmaker() as s
    ):  # even after a top-up, the same key returns the stored rejection
        await s.execute(
            update(MockAccount)
            .where(MockAccount.account_number == AMAKA.account_number)
            .values(balance_kobo=10**12)
        )
        await s.commit()
    again = await pay(bank, AMAKA.balance_kobo + 1, key)
    assert again.status == "REJECTED" and again.reason == "INSUFFICIENT_FUNDS" and again.replayed


async def test_spending_the_whole_balance_is_allowed_but_not_one_kobo_more(
    bank: BankAdapter, sessionmaker: SM
) -> None:
    assert (await pay(bank, AMAKA.balance_kobo)).status == "SUCCESS"
    assert await balance(sessionmaker, AMAKA.account_number, "057") == 0
    assert (await pay(bank, 1)).reason == "INSUFFICIENT_FUNDS"


@pytest.mark.parametrize("amount", [0, -1, -5_000])
async def test_non_positive_amounts_are_refused_and_nothing_is_stored(
    bank: BankAdapter, sessionmaker: SM, amount: int
) -> None:
    r = await pay(bank, amount)
    assert (r.status, r.reason) == ("REJECTED", "INVALID_AMOUNT")
    async with sessionmaker() as s:
        assert (await s.execute(select(func.count()).select_from(MockTransfer))).scalar_one() == 0


async def test_unknown_accounts_and_self_transfers_are_rejected(
    bank: BankAdapter, sessionmaker: SM
) -> None:
    ghost = seed.SeedAccount(uuid.uuid4(), "9999999999", "057", "GHOST", 1)
    assert (await pay(bank, 100, to=ghost)).reason == "ACCOUNT_NOT_FOUND"
    r = await bank.transfer(
        idempotency_key=uuid.uuid4(), from_account="9999999999", to_account=BISI.account_number,
        to_bank="057", amount_kobo=100, narration="x",
    )  # fmt: skip
    assert r.reason == "ACCOUNT_NOT_FOUND"
    assert (await pay(bank, 100, to=AMAKA)).reason == "SAME_ACCOUNT"
    assert await total(sessionmaker) == sum(a.balance_kobo for a in seed.ACCOUNTS)  # nothing moved


# --- concurrency ---


async def test_the_same_key_sent_eight_times_at_once_debits_once(
    bank: BankAdapter, sessionmaker: SM
) -> None:
    key = uuid.uuid4()
    results = await asyncio.gather(*[pay(bank, 15_000 * NAIRA, key) for _ in range(8)])
    assert {r.status for r in results} == {"SUCCESS"} and len({r.reference for r in results}) == 1
    assert sum(1 for r in results if not r.replayed) == 1  # exactly one real transfer
    assert (
        await balance(sessionmaker, AMAKA.account_number, "057")
        == AMAKA.balance_kobo - 15_000 * NAIRA
    )


async def test_concurrent_payments_can_never_overdraw(bank: BankAdapter, sessionmaker: SM) -> None:
    async with sessionmaker() as s:
        await s.execute(
            update(MockAccount)
            .where(MockAccount.account_number == AMAKA.account_number)
            .values(balance_kobo=100 * NAIRA)
        )
        await s.commit()
    before = await total(sessionmaker)
    results = await asyncio.gather(*[pay(bank, 30 * NAIRA) for _ in range(5)])
    assert sorted(r.status for r in results) == ["REJECTED"] * 2 + ["SUCCESS"] * 3
    assert {r.reason for r in results if r.status == "REJECTED"} == {"INSUFFICIENT_FUNDS"}
    assert await balance(sessionmaker, AMAKA.account_number, "057") == 10 * NAIRA
    assert await total(sessionmaker) == before


async def test_opposite_transfers_at_once_do_not_deadlock(
    bank: BankAdapter, sessionmaker: SM
) -> None:
    async def back(amount: int) -> object:
        return await bank.transfer(
            idempotency_key=uuid.uuid4(), from_account=BISI.account_number, to_account=AMAKA.account_number,
            to_bank="057", amount_kobo=amount, narration="refund",
        )  # fmt: skip

    jobs = [pay(bank, 10 * NAIRA) if i % 2 else back(10 * NAIRA) for i in range(20)]
    results = await asyncio.wait_for(asyncio.gather(*jobs), timeout=20)
    assert all(r.status == "SUCCESS" for r in results)  # type: ignore[attr-defined]
    assert (
        await balance(sessionmaker, AMAKA.account_number, "057") == AMAKA.balance_kobo
    )  # 10 each way


async def test_a_random_storm_conserves_money_and_never_goes_negative(
    bank: BankAdapter, sessionmaker: SM
) -> None:
    rng = random.Random(7)
    before = await total(sessionmaker)
    targets = [BISI, seed.ACCOUNTS[2], TUNDE, seed.ACCOUNTS[5]]
    jobs = [pay(bank, rng.randint(1, 80_000) * NAIRA, to=rng.choice(targets)) for _ in range(40)]
    await asyncio.gather(*jobs)
    assert await total(sessionmaker) == before
    async with sessionmaker() as s:
        assert (await s.execute(select(func.min(MockAccount.balance_kobo)))).scalar_one() >= 0


# --- the rest of the contract ---


async def test_card_auth_is_declined_because_cards_are_locked_by_default(bank: BankAdapter) -> None:
    r = await bank.card_auth(card_ref="card-1", amount_kobo=100, merchant="POS")
    assert (r.approved, r.reason) == (False, "CARD_LOCKED")


async def test_latency_is_realistic_by_default_and_can_be_switched_off(sessionmaker: SM) -> None:
    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    realistic = MockBankAdapter(sessionmaker, sleep=fake_sleep, rng=random.Random(1))
    for _ in range(25):
        await realistic.name_enquiry("0123456789", "057")
    assert slept and all(0.3 <= s <= 0.8 for s in slept)
    slept.clear()
    await MockBankAdapter(sessionmaker, latency=Latency(0, 0), sleep=fake_sleep).name_enquiry(
        "0123456789", "057"
    )
    assert slept == []
