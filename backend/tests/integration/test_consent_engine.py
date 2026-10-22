import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zolo.ai.types import Lang
from zolo.audit.models import AuditEvent
from zolo.bank.adapter import TransferResult
from zolo.bank.mock import Latency, MockBankAdapter
from zolo.bank.models import MockAccount, MockTransfer
from zolo.consent.intent import Intent, intent_hash
from zolo.consent.models import PaymentRequest
from zolo.consent.service import ConsentService, Viewer
from zolo.core.config import Settings
from zolo.core.errors import ApiError
from zolo.core.models import Customer
from zolo.demo import seed_data as seed
from zolo.demo.seed import reset_demo

SM = async_sessionmaker[AsyncSession]
NAIRA = 100
AMAKA, BISI, MAMA = seed.AMAKA.id, seed.BISI.id, seed.MAMA_CHI.id
START = datetime(2026, 10, 21, 10, 0, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class StubAudio:
    def audio_url(self, text: str, lang: Lang) -> str | None:
        return f"/voice/audio/{len(text)}-{lang}.mp3"

    async def wait_ready(self, text: str, lang: Lang) -> None:
        return None


class Flaky:
    """A bank that loses the first `fail_times` calls (timeout), then behaves."""

    def __init__(self, inner: MockBankAdapter, fail_times: int = 0) -> None:
        self.inner, self.fail_times, self.calls = inner, fail_times, 0

    async def name_enquiry(self, account: str, bank_code: str):  # type: ignore[no-untyped-def]
        return await self.inner.name_enquiry(account, bank_code)

    async def transfer(self, **kw):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TimeoutError("network dropped")
        return await self.inner.transfer(**kw)

    async def card_auth(self, **kw):  # type: ignore[no-untyped-def]
        return await self.inner.card_auth(**kw)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
async def world(sessionmaker: SM, settings: Settings, clock: Clock):  # type: ignore[no-untyped-def]
    await reset_demo(sessionmaker, settings)
    bank = Flaky(MockBankAdapter(sessionmaker, latency=Latency(0, 0)))
    svc = ConsentService(settings, bank, audio=StubAudio(), clock=clock)  # type: ignore[arg-type]
    return svc, bank, sessionmaker


async def create(world, amount: int = 15_000 * NAIRA, agent: uuid.UUID = BISI, key=None):  # type: ignore[no-untyped-def]
    svc, _, sm = world
    async with sm() as s:
        return await svc.create_agent_request(s, agent, amount, key)


async def claim(world, code: str, customer: uuid.UUID = AMAKA):  # type: ignore[no-untyped-def]
    svc, _, sm = world
    async with sm() as s:
        return await svc.claim(s, customer, code)


async def readback(world, request_id: uuid.UUID, customer: uuid.UUID = AMAKA, lang: str = "pcm"):  # type: ignore[no-untyped-def]
    svc, _, sm = world
    async with sm() as s:
        return await svc.get_readback(s, customer, request_id, lang)


async def row(sm: SM, request_id: uuid.UUID) -> PaymentRequest:
    async with sm() as s:
        return (
            await s.execute(select(PaymentRequest).where(PaymentRequest.id == request_id))
        ).scalar_one()


async def to_read_back(world, amount: int = 15_000 * NAIRA):  # type: ignore[no-untyped-def]
    made = await create(world, amount)
    await claim(world, made.claim_code)  # type: ignore[arg-type]
    await readback(world, made.id)
    return made


async def force_approved(sm: SM, request_id: uuid.UUID, when: datetime = START) -> None:
    async with sm() as s:
        await s.execute(
            update(PaymentRequest).where(PaymentRequest.id == request_id)
            .values(state="APPROVED", approved_at=when)
        )  # fmt: skip
        await s.commit()


async def code_of(exc: pytest.ExceptionInfo[ApiError]) -> tuple[int, str]:
    return exc.value.status, exc.value.code.value


# ======================================================================= create


async def test_an_agent_creates_a_request_with_a_code_a_qr_and_a_two_minute_life(
    world, clock
) -> None:  # type: ignore[no-untyped-def]
    made = await create(world)
    assert re.fullmatch(r"\d{4}", made.claim_code or "")
    assert made.qr_payload == f"http://localhost:3000/claim?code={made.claim_code}"
    assert made.expires_at == START + timedelta(seconds=120) and made.expires_at.microsecond == 0
    assert (made.payee_name, made.amount_kobo, made.state) == (
        "BISI VENTURES",
        1_500_000,
        "CREATED",
    )
    r = await row(world[2], made.id)
    assert (
        r.customer_id is None
        and r.initiator == "agent"
        and len(r.nonce) == 16
        and r.intent_hash is None
    )


async def test_the_payee_name_comes_from_the_bank_not_from_zolos_copy(world) -> None:  # type: ignore[no-untyped-def]
    async with world[2]() as s:
        await s.execute(
            update(MockAccount)
            .where(MockAccount.account_number == "0123456789")
            .values(account_name="BISI VENTURES LTD")
        )
        await s.commit()
    assert (await create(world)).payee_name == "BISI VENTURES LTD"


@pytest.mark.parametrize("amount,status,code", [
    (0, 422, "VALIDATION_ERROR"), (-100, 422, "VALIDATION_ERROR"),
    (1_500_050, 422, "VALIDATION_ERROR"),  # kobo cannot be read back aloud
    (100_000 * NAIRA + NAIRA, 422, "LIMIT_EXCEEDED"),
])  # fmt: skip
async def test_bad_amounts_are_refused_before_anything_is_stored(
    world, amount, status, code
) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ApiError) as exc:
        await create(world, amount)
    assert (exc.value.status, exc.value.code.value) == (status, code)
    async with world[2]() as s:
        assert (await s.execute(select(func.count()).select_from(PaymentRequest))).scalar_one() == 0


