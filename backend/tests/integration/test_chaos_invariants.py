"""Random sequences of everything a customer, an agent, an attacker and bad luck can do, with the
rules that must NEVER break checked after every step.

Each seed is a different, reproducible storm of: creating, claiming (right and wrong codes),
reading back, asking for challenges, approving (good, corrupt and old signatures), declining,
tampering, expiring, the clock jumping, the bank dropping calls, and retrying the transfer.
A failure prints the seed and step, so it can be replayed exactly.
"""

import random
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.conftest import make_settings
from tests.integration.test_consent_engine import AMAKA, BISI, NAIRA, Clock, Flaky, StubAudio
from tests.integration.test_passkeys import register
from tests.webauthn_software import SoftwareAuthenticator
from zolo.audit.models import AuditEvent
from zolo.bank.mock import Latency, MockBankAdapter
from zolo.bank.models import MockAccount, MockTransfer
from zolo.consent.intent import intent_hash
from zolo.consent.models import PaymentRequest
from zolo.consent.service import ConsentService
from zolo.core.config import Settings
from zolo.core.db import make_sessionmaker
from zolo.core.errors import ApiError
from zolo.demo.seed import reset_demo
from zolo.passkeys.models import WebAuthnChallenge

SM = async_sessionmaker[AsyncSession]
TERMINAL = {"SETTLED", "DECLINED", "EXPIRED", "FAILED"}
SIGNED = {"APPROVED", "SUBMITTED", "SETTLED", "FAILED"}
CUSTOMER_ACCOUNT = "2000000001"


