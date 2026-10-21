"""Every state a request can be in, against every action a customer can try.

The unit tests prove the transition TABLE is right. This proves the real operations behave right in
every state: the exact outcome, and that money moves only where it should (the settle step on a
request that is APPROVED or SUBMITTED, and nowhere else).
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.test_consent_engine import (
    AMAKA,
    NAIRA,
    Clock,
    Flaky,
    StubAudio,
    balance,
    claim,
    create,
    force_approved,
    readback,
    row,
)
from tests.integration.test_passkeys import register
from tests.webauthn_software import SoftwareAuthenticator
from zolo.bank.mock import Latency, MockBankAdapter
from zolo.bank.models import MockAccount, MockTransfer
from zolo.consent.service import ConsentService
from zolo.core.config import Settings
from zolo.core.errors import ApiError
from zolo.demo.seed import reset_demo

SM = async_sessionmaker[AsyncSession]
GARBAGE = {"id": "x", "rawId": "AAAA", "type": "public-key", "response": {}}
STATES = [
    "CREATED",
    "READ_BACK",
    "APPROVED",
    "SUBMITTED",
    "SETTLED",
    "DECLINED",
    "EXPIRED",
    "FAILED",
]
OPS = ["claim", "readback", "challenge", "approve", "decline", "settle"]
START_BALANCE = 250_000 * NAIRA


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
async def world(sessionmaker: SM, settings: Settings, clock: Clock):  # type: ignore[no-untyped-def]
    await reset_demo(sessionmaker, settings)
    bank = Flaky(MockBankAdapter(sessionmaker, latency=Latency(0, 0)))
    svc = ConsentService(settings, bank, audio=StubAudio(), clock=clock)  # type: ignore[arg-type]
    return svc, bank, sessionmaker


async def build(world, clock: Clock, state: str) -> tuple[uuid.UUID, str]:  # type: ignore[no-untyped-def]
    """Get a real request into `state`, the same way real traffic would (APPROVED is forced: the
    engine never rests there, because the transfer is sent straight after the approval)."""
    svc, bank, sm = world
    phone = SoftwareAuthenticator()
    await register(world, phone)
    made = await create(world)
    code = made.claim_code or ""
    await claim(world, code)
    if state == "CREATED":
        return made.id, code
    await readback(world, made.id)
    if state == "READ_BACK":
        return made.id, code
    if state == "DECLINED":
        async with sm() as s:
            await svc.decline(s, AMAKA, made.id)
    elif state == "EXPIRED":
        clock.advance(200)
        async with sm() as s:
            await svc.get_request(
                s,
                __import__("zolo.consent.service", fromlist=["Viewer"]).Viewer("customer", AMAKA),
                made.id,
            )
    else:  # the approved family: get a challenge and a real signature first
        async with sm() as s:
            options = await svc.issue_challenge(s, AMAKA, made.id)
        if state == "APPROVED":
            await force_approved(sm, made.id)
        elif state == "SUBMITTED":
            bank.fail_times = bank.calls + 1  # the network drops once
            async with sm() as s:
                await svc.approve(s, AMAKA, made.id, phone.assert_(options))
        elif state == "SETTLED":
            async with sm() as s:
                await svc.approve(s, AMAKA, made.id, phone.assert_(options))
        elif state == "FAILED":
            async with sm() as s:
                await s.execute(
                    update(MockAccount)
                    .where(MockAccount.account_number == "2000000001")
                    .values(balance_kobo=100 * NAIRA)
                )
                await s.commit()
            async with sm() as s:
                await svc.approve(s, AMAKA, made.id, phone.assert_(options))
    got = (await row(sm, made.id)).state
    assert got == state, f"could not build {state}, got {got}"
    return made.id, code


async def attempt(world, op: str, request_id: uuid.UUID, code: str) -> tuple[Any, ...]:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    try:
        async with sm() as s:
            if op == "claim":
                v: Any = await svc.claim(s, AMAKA, code)
            elif op == "readback":
                await svc.get_readback(s, AMAKA, request_id, "pcm")
                v = None
            elif op == "challenge":
                await svc.issue_challenge(s, AMAKA, request_id)
                v = None
            elif op == "approve":
                v = await svc.approve(s, AMAKA, request_id, GARBAGE)
            elif op == "decline":
                v = await svc.decline(s, AMAKA, request_id)
            else:
                v = await svc.settle(s, request_id)
    except ApiError as exc:
        return ("err", exc.status, exc.code.value)
    return ("ok", v.state if v is not None else None)


ERR = lambda status, code: ("err", status, code)  # noqa: E731

# (state, op) -> (outcome, state afterwards, a new transfer expected?)
EXPECT: dict[tuple[str, str], tuple[tuple[Any, ...], str, bool]] = {}


def row_(state: str, **ops: tuple[Any, ...]) -> None:
    for op, spec in ops.items():
        outcome, after, *moved = spec
        EXPECT[(state, op)] = (outcome, after, bool(moved and moved[0]))


NOT_FOUND = ERR(404, "CODE_NOT_FOUND")
CONFLICT = ERR(409, "STATE_CONFLICT")
USED = ERR(409, "ALREADY_USED")
GONE = ERR(410, "REQUEST_EXPIRED")

row_("CREATED", claim=(("ok", "CREATED"), "CREATED"), readback=(("ok", None), "READ_BACK"),
     challenge=(CONFLICT, "CREATED"), approve=(CONFLICT, "CREATED"), decline=(CONFLICT, "CREATED"),
     settle=(("ok", "CREATED"), "CREATED"))  # fmt: skip
row_("READ_BACK", claim=(("ok", "READ_BACK"), "READ_BACK"), readback=(("ok", None), "READ_BACK"),
     challenge=(("ok", None), "READ_BACK"), approve=(ERR(409, "CHALLENGE_NOT_FOUND"), "READ_BACK"),
     decline=(("ok", "DECLINED"), "DECLINED"), settle=(("ok", "READ_BACK"), "READ_BACK"))  # fmt: skip
row_("DECLINED", claim=(NOT_FOUND, "DECLINED"), readback=(CONFLICT, "DECLINED"), challenge=(CONFLICT, "DECLINED"),
     approve=(CONFLICT, "DECLINED"), decline=(("ok", "DECLINED"), "DECLINED"), settle=(("ok", "DECLINED"), "DECLINED"))  # fmt: skip
row_("EXPIRED", claim=(NOT_FOUND, "EXPIRED"), readback=(GONE, "EXPIRED"), challenge=(GONE, "EXPIRED"),
     approve=(GONE, "EXPIRED"), decline=(GONE, "EXPIRED"), settle=(("ok", "EXPIRED"), "EXPIRED"))  # fmt: skip
row_("APPROVED", claim=(NOT_FOUND, "APPROVED"), readback=(CONFLICT, "APPROVED"), challenge=(CONFLICT, "APPROVED"),
     approve=(CONFLICT, "APPROVED"), decline=(CONFLICT, "APPROVED"), settle=(("ok", "SETTLED"), "SETTLED", True))  # fmt: skip
row_("SUBMITTED", claim=(NOT_FOUND, "SUBMITTED"), readback=(CONFLICT, "SUBMITTED"), challenge=(CONFLICT, "SUBMITTED"),
     approve=(USED, "SUBMITTED"), decline=(CONFLICT, "SUBMITTED"), settle=(("ok", "SETTLED"), "SETTLED", True))  # fmt: skip
row_("SETTLED", claim=(NOT_FOUND, "SETTLED"), readback=(CONFLICT, "SETTLED"), challenge=(CONFLICT, "SETTLED"),
     approve=(USED, "SETTLED"), decline=(CONFLICT, "SETTLED"), settle=(("ok", "SETTLED"), "SETTLED"))  # fmt: skip
row_("FAILED", claim=(NOT_FOUND, "FAILED"), readback=(CONFLICT, "FAILED"), challenge=(CONFLICT, "FAILED"),
     approve=(USED, "FAILED"), decline=(CONFLICT, "FAILED"), settle=(("ok", "FAILED"), "FAILED"))  # fmt: skip


def test_the_matrix_covers_every_cell() -> None:
    assert set(EXPECT) == {(s, o) for s in STATES for o in OPS}


async def transfers(sm: SM) -> int:
    async with sm() as s:
        return (await s.execute(select(func.count()).select_from(MockTransfer))).scalar_one()


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("op", OPS)
async def test_every_action_in_every_state(world, clock, state: str, op: str) -> None:  # type: ignore[no-untyped-def]
    outcome, after, moves_money = EXPECT[(state, op)]
    request_id, code = await build(world, clock, state)
    sm = world[2]
    transfers_before = await transfers(sm)
    paid_before = await balance(sm, "2000000001")

    got = await attempt(world, op, request_id, code)

    assert got == outcome, f"{op} on a {state} request"
    assert (await row(sm, request_id)).state == after
    new_transfers = (await transfers(sm)) - transfers_before
    if moves_money:  # only the settle step, only on a request that was signed and not yet paid
        assert new_transfers == 1 or (state == "SUBMITTED" and new_transfers == 0)
        assert (await balance(sm, "2000000001")) <= paid_before
    else:
        assert new_transfers == 0 and await balance(sm, "2000000001") == paid_before, (
            "money moved where it must not"
        )


@pytest.mark.parametrize("state", ["SUBMITTED", "SETTLED"])
async def test_a_signed_request_is_debited_exactly_once_whatever_is_attempted_afterwards(
    world, clock, state: str
) -> None:  # type: ignore[no-untyped-def]
    request_id, code = await build(world, clock, state)
    sm = world[2]
    for op in OPS * 2:
        await attempt(world, op, request_id, code)
    assert await balance(sm, "2000000001") == START_BALANCE - 15_000 * NAIRA
    async with sm() as s:
        assert (
            await s.execute(
                select(func.count())
                .select_from(MockTransfer)
                .where(MockTransfer.status == "SUCCESS")
            )
        ).scalar_one() == 1
