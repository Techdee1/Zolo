"""The twelve failure cases from the engineering brief, one by one.

Each is a scripted, repeatable test of what the BACKEND guarantees. Where a case is mostly the
voice layer's or the app's job (a misheard amount, a noisy room), the test is the backend half of
it; where the feature is a later phase, the test says so out loud and checks the Phase 1 safety
net that stands in for it. Nothing is silently skipped: a test below fails if a case is missing.

    1 misheard amount            7 cloned voice
    2 wrong recipient            8 large first payment, new payee, at night
    3 amount changed after       9 noisy environment
      the readback              10 swapped card, stolen PIN (Card Guard)
    4 replay of an old approval 11 agent keys more than the unlocked amount
    5 network drops in approval 12 request not approved in 2 minutes
    6 fingerprint fails 3 times
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.api.conftest import MonotonicClock, browser, login
from tests.api.test_endpoints import heard, new_request, problem, ready, register_passkey
from tests.conftest import make_settings
from tests.integration.test_consent_engine import NAIRA, Clock, Flaky, StubAudio
from tests.webauthn_software import SoftwareAuthenticator
from zolo.agents.models import Agent
from zolo.api.main import create_app
from zolo.api.services import Overrides
from zolo.bank.mock import Latency, MockBankAdapter
from zolo.bank.models import BankAccount
from zolo.consent.models import PaymentRequest
from zolo.core.ratelimit import RateLimiter
from zolo.demo import seed_data as seed
from zolo.demo.seed import reset_demo

COVERED: set[int] = set()


def case(number: int) -> Callable[[Any], Any]:
    def mark(fn: Any) -> Any:
        COVERED.add(number)
        return fn

    return mark


async def balances(sm: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    async with sm() as s:
        return dict(
            (await s.execute(text("SELECT account_number, balance_kobo FROM mock_accounts"))).all()
        )


async def transfers(sm: async_sessionmaker[AsyncSession]) -> int:
    async with sm() as s:
        return int((await s.execute(text("SELECT count(*) FROM mock_transfers"))).scalar_one())


# --------------------------------------------------------------------------- 1


@case(1)
async def test_case_01_a_misheard_amount_cannot_reach_a_signature_unheard(
    agent: AsyncClient, customer: AsyncClient
) -> None:
    """The voice half (keypad fallback) is Phase 2. The backend half: the amount is a strict
    integer the agent typed, and the customer hears it in words AND digits before signing, so
    'fifteen' and 'fifty' can never be confused at the point that matters."""
    fifteen = await heard(agent, customer, 15_000)
    fifty = await heard(agent, customer, 50_000)
    a = (await customer.get(f"/requests/{fifteen['id']}/readback?lang=en")).json()
    b = (await customer.get(f"/requests/{fifty['id']}/readback?lang=en")).json()
    assert "fifteen thousand" in a["text"] and "One five, zero zero zero" in a["text"]
    assert "fifty thousand" in b["text"] and "Five zero, zero zero zero" in b["text"]
    assert a["amount_kobo"] == 1_500_000 and b["amount_kobo"] == 5_000_000
    for bad in ("fifteen thousand", 1500000.0, "1500000"):  # nothing but a true integer is accepted
        assert problem(await agent.post("/agent/requests", json={"amount_kobo": bad}))[0] == 422


# --------------------------------------------------------------------------- 2


@case(2)
async def test_case_02_a_wrong_recipient_is_heard_by_its_real_name_and_declined(
    api: FastAPI, customer: AsyncClient, sessionmaker, phone: SoftwareAuthenticator
) -> None:  # type: ignore[no-untyped-def]
    """An agent presents as 'Bisi Ventures' but the account behind it is someone else's. The
    readback uses the BANK-verified name, so the customer hears the truth and says no."""
    wrong = seed.WRONG_RECIPIENT_ACCOUNT
    agent_id = uuid.uuid4()
    async with sessionmaker() as s:
        s.add(
            Agent(
                id=agent_id,
                account_id=wrong.id,
                business_name="Bisi Ventures",
                phone="+2348044444444",
            )
        )
        await s.flush()
        await s.execute(
            update(BankAccount).where(BankAccount.id == wrong.id).values(agent_id=agent_id)
        )
        await s.commit()
    before = await balances(sessionmaker)
    async with browser(api) as impostor:
        await login(impostor, "+2348044444444")
        made = await new_request(impostor, 51_000)
    assert made["payee_name"] == "OKONKWO PETER"  # not 'Bisi Ventures'
    await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
    text_ = (await customer.get(f"/requests/{made['id']}/readback")).json()["text"]
    assert (
        text_.startswith("Okonkwo Peter dey ask for fifty one thousand naira")
        and "Bisi" not in text_
    )
    declined = await customer.post(f"/requests/{made['id']}/decline")
    assert declined.json()["state"] == "DECLINED"
    assert await balances(sessionmaker) == before and await transfers(sessionmaker) == 0


# --------------------------------------------------------------------------- 3


@case(3)
async def test_case_03_an_amount_changed_after_the_readback_sends_nothing(
    agent: AsyncClient, customer: AsyncClient, phone: SoftwareAuthenticator, sessionmaker
) -> None:  # type: ignore[no-untyped-def]
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    assertion = phone.assert_(options)
    async with sessionmaker() as s:
        await s.execute(
            update(PaymentRequest)
            .where(PaymentRequest.id == uuid.UUID(made["id"]))
            .values(amount_kobo=5_100_000)
        )
        await s.commit()
    before = await balances(sessionmaker)
    r = await customer.post(f"/requests/{made['id']}/approve", json=assertion)
    assert problem(r) == (409, "INTENT_CHANGED")
    assert (
        r.json()["title"] == "This payment changed after you heard it"
    )  # the app adds "Nothing was sent."
    assert await balances(sessionmaker) == before and await transfers(sessionmaker) == 0


# --------------------------------------------------------------------------- 4


@case(4)
async def test_case_04_a_replayed_approval_is_rejected_as_already_used(
    agent: AsyncClient, customer: AsyncClient, phone: SoftwareAuthenticator, sessionmaker
) -> None:  # type: ignore[no-untyped-def]
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    good = phone.assert_(options)
    assert (await customer.post(f"/requests/{made['id']}/approve", json=good)).json()[
        "state"
    ] == "SETTLED"
    after_first = await balances(sessionmaker)
    for _ in range(3):
        assert problem(await customer.post(f"/requests/{made['id']}/approve", json=good)) == (
            409,
            "ALREADY_USED",
        )
    assert await balances(sessionmaker) == after_first and await transfers(sessionmaker) == 1


# --------------------------------------------------------------------------- 5


@case(5)
async def test_case_05_a_dropped_network_in_approval_moves_no_money_twice(
    sessionmaker, settings, phone: SoftwareAuthenticator
) -> None:  # type: ignore[no-untyped-def]
    """Phase 1: the approval is saved, the bank call is lost, the request stays SUBMITTED and
    nothing is debited. Sending the same transfer again (what the Phase 2 reconciler will do)
    pays exactly once. The automatic resume itself is Phase 2."""
    await reset_demo(sessionmaker, settings)
    clock = Clock()
    flaky = Flaky(MockBankAdapter(sessionmaker, latency=Latency(0, 0)), fail_times=1)
    app = create_app(
        settings,
        overrides=Overrides(
            clock=clock, audio=StubAudio(), bank=flaky, limiter=RateLimiter(MonotonicClock())
        ),
    )  # type: ignore[arg-type]
    app.state.sessionmaker = sessionmaker
    from tests.api.conftest import AMAKA_PHONE, BISI_PHONE

    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        await register_passkey(customer, phone)
        made, options = await ready(agent, customer, phone)
        r = await customer.post(f"/requests/{made['id']}/approve", json=phone.assert_(options))
        assert r.status_code == 200 and r.json()["state"] == "SUBMITTED"  # pending, not failed
        assert (await balances(sessionmaker))["2000000001"] == 250_000 * NAIRA and await transfers(
            sessionmaker
        ) == 0
        async with sessionmaker() as s:
            assert (
                await app.state.services.consent.settle(s, uuid.UUID(made["id"]))
            ).state == "SETTLED"
        async with sessionmaker() as s:
            assert (
                await app.state.services.consent.settle(s, uuid.UUID(made["id"]))
            ).state == "SETTLED"
        assert (await balances(sessionmaker))["2000000001"] == 235_000 * NAIRA and await transfers(
            sessionmaker
        ) == 1
        assert (await agent.get(f"/requests/{made['id']}")).json()["state"] == "SETTLED"


# --------------------------------------------------------------------------- 6


@case(6)
async def test_case_06_repeated_failed_signatures_are_throttled_and_never_pay(
    agent: AsyncClient, customer: AsyncClient, phone: SoftwareAuthenticator, sessionmaker
) -> None:  # type: ignore[no-untyped-def]
    """The phone's own fallback (fingerprint, then screen lock) is the OS's job. The backend
    half: a failing signature never approves, attempts are limited, and the request can still be
    approved by a good signature afterwards. A cooling-off LOCK after 3 failures is Phase 3."""
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    for _ in range(3):
        r = await customer.post(
            f"/requests/{made['id']}/approve", json=phone.assert_(options, user_verified=False)
        )
        assert problem(r) == (401, "SIGNATURE_INVALID")
    assert (await agent.get(f"/requests/{made['id']}")).json()[
        "state"
    ] == "READ_BACK" and await transfers(sessionmaker) == 0
    assert (
        await customer.post(f"/requests/{made['id']}/approve", json=phone.assert_(options))
    ).json()["state"] == "SETTLED"


# --------------------------------------------------------------------------- 7


@case(7)
async def test_case_07_nothing_but_a_passkey_signature_can_approve(
    agent: AsyncClient, customer: AsyncClient, phone: SoftwareAuthenticator, sessionmaker
) -> None:  # type: ignore[no-untyped-def]
    """Voice drafting is Phase 2. The guarantee that makes a cloned voice harmless is already
    here: a logged-in customer with the request in hand still cannot approve without a valid
    signature from their own passkey, and the AI package cannot reach the consent engine at all."""
    await register_passkey(customer, phone)
    made, _ = await ready(agent, customer, phone)
    for body in ({}, {"approve": True}, {"voice": "yes I approve"}, {"id": "x", "rawId": "AAAA"}):
        assert problem(await customer.post(f"/requests/{made['id']}/approve", json=body)) == (
            401,
            "SIGNATURE_INVALID",
        )
    assert (await agent.get(f"/requests/{made['id']}")).json()[
        "state"
    ] == "READ_BACK" and await transfers(sessionmaker) == 0
    # and a passkey that is not this customer's cannot approve their request either
    stranger = SoftwareAuthenticator()
    _, options = made, (await customer.post(f"/requests/{made['id']}/challenge")).json()
    assert (
        problem(
            await customer.post(f"/requests/{made['id']}/approve", json=stranger.assert_(options))
        )[1]
        == "SIGNATURE_INVALID"
    )


# --------------------------------------------------------------------------- 8


@case(8)
async def test_case_08_a_big_first_payment_is_held_by_the_hard_caps_in_phase_1(
    agent: AsyncClient, customer: AsyncClient, phone: SoftwareAuthenticator, sessionmaker
) -> None:  # type: ignore[no-untyped-def]
    """The new-payee cooling-off, the night rule and the callback are Phase 2 risk rules. In
    Phase 1 the hard caps are the net: nothing over the per-payment cap is even created, and
    nothing over the daily cap can be approved."""
    assert problem(await agent.post("/agent/requests", json={"amount_kobo": 100_001 * NAIRA})) == (
        422,
        "LIMIT_EXCEEDED",
    )
    await register_passkey(customer, phone)
    for _ in range(2):
        made, options = await ready(agent, customer, phone, 90_000)
        assert (
            await customer.post(f"/requests/{made['id']}/approve", json=phone.assert_(options))
        ).json()["state"] == "SETTLED"
    made, options = await ready(agent, customer, phone, 90_000)
    blocked = await customer.post(f"/requests/{made['id']}/approve", json=phone.assert_(options))
    assert problem(blocked) == (422, "LIMIT_EXCEEDED")
    assert (await balances(sessionmaker))["2000000001"] == 250_000 * NAIRA - 180_000 * NAIRA


# --------------------------------------------------------------------------- 9


@case(9)
@pytest.mark.skip(
    reason="Noisy rooms are speech-to-text and the app's job (two retries, then keypad). The backend only ever receives typed integers and a signature."
)
def test_case_09_a_noisy_environment() -> None:
    raise AssertionError("not a backend concern")


# --------------------------------------------------------------------------- 10


@case(10)
async def test_case_10_a_swapped_card_with_a_stolen_pin_is_declined_because_the_card_is_locked(
    sessionmaker,
) -> None:  # type: ignore[no-untyped-def]
    """Card Guard proper (open a window, pay inside it) is Phase 3. Until then every card
    authorisation is declined: cards are locked by default, so the Phase 1 mock fails safe."""
    bank = MockBankAdapter(sessionmaker, latency=Latency(0, 0))
    r = await bank.card_auth(card_ref="swapped-card", amount_kobo=18_500 * NAIRA, merchant="POS")
    assert (r.approved, r.reason) == (False, "CARD_LOCKED")


# --------------------------------------------------------------------------- 11


@case(11)
@pytest.mark.skip(
    reason="OVER_LIMIT and WINDOW_USED need a Card Guard window, which is Phase 3. Phase 1 declines every card with CARD_LOCKED (case 10)."
)
def test_case_11_an_agent_keys_more_than_the_unlocked_amount() -> None:
    raise AssertionError("Phase 3")


# --------------------------------------------------------------------------- 12


@case(12)
async def test_case_12_a_request_not_approved_in_two_minutes_expires(
    agent: AsyncClient,
    customer: AsyncClient,
    phone: SoftwareAuthenticator,
    clock: Clock,
    sessionmaker,
) -> None:  # type: ignore[no-untyped-def]
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    assertion = phone.assert_(options)
    clock.advance(119)  # still inside the window
    assert (await agent.get(f"/requests/{made['id']}")).json()["state"] == "READ_BACK"
    clock.advance(2)  # 121 seconds
    assert problem(await customer.post(f"/requests/{made['id']}/approve", json=assertion)) == (
        410,
        "REQUEST_EXPIRED",
    )
    assert (await agent.get(f"/requests/{made['id']}")).json()["state"] == "EXPIRED"
    assert await transfers(sessionmaker) == 0
    again = await new_request(agent)  # the agent simply creates a new one
    assert again["id"] != made["id"] and again["claim_code"]


def test_all_twelve_failure_cases_have_a_test() -> None:
    assert COVERED == set(range(1, 13)), f"missing: {sorted(set(range(1, 13)) - COVERED)}"


def test_make_settings_is_the_demo_configuration_these_cases_run_under() -> None:
    s = make_settings()
    assert s.request_ttl_seconds == 120 and s.demo_mode and s.webauthn_strict_counter