async def test_exactly_the_cap_is_allowed(world) -> None:  # type: ignore[no-untyped-def]
    assert (await create(world, 100_000 * NAIRA)).amount_kobo == 100_000 * NAIRA * 1


async def test_only_an_agent_can_create_and_the_payee_must_exist_at_the_bank(world) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ApiError) as exc:
        await create(world, agent=AMAKA)  # a customer id is not an agent
    assert await code_of(exc) == (403, "FORBIDDEN")
    async with world[2]() as s:
        await s.execute(text("DELETE FROM mock_accounts WHERE account_number = '0123456789'"))
        await s.commit()
    with pytest.raises(ApiError) as exc:
        await create(world)
    assert await code_of(exc) == (422, "NAME_ENQUIRY_FAILED")


async def test_a_repeated_idempotency_key_returns_the_same_request(world) -> None:  # type: ignore[no-untyped-def]
    key = uuid.uuid4()
    a, b = await create(world, key=key), await create(world, key=key)
    assert (a.id, a.claim_code) == (b.id, b.claim_code)
    async with world[2]() as s:
        assert (await s.execute(select(func.count()).select_from(PaymentRequest))).scalar_one() == 1
    with pytest.raises(ApiError) as exc:  # same key, different request
        await create(world, amount=9_000 * NAIRA, key=key)
    assert await code_of(exc) == (409, "STATE_CONFLICT")


async def test_five_simultaneous_creates_with_one_key_make_one_request(world) -> None:  # type: ignore[no-untyped-def]
    key = uuid.uuid4()
    made = await asyncio.gather(*[create(world, key=key) for _ in range(5)])
    assert len({m.id for m in made}) == 1
    async with world[2]() as s:
        assert (await s.execute(select(func.count()).select_from(PaymentRequest))).scalar_one() == 1


async def test_sixty_simultaneous_requests_all_get_different_live_codes(world) -> None:  # type: ignore[no-untyped-def]
    made = await asyncio.gather(*[create(world) for _ in range(60)])
    assert len({m.claim_code for m in made}) == 60