class Storm:
    def __init__(self, seed: int, settings: Settings, sm: SM) -> None:
        self.seed, self.rng, self.sm, self.settings = seed, random.Random(seed), sm, settings
        self.clock = Clock()
        self.bank = Flaky(MockBankAdapter(sm, latency=Latency(0, 0)))
        self.svc = ConsentService(settings, self.bank, audio=StubAudio(), clock=self.clock)  # type: ignore[arg-type]
        self.phone = SoftwareAuthenticator()
        self.phone.counter_mode = (
            "zero"  # platform-style passkey: replay safety comes from the challenge
        )
        self.ids: list[uuid.UUID] = []
        self.codes: dict[uuid.UUID, str] = {}
        self.signed: dict[uuid.UUID, dict[str, Any]] = {}
        self.final: dict[uuid.UUID, str] = {}
        self.initial_total = 0
        self.initial_customer = 0
        self.log: list[str] = []

    async def setup(self, world: tuple[Any, Any, SM]) -> None:
        await register(world, self.phone)
        async with self.sm() as s:
            self.initial_total = (
                await s.execute(select(func.sum(MockAccount.balance_kobo)))
            ).scalar_one()
            self.initial_customer = (
                await s.execute(
                    select(MockAccount.balance_kobo).where(
                        MockAccount.account_number == CUSTOMER_ACCOUNT
                    )
                )
            ).scalar_one()

    async def states(self) -> dict[uuid.UUID, tuple[str, bool]]:
        async with self.sm() as s:
            rows = (
                await s.execute(
                    select(PaymentRequest.id, PaymentRequest.state, PaymentRequest.customer_id)
                )
            ).all()
        return {r[0]: (r[1], r[2] is not None) for r in rows}

    async def pick(self, op: str) -> uuid.UUID | None:
        """Usually a request that this operation can actually advance (so the storm really pays
        people), sometimes any request at all (so it also misbehaves)."""
        if not self.ids:
            return None
        if self.rng.random() < 0.25:
            return self.rng.choice(self.ids)
        known = await self.states()
        fits = {
            "claim": lambda st, claimed: st == "CREATED" and not claimed,
            "readback": lambda st, claimed: st in ("CREATED", "READ_BACK") and claimed,
            "challenge": lambda st, claimed: st == "READ_BACK",
            "approve": lambda st, claimed: st == "READ_BACK",
            "bad_approve": lambda st, claimed: st == "READ_BACK",
            "decline": lambda st, claimed: st == "READ_BACK",
            "tamper": lambda st, claimed: st == "READ_BACK",
            "expire": lambda st, claimed: st in ("CREATED", "READ_BACK"),
            "settle": lambda st, claimed: st in ("APPROVED", "SUBMITTED"),
        }.get(op, lambda st, claimed: True)
        good = [i for i in self.ids if i in known and fits(*known[i])]
        return self.rng.choice(good or self.ids)

    async def step(self, n: int) -> None:
        op = self.rng.choices(
            ["create", "claim", "wrong_claim", "readback", "challenge", "approve", "bad_approve",
             "decline", "tamper", "expire", "tick", "drop", "settle"],
            weights=[5, 9, 2, 8, 9, 18, 4, 3, 2, 1, 5, 3, 6],
        )[0]  # fmt: skip
        self.log.append(f"{n}:{op}")
        rid = await self.pick(op)
        svc = self.svc
        try:
            async with self.sm() as s:
                if op == "create":
                    made = await svc.create_agent_request(
                        s,
                        BISI,
                        self.rng.choice([1_000, 5_000, 15_000, 30_000, 60_000, 100_000]) * NAIRA,
                    )
                    self.ids.append(made.id)
                    self.codes[made.id] = made.claim_code or "0000"
                elif op == "claim" and rid:
                    await svc.claim(s, AMAKA, self.codes[rid])
                elif op == "wrong_claim":
                    await svc.claim(s, AMAKA, f"{self.rng.randrange(10000):04d}")
                elif op == "readback" and rid:
                    await svc.get_readback(s, AMAKA, rid, self.rng.choice(["pcm", "en"]))
                elif op == "challenge" and rid:
                    options = await svc.issue_challenge(s, AMAKA, rid)
                    self.signed[rid] = self.phone.assert_(
                        options
                    )  # the customer signs what they were asked to
                elif op == "approve" and rid and rid in self.signed:
                    await svc.approve(s, AMAKA, rid, self.signed[rid])
                elif op == "bad_approve" and rid:
                    good = self.signed.get(rid) or {"id": "x", "rawId": "AAAA"}
                    bad = dict(good)
                    if "response" in bad:
                        bad = {**bad, "response": {**bad["response"], "signature": "AAAA"}}
                    await svc.approve(s, AMAKA, rid, bad)
                elif op == "decline" and rid:
                    await svc.decline(s, AMAKA, rid)
                elif op == "tamper" and rid:
                    await svc.demo_tamper(s, rid, self.rng.choice([2_000, 51_000, 99_000]) * NAIRA)
                elif op == "expire" and rid:
                    await svc.demo_expire(s, rid)
                elif op == "tick":
                    self.clock.advance(
                        self.rng.choice([1, 2, 3, 5, 8, 10, 15])
                        if self.rng.random() < 0.93
                        else 130
                    )
                elif op == "drop":
                    self.bank.fail_times = self.bank.calls + self.rng.choice([1, 2])
                elif op == "settle" and rid:
                    await svc.settle(s, rid)
        except ApiError:
            pass  # a refusal is a perfectly good answer; anything else is a bug
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                f"seed {self.seed} step {n} op {op}: unexpected {type(exc).__name__}: {exc}\n{self.log[-12:]}"
            ) from exc

    async def check(self, n: int) -> None:
        where = f"seed {self.seed} step {n}\nlast ops: {self.log[-10:]}"
        async with self.sm() as s:
            balances = dict(
                (
                    await s.execute(select(MockAccount.account_number, MockAccount.balance_kobo))
                ).all()
            )
            reqs = list((await s.execute(select(PaymentRequest))).scalars())
            transfers = list((await s.execute(select(MockTransfer))).scalars())
            used = (
                await s.execute(
                    select(func.count())
                    .select_from(WebAuthnChallenge)
                    .where(
                        WebAuthnChallenge.used_at.is_not(None),
                        WebAuthnChallenge.purpose == "authenticate",
                    )
                )
            ).scalar_one()
        # I1/I2: money is conserved and never negative
        assert sum(balances.values()) == self.initial_total, (
            f"money was created or destroyed\n{where}"
        )
        assert min(balances.values()) >= 0, where
        by_key = {t.idempotency_key: t for t in transfers}
        successes = [t for t in transfers if t.status == "SUCCESS"]
        settled = [r for r in reqs if r.state == "SETTLED"]
        # I3/I4: exactly the settled requests were paid, once each, for exactly their amount
        assert len(successes) == len(settled), f"paid transfers != settled requests\n{where}"
        for r in settled:
            t = by_key.get(r.idempotency_key)
            assert t is not None and t.status == "SUCCESS" and t.amount_kobo == r.amount_kobo, (
                f"settled but not paid exactly once\n{where}"
            )
        assert balances[CUSTOMER_ACCOUNT] == self.initial_customer - sum(
            r.amount_kobo for r in settled
        ), f"customer debit != settled total\n{where}"
        for r in reqs:
            t = by_key.get(r.idempotency_key)
            if r.state in {"CREATED", "READ_BACK", "DECLINED", "EXPIRED", "APPROVED", "SUBMITTED"}:
                assert t is None or t.status != "SUCCESS", f"{r.state} request was paid\n{where}"
            # I5: a finished request never changes again
            if r.id in self.final:
                assert self.final[r.id] == r.state, (
                    f"terminal state {self.final[r.id]} became {r.state}\n{where}"
                )
            if r.state in TERMINAL:
                self.final[r.id] = r.state
            # I6: nothing is signed without a time, and every signature spent exactly one challenge
            if r.state in SIGNED:
                assert r.approved_at is not None, where
            assert r.amount_kobo > 0 and r.amount_kobo % 100 == 0, where
        assert used == sum(1 for r in reqs if r.approved_at is not None), (
            f"challenges used != approvals\n{where}"
        )
        # I8: the caps hold
        assert (
            sum(r.amount_kobo for r in reqs if r.state in SIGNED - {"FAILED"})
            <= self.settings.daily_cap_kobo * 1
        ), f"daily cap broken\n{where}"
        assert all(
            r.amount_kobo <= self.settings.per_payment_cap_kobo
            or r.state in {"READ_BACK", "CREATED", "DECLINED", "EXPIRED"}
            for r in reqs
        ), where

    async def finish(self) -> None:
        # I7: whatever was paid is exactly what the customer heard
        async with self.sm() as s:
            for r in (
                await s.execute(select(PaymentRequest).where(PaymentRequest.state == "SETTLED"))
            ).scalars():
                heard = intent_hash(await self.svc.intent_for(s, r))
                assert r.intent_hash == heard, (
                    f"seed {self.seed}: a settled request no longer matches what was heard"
                )


SEEDS = [1, 7, 42, 2026]
STEPS = 400


@dataclass
class Outcome:
    error: BaseException | None
    states: Counter[str]
    events: Counter[str]


async def run_storm(seed: int, sm: SM, settings: Settings) -> Storm:
    await reset_demo(sm, settings)
    storm = Storm(seed, settings, sm)
    await storm.setup((storm.svc, storm.bank, sm))
    for n in range(STEPS):
        await storm.step(n)
        if n % 5 == 0:
            await storm.check(n)
    await storm.check(STEPS)
    await storm.finish()
    return storm


@pytest.fixture(scope="module")
async def storms(engine: AsyncEngine) -> dict[int, Outcome]:
    """Run each seed once. A broken rule is captured and re-raised by that seed's own test."""
    sm = make_sessionmaker(engine)
    settings = make_settings()
    out: dict[int, Outcome] = {}
    for seed in SEEDS:
        error: BaseException | None = None
        try:
            await run_storm(seed, sm, settings)
        except BaseException as exc:  # noqa: BLE001
            error = exc
        async with sm() as s:
            states = Counter((await s.execute(select(PaymentRequest.state))).scalars())
            events = Counter((await s.execute(select(AuditEvent.event))).scalars())
        out[seed] = Outcome(error, states, events)
    return out


@pytest.mark.parametrize("seed", SEEDS)
def test_random_storms_never_break_the_money_rules(seed: int, storms: dict[int, Outcome]) -> None:
    if storms[seed].error is not None:
        raise storms[seed].error  # type: ignore[misc]


@pytest.mark.parametrize("seed", SEEDS)
def test_each_storm_really_pays_people_and_really_refuses_attacks(
    seed: int, storms: dict[int, Outcome]
) -> None:
    """A storm that never pays anyone proves nothing (the first version did exactly that and this
    test caught it). Every seed must settle payments AND hit refusals the rules exist for."""
    o = storms[seed]
    assert o.states["SETTLED"] >= 2, f"seed {seed} paid {o.states['SETTLED']}: {dict(o.states)}"
    assert o.states["DECLINED"] + o.states["EXPIRED"] >= 1, dict(o.states)
    for needed in ("request.read_back", "transfer.settled"):
        assert o.events[needed] >= 1, f"seed {seed} never produced {needed}: {dict(o.events)}"


def test_across_the_storms_the_rare_defences_are_exercised(storms: dict[int, Outcome]) -> None:
    states: Counter[str] = Counter()
    events: Counter[str] = Counter()
    for o in storms.values():
        states.update(o.states)
        events.update(o.events)
    for defence in (
        "approve.intent_changed",
        "approve.replayed",
        "transfer.pending",
        "demo.tampered",
        "request.expired",
    ):
        assert events[defence] >= 1, f"no storm ever triggered {defence}: {dict(events)}"
    assert states["SETTLED"] >= 10, dict(states)
    print(f"\nstorms: {dict(states)}\nevents: {dict(events)}")