# ======================================================================= claim


async def test_claiming_binds_the_request_to_the_customer(world) -> None:  # type: ignore[no-untyped-def]
    made = await create(world)
    seen = await claim(world, made.claim_code)  # type: ignore[arg-type]
    assert (seen.id, seen.state, seen.claimed, seen.amount_kobo) == (
        made.id,
        "CREATED",
        True,
        1_500_000,
    )
    assert (await row(world[2], made.id)).customer_id == AMAKA


async def test_claiming_twice_as_the_same_customer_is_harmless(world) -> None:  # type: ignore[no-untyped-def]
    made = await create(world)
    a, b = await claim(world, made.claim_code), await claim(world, made.claim_code)  # type: ignore[arg-type]
    assert a.id == b.id


async def test_someone_else_cannot_claim_a_claimed_request_and_cannot_tell_it_exists(world) -> None:  # type: ignore[no-untyped-def]
    other = uuid.uuid4()
    async with world[2]() as s:
        s.add(Customer(id=other, display_name="Other", phone="+2348055555555"))
        await s.commit()
    made = await create(world)
    await claim(world, made.claim_code)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as exc:
        await claim(world, made.claim_code, other)  # type: ignore[arg-type]
    assert await code_of(exc) == (404, "CODE_NOT_FOUND")
    with pytest.raises(ApiError) as nothing:
        await claim(world, "0000" if made.claim_code != "0000" else "1111", other)
    assert await code_of(nothing) == (404, "CODE_NOT_FOUND")  # identical answer


async def test_two_customers_racing_for_one_code_only_one_wins(world) -> None:  # type: ignore[no-untyped-def]
    other = uuid.uuid4()
    async with world[2]() as s:
        s.add(Customer(id=other, display_name="Other", phone="+2348055555556"))
        await s.commit()
    made = await create(world)
    results = await asyncio.gather(
        claim(world, made.claim_code),
        claim(world, made.claim_code, other),
        return_exceptions=True,  # type: ignore[arg-type]
    )
    assert sum(isinstance(r, ApiError) for r in results) == 1
    winner = (await row(world[2], made.id)).customer_id
    assert winner in (AMAKA, other)


async def test_a_wrong_code_is_not_found(world) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ApiError) as exc:
        await claim(world, "9999")
    assert await code_of(exc) == (404, "CODE_NOT_FOUND")


async def test_claiming_after_the_deadline_is_410_and_the_expiry_is_saved(world, clock) -> None:  # type: ignore[no-untyped-def]
    made = await create(world)
    clock.advance(121)
    with pytest.raises(ApiError) as exc:
        await claim(world, made.claim_code)  # type: ignore[arg-type]
    assert await code_of(exc) == (410, "REQUEST_EXPIRED")
    assert (await row(world[2], made.id)).state == "EXPIRED"
    with pytest.raises(ApiError) as again:  # the code is free again
        await claim(world, made.claim_code)  # type: ignore[arg-type]
    assert await code_of(again) == (404, "CODE_NOT_FOUND")


# ======================================================================= readback


async def test_the_readback_moves_to_read_back_and_stores_the_hash_of_what_was_read(world) -> None:  # type: ignore[no-untyped-def]
    made = await create(world)
    await claim(world, made.claim_code)  # type: ignore[arg-type]
    rb = await readback(world, made.id)
    assert (
        rb.text
        == "Bisi Ventures dey ask for fifteen thousand naira. One five, zero zero zero. You wan approve?"
    )
    assert (rb.amount_words, rb.payee_name, rb.amount_kobo, rb.lang) == (
        "fifteen thousand",
        "Bisi Ventures",
        1_500_000,
        "pcm",
    )
    assert rb.audio_url == f"/voice/audio/{len(rb.text)}-pcm.mp3"
    r = await row(world[2], made.id)
    assert r.state == "READ_BACK" and r.customer_id == AMAKA
    expected = intent_hash(Intent(
        request_id=r.id, customer_id=AMAKA, payee_account="0123456789", payee_bank_code="057",
        payee_name="BISI VENTURES", amount_kobo=1_500_000, currency="NGN", nonce=r.nonce, expires_at=r.expires_at,
    ))  # fmt: skip
    assert r.intent_hash == expected  # an independent recomputation


async def test_the_english_readback(world) -> None:  # type: ignore[no-untyped-def]
    made = await create(world)
    await claim(world, made.claim_code)  # type: ignore[arg-type]
    assert (await readback(world, made.id, lang="en")).text.startswith(
        "Bisi Ventures is asking for fifteen thousand naira"
    )


async def test_listening_again_gives_the_same_words_and_the_same_hash(world) -> None:  # type: ignore[no-untyped-def]
    made = await to_read_back(world)
    first = (await row(world[2], made.id)).intent_hash
    again = await readback(world, made.id)
    assert (
        again.text.startswith("Bisi Ventures dey ask")
        and (await row(world[2], made.id)).intent_hash == first
    )


async def test_two_simultaneous_readbacks_agree(world) -> None:  # type: ignore[no-untyped-def]
    made = await create(world)
    await claim(world, made.claim_code)  # type: ignore[arg-type]
    a, b = await asyncio.gather(readback(world, made.id), readback(world, made.id))
    assert a.text == b.text and (await row(world[2], made.id)).state == "READ_BACK"


async def test_readback_is_private_to_the_claimer_and_needs_a_supported_language(world) -> None:  # type: ignore[no-untyped-def]
    made = await create(world)
    with pytest.raises(ApiError) as unclaimed:  # nobody has claimed it yet
        await readback(world, made.id)
    assert await code_of(unclaimed) == (404, "NOT_FOUND")
    await claim(world, made.claim_code)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as stranger:
        await readback(world, made.id, customer=uuid.uuid4())
    assert await code_of(stranger) == (404, "NOT_FOUND")
    for lang in ("yo", "fr", ""):
        with pytest.raises(ApiError) as bad:
            await readback(world, made.id, lang=lang)
        assert await code_of(bad) == (422, "VALIDATION_ERROR")


async def test_readback_after_the_deadline_is_410(world, clock) -> None:  # type: ignore[no-untyped-def]
    made = await create(world)
    await claim(world, made.claim_code)  # type: ignore[arg-type]
    clock.advance(130)
    with pytest.raises(ApiError) as exc:
        await readback(world, made.id)
    assert await code_of(exc) == (410, "REQUEST_EXPIRED")
    assert (await row(world[2], made.id)).state == "EXPIRED"


async def test_a_change_after_the_readback_is_reported_not_quietly_re_read(world) -> None:  # type: ignore[no-untyped-def]
    made = await to_read_back(world)
    stored = (await row(world[2], made.id)).intent_hash
    async with world[2]() as s:
        await s.execute(
            update(PaymentRequest).where(PaymentRequest.id == made.id).values(amount_kobo=5_100_000)
        )
        await s.commit()
    with pytest.raises(ApiError) as exc:
        await readback(world, made.id)
    assert await code_of(exc) == (409, "INTENT_CHANGED")
    r = await row(world[2], made.id)
    assert (
        r.state == "READ_BACK" and r.intent_hash == stored
    )  # the signed-for hash is not rewritten


async def test_a_change_before_the_customer_hears_it_is_what_they_hear_and_sign(world) -> None:  # type: ignore[no-untyped-def]
    made = await create(world)
    await claim(world, made.claim_code)  # type: ignore[arg-type]
    async with world[2]() as s:
        await s.execute(
            update(PaymentRequest).where(PaymentRequest.id == made.id).values(amount_kobo=5_100_000)
        )
        await s.commit()
    assert "fifty one thousand" in (await readback(world, made.id, lang="en")).text


# ======================================================================= decline, status, expiry


async def test_decline_ends_the_request_and_is_harmless_twice(world) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made = await to_read_back(world)
    async with sm() as s:
        assert (await svc.decline(s, AMAKA, made.id)).state == "DECLINED"
    async with sm() as s:
        assert (await svc.decline(s, AMAKA, made.id)).state == "DECLINED"
    assert (await row(sm, made.id)).state == "DECLINED"


async def test_decline_only_works_after_the_readback_and_only_for_the_claimer(world) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made = await create(world)
    await claim(world, made.claim_code)  # type: ignore[arg-type]
    async with sm() as s:
        with pytest.raises(ApiError) as early:
            await svc.decline(s, AMAKA, made.id)
    assert await code_of(early) == (409, "STATE_CONFLICT")
    await readback(world, made.id)
    async with sm() as s:
        with pytest.raises(ApiError) as stranger:
            await svc.decline(s, uuid.uuid4(), made.id)
    assert await code_of(stranger) == (404, "NOT_FOUND")


async def test_an_expired_request_cannot_be_declined(world, clock) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made = await to_read_back(world)
    clock.advance(200)
    async with sm() as s:
        with pytest.raises(ApiError) as exc:
            await svc.decline(s, AMAKA, made.id)
    assert await code_of(exc) == (410, "REQUEST_EXPIRED")


async def test_status_is_visible_to_the_agent_and_the_claimer_only(world) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made = await create(world)
    async with sm() as s:
        assert (await svc.get_request(s, Viewer("agent", BISI), made.id)).state == "CREATED"
    async with sm() as s:
        with pytest.raises(ApiError) as other_agent:
            await svc.get_request(s, Viewer("agent", MAMA), made.id)
    assert await code_of(other_agent) == (404, "NOT_FOUND")
    async with sm() as s:
        with pytest.raises(ApiError) as unclaimed:
            await svc.get_request(s, Viewer("customer", AMAKA), made.id)
    assert await code_of(unclaimed) == (404, "NOT_FOUND")
    await claim(world, made.claim_code)  # type: ignore[arg-type]
    async with sm() as s:
        assert (await svc.get_request(s, Viewer("customer", AMAKA), made.id)).claimed


async def test_expiry_is_applied_lazily_when_the_status_is_read(world, clock) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made = await to_read_back(world)
    assert (await row(sm, made.id)).state == "READ_BACK"
    clock.advance(121)
    assert (await row(sm, made.id)).state == "READ_BACK"  # nothing has looked at it yet
    async with sm() as s:
        view = await svc.get_request(s, Viewer("agent", BISI), made.id)
    assert view.state == "EXPIRED"  # status shows it, it does not raise
    assert (await row(sm, made.id)).state == "EXPIRED"


# ======================================================================= settle (the transfer)


async def total_debits(sm: SM) -> int:
    async with sm() as s:
        return (await s.execute(select(func.count()).select_from(MockTransfer))).scalar_one()


async def balance(sm: SM, number: str) -> int:
    async with sm() as s:
        return (
            await s.execute(
                select(MockAccount.balance_kobo).where(MockAccount.account_number == number)
            )
        ).scalar_one()


async def test_settling_an_approved_request_moves_the_money_once(world) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made = await to_read_back(world)
    await force_approved(sm, made.id)
    async with sm() as s:
        done = await svc.settle(s, made.id)
    assert done.state == "SETTLED" and (done.bank_reference or "").startswith("MOCK-")
    assert await balance(sm, "2000000001") == 250_000 * NAIRA - 15_000 * NAIRA
    assert await balance(sm, "0123456789") == 500_000 * NAIRA + 15_000 * NAIRA
    r = await row(sm, made.id)
    assert r.settled_at == START and r.bank_reference == done.bank_reference


async def test_settling_again_never_pays_twice(world) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made = await to_read_back(world)
    await force_approved(sm, made.id)
    for _ in range(3):
        async with sm() as s:
            assert (await svc.settle(s, made.id)).state == "SETTLED"
    assert await total_debits(sm) == 1 and await balance(sm, "2000000001") == 235_000 * NAIRA


async def test_five_simultaneous_settles_send_one_transfer(world) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made = await to_read_back(world)
    await force_approved(sm, made.id)

    async def go() -> str:
        async with sm() as s:
            return (await svc.settle(s, made.id)).state

    states = await asyncio.gather(*[go() for _ in range(5)])
    assert set(states) <= {"SETTLED", "SUBMITTED"}
    async with sm() as s:  # a final settle makes the outcome certain
        assert (await svc.settle(s, made.id)).state == "SETTLED"
    assert await total_debits(sm) == 1 and await balance(sm, "2000000001") == 235_000 * NAIRA


async def test_a_dropped_network_leaves_it_submitted_and_the_retry_pays_exactly_once(world) -> None:  # type: ignore[no-untyped-def]
    svc, bank, sm = world
    bank.fail_times = 1
    made = await to_read_back(world)
    await force_approved(sm, made.id)
    async with sm() as s:
        first = await svc.settle(s, made.id)
    assert first.state == "SUBMITTED" and await balance(sm, "2000000001") == 250_000 * NAIRA
    async with sm() as s:
        second = await svc.settle(s, made.id)
    assert second.state == "SETTLED"
    assert await balance(sm, "2000000001") == 235_000 * NAIRA and await total_debits(sm) == 1


async def test_a_bank_rejection_fails_the_request_and_moves_no_money(world) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made = await to_read_back(world)
    await force_approved(sm, made.id)
    async with sm() as s:
        await s.execute(
            update(MockAccount)
            .where(MockAccount.account_number == "2000000001")
            .values(balance_kobo=100 * NAIRA)
        )
        await s.commit()
    async with sm() as s:
        done = await svc.settle(s, made.id)
    assert (done.state, done.failure_reason, done.bank_reference) == (
        "FAILED",
        "INSUFFICIENT_FUNDS",
        None,
    )
    assert await balance(sm, "2000000001") == 100 * NAIRA


async def test_only_an_approved_request_is_ever_sent_to_the_bank(world) -> None:  # type: ignore[no-untyped-def]
    svc, bank, sm = world
    made = await to_read_back(world)  # READ_BACK: heard but not signed
    async with sm() as s:
        assert (await svc.settle(s, made.id)).state == "READ_BACK"
    declined = await to_read_back(world)
    async with sm() as s:
        await svc.decline(s, AMAKA, declined.id)
        assert (await svc.settle(s, declined.id)).state == "DECLINED"
    assert bank.calls == 0 and await total_debits(sm) == 0


# ======================================================================= daily total


async def test_the_daily_total_counts_signed_payments_on_the_lagos_calendar_day(world) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    lagos_noon = datetime(2026, 10, 21, 11, 0, tzinfo=UTC)  # 12:00 in Lagos (UTC+1)
    cases = [  # (when approved, state, amount, counted?)
        (
            datetime(2026, 10, 20, 22, 59, tzinfo=UTC),
            "SETTLED",
            1_000 * NAIRA,
            False,
        ),  # 23:59 Lagos, the day before
        (
            datetime(2026, 10, 20, 23, 0, tzinfo=UTC),
            "SETTLED",
            2_000 * NAIRA,
            True,
        ),  # 00:00 Lagos, today
        (datetime(2026, 10, 21, 9, 0, tzinfo=UTC), "APPROVED", 3_000 * NAIRA, True),
        (datetime(2026, 10, 21, 9, 5, tzinfo=UTC), "SUBMITTED", 4_000 * NAIRA, True),
        (
            datetime(2026, 10, 21, 22, 59, tzinfo=UTC),
            "SETTLED",
            5_000 * NAIRA,
            True,
        ),  # 23:59 Lagos, still today
        (
            datetime(2026, 10, 21, 23, 0, tzinfo=UTC),
            "SETTLED",
            6_000 * NAIRA,
            False,
        ),  # tomorrow in Lagos
    ]
    for when, state, amount, _ in cases:
        made = await to_read_back(world, amount)
        async with sm() as s:
            values = {"state": state, "approved_at": when}
            if state == "SETTLED":
                values |= {"bank_reference": f"R{amount}", "settled_at": when}
            await s.execute(
                update(PaymentRequest).where(PaymentRequest.id == made.id).values(**values)
            )
            await s.commit()
    declined = await to_read_back(world, 9_000 * NAIRA)
    async with sm() as s:
        await svc.decline(s, AMAKA, declined.id)
    async with sm() as s:
        total = await svc.approved_today_kobo(s, AMAKA, lagos_noon)
    assert total == sum(a for _, _, a, counted in cases if counted)


# ======================================================================= audit


async def test_the_audit_trail_tells_the_story_without_personal_data(world) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made = await to_read_back(world)
    await force_approved(sm, made.id)
    async with sm() as s:
        await svc.settle(s, made.id)
    async with sm() as s:
        events = (await s.execute(select(AuditEvent).order_by(AuditEvent.id))).scalars().all()
    assert [e.event for e in events] == [
        "request.created", "request.claimed", "request.read_back", "transfer.submitted", "transfer.settled",
    ]  # fmt: skip
    dump = " ".join(f"{e.event} {e.actor} {e.details}" for e in events)
    for private in ("BISI", "Bisi", "Amaka", "0123456789", "2000000001", "1500000", "15000"):
        assert private not in dump, private
    assert all(e.request_id == made.id for e in events)


# ======================================================================= module boundaries


def test_only_the_consent_module_calls_transfer_or_changes_state() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "zolo"
    offenders = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).parts
        text_ = path.read_text("utf-8")
        in_consent, in_bank = rel[0] == "consent", rel[0] == "bank"
        if re.search(r"\.transfer\(", text_) and not (in_consent or in_bank):
            offenders.append(f"{path.name}: calls transfer")
        if re.search(r"consent\.machine|apply_transition", text_) and not in_consent:
            offenders.append(f"{path.name}: uses the state machine")
    assert offenders == [], offenders
    # the AI package can only draft: it must not reach consent or the bank at all
    for path in (root / "ai").rglob("*.py"):
        assert not re.search(r"zolo\.(consent|bank)", path.read_text("utf-8")), path.name


def test_transfer_results_are_plain_values() -> None:
    assert TransferResult(status="SUCCESS", reference="R").replayed is False


# ======================================================================= the deadline is exact


async def test_a_request_expires_at_exactly_its_deadline_not_a_moment_after(world, clock) -> None:  # type: ignore[no-untyped-def]
    made = await create(world)  # expires START + 120s
    clock.advance(119.999)
    async with world[2]() as s:
        assert (await world[0].get_request(s, Viewer("agent", BISI), made.id)).state == "CREATED"
    clock.advance(0.001)  # now == expires_at exactly
    async with world[2]() as s:
        assert (await world[0].get_request(s, Viewer("agent", BISI), made.id)).state == "EXPIRED"


async def test_claiming_at_exactly_the_deadline_is_too_late(world, clock) -> None:  # type: ignore[no-untyped-def]
    made = await create(world)
    clock.advance(120)
    with pytest.raises(ApiError) as exc:
        await claim(world, made.claim_code)  # type: ignore[arg-type]
    assert await code_of(exc) == (410, "REQUEST_EXPIRED")


async def test_declining_and_reading_back_at_exactly_the_deadline_are_too_late(
    world, clock
) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made = await to_read_back(world)
    clock.advance(120)
    for call in (
        lambda s: svc.decline(s, AMAKA, made.id),
        lambda s: svc.get_readback(s, AMAKA, made.id, "pcm"),
    ):
        async with sm() as s:
            with pytest.raises(ApiError) as exc:
                await call(s)
        assert await code_of(exc) == (410, "REQUEST_EXPIRED")
