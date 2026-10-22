"""The demo console: reset, tamper, replay, expire and the timeline."""

import json
import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text

from tests.api.conftest import AMAKA_PHONE, browser, login
from tests.api.test_endpoints import heard, new_request, problem, ready, register_passkey
from tests.conftest import make_settings
from tests.integration.test_consent_engine import NAIRA
from tests.webauthn_software import SoftwareAuthenticator

TOKEN = {"X-Demo-Token": "test-demo-token"}
RID = uuid.uuid4()
ALL_DEMO = [
    ("POST", "/demo/reset"),
    ("POST", f"/demo/requests/{RID}/tamper"),
    ("POST", f"/demo/requests/{RID}/replay"),
    ("POST", f"/demo/requests/{RID}/expire"),
    ("GET", f"/demo/requests/{RID}/timeline"),
]


# ======================================================================= the gate


async def test_the_demo_endpoints_do_not_exist_outside_demo_mode(
    sessionmaker, clock, limiter_clock
) -> None:  # type: ignore[no-untyped-def]
    from tests.api.conftest import build_app

    app = await build_app(
        sessionmaker, make_settings(demo_mode=False, demo_token=""), clock, limiter_clock
    )
    async with browser(app) as c:
        for method, path in ALL_DEMO:
            r = await c.request(method, path, headers=TOKEN)  # even with a "valid" looking token
            assert problem(r) == (404, "NOT_FOUND"), path
        assert not [
            p for p in (await c.get("/openapi.json")).json()["paths"] if p.startswith("/demo")
        ]


@pytest.mark.parametrize("method,path", ALL_DEMO)
async def test_a_token_is_required_on_every_demo_endpoint(
    anonymous: AsyncClient, method: str, path: str
) -> None:
    assert problem(await anonymous.request(method, path)) == (401, "UNAUTHENTICATED")
    assert problem(await anonymous.request(method, path, headers={"X-Demo-Token": "wrong"})) == (
        401,
        "UNAUTHENTICATED",
    )
    assert problem(await anonymous.request(method, path, headers={"X-Demo-Token": ""})) == (
        401,
        "UNAUTHENTICATED",
    )


async def test_the_token_is_accepted_only_as_a_header(anonymous: AsyncClient) -> None:
    assert problem(await anonymous.post("/demo/reset?demo_token=test-demo-token")) == (
        401,
        "UNAUTHENTICATED",
    )
    assert problem(await anonymous.post("/demo/reset?X-Demo-Token=test-demo-token")) == (
        401,
        "UNAUTHENTICATED",
    )
    anonymous.cookies.set("X-Demo-Token", "test-demo-token")
    assert problem(await anonymous.post("/demo/reset")) == (401, "UNAUTHENTICATED")


async def test_a_logged_in_customer_or_agent_is_not_the_demo_operator(
    agent: AsyncClient, customer: AsyncClient
) -> None:
    for who in (agent, customer):
        assert problem(await who.post("/demo/reset")) == (401, "UNAUTHENTICATED")


async def test_wrong_tokens_are_counted_and_lock_the_caller_out(
    anonymous: AsyncClient, limiter_clock
) -> None:  # type: ignore[no-untyped-def]
    for _ in range(10):
        assert (
            problem(await anonymous.post("/demo/reset", headers={"X-Demo-Token": "guess"}))[0]
            == 401
        )
    locked = await anonymous.post("/demo/reset", headers=TOKEN)  # even the RIGHT token now
    assert problem(locked) == (429, "RATE_LIMITED") and int(locked.headers["retry-after"]) >= 290
    limiter_clock.advance(301)
    assert (await anonymous.post("/demo/reset", headers=TOKEN)).status_code == 200


async def test_the_demo_endpoints_are_documented_with_the_token_header() -> None:
    from zolo.api.export_openapi import schema

    paths = schema()["paths"]
    demo = {p: ops for p, ops in paths.items() if p.startswith("/demo")}  # type: ignore[attr-defined]
    assert set(demo) == {"/demo/reset", "/demo/requests/{request_id}/tamper", "/demo/requests/{request_id}/replay",
                         "/demo/requests/{request_id}/expire", "/demo/requests/{request_id}/timeline"}  # fmt: skip
    for ops in demo.values():
        for op in ops.values():
            assert any(
                p["name"] == "x-demo-token" and p["in"] == "header" for p in op["parameters"]
            )


def test_the_phase_2_demo_endpoints_are_not_built() -> None:
    from zolo.api.export_openapi import schema

    joined = " ".join(schema()["paths"])  # type: ignore[arg-type]
    for later in ("/demo/bank/fail", "/demo/voice/cloned", "/demo/card/swap"):
        assert later not in joined


# ======================================================================= reset


async def test_reset_returns_the_demo_to_its_starting_state(
    api: FastAPI,
    agent: AsyncClient,
    customer: AsyncClient,
    anonymous: AsyncClient,
    phone: SoftwareAuthenticator,
    sessionmaker,
) -> None:  # type: ignore[no-untyped-def]
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    await customer.post(
        f"/requests/{made['id']}/approve", json=phone.assert_(options)
    )  # money moves
    r = await anonymous.post("/demo/reset", headers=TOKEN)
    assert r.status_code == 200 and r.json() == {
        "customers": 1,
        "agents": 2,
        "accounts": 7,
        "recipients": 4,
    }
    async with sessionmaker() as s:
        for table in ("payment_requests", "audit_events", "mock_transfers", "webauthn_challenges"):
            assert (await s.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0  # noqa: S608
        balances = dict(
            (await s.execute(text("SELECT account_number, balance_kobo FROM mock_accounts"))).all()
        )
    assert balances["2000000001"] == 250_000 * NAIRA and balances["0123456789"] == 500_000 * NAIRA
    assert problem(await agent.get(f"/requests/{made['id']}")) == (
        404,
        "NOT_FOUND",
    )  # the old request is gone


async def test_the_passkey_on_the_demo_phone_survives_a_reset_and_still_approves(
    agent: AsyncClient, customer: AsyncClient, anonymous: AsyncClient, phone: SoftwareAuthenticator
) -> None:
    await register_passkey(customer, phone)
    assert (await anonymous.post("/demo/reset", headers=TOKEN)).status_code == 200
    # the same sessions, the same passkey, a brand new request: no re-registration needed
    made, options = await ready(agent, customer, phone)
    r = await customer.post(f"/requests/{made['id']}/approve", json=phone.assert_(options))
    assert r.status_code == 200 and r.json()["state"] == "SETTLED"


async def test_reset_forgets_rate_limits_and_captured_assertions(
    api: FastAPI,
    agent: AsyncClient,
    customer: AsyncClient,
    anonymous: AsyncClient,
    phone: SoftwareAuthenticator,
) -> None:
    for _ in range(5):  # lock the customer out of claiming
        await customer.post("/requests/claim", json={"claim_code": "0000"})
    assert problem(await customer.post("/requests/claim", json={"claim_code": "0000"}))[0] == 429
    await register_passkey(customer, phone)
    made, options = await ready_after_reset_unlock(api, agent, customer, phone, anonymous)
    await customer.post(f"/requests/{made['id']}/approve", json=phone.assert_(options))
    demo = api.state.services.demo
    assert demo.last_assertion(uuid.UUID(made["id"])) is not None
    await anonymous.post("/demo/reset", headers=TOKEN)
    assert demo.last_assertion(uuid.UUID(made["id"])) is None
    wrong = await customer.post("/requests/claim", json={"claim_code": "0000"})
    assert wrong.status_code == 404  # not 429: the lock is gone


async def ready_after_reset_unlock(api, agent, customer, phone, anonymous):  # type: ignore[no-untyped-def]
    await anonymous.post("/demo/reset", headers=TOKEN)  # clears the lock so the flow can proceed
    return await ready(agent, customer, phone)


async def test_reset_twice_gives_the_same_world(anonymous: AsyncClient, sessionmaker) -> None:  # type: ignore[no-untyped-def]
    async def snapshot() -> list[object]:
        async with sessionmaker() as s:
            return list(
                (
                    await s.execute(
                        text("SELECT account_number, balance_kobo FROM mock_accounts ORDER BY 1")
                    )
                ).all()
            )

    await anonymous.post("/demo/reset", headers=TOKEN)
    first = await snapshot()
    await anonymous.post("/demo/reset", headers=TOKEN)
    assert await snapshot() == first


# ======================================================================= tamper


async def test_tampering_after_the_readback_makes_approval_fail_and_moves_no_money(
    agent: AsyncClient,
    customer: AsyncClient,
    anonymous: AsyncClient,
    phone: SoftwareAuthenticator,
    sessionmaker,
) -> None:  # type: ignore[no-untyped-def]
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    assertion = phone.assert_(options)  # the customer signed the N15,000 they heard
    t = await anonymous.post(f"/demo/requests/{made['id']}/tamper", headers=TOKEN)
    assert (
        t.status_code == 200
        and t.json()["amount_kobo"] == 5_100_000
        and t.json()["state"] == "READ_BACK"
    )  # N51,000 by default
    r = await customer.post(f"/requests/{made['id']}/approve", json=assertion)
    assert problem(r) == (409, "INTENT_CHANGED")
    assert (await agent.get(f"/requests/{made['id']}")).json()["state"] == "READ_BACK"
    async with sessionmaker() as s:
        assert (await s.execute(text("SELECT count(*) FROM mock_transfers"))).scalar_one() == 0
        assert (
            await s.execute(
                text("SELECT balance_kobo FROM mock_accounts WHERE account_number='2000000001'")
            )
        ).scalar_one() == 250_000 * NAIRA


async def test_a_custom_tamper_amount_and_the_other_ways_it_is_caught(
    agent: AsyncClient, customer: AsyncClient, anonymous: AsyncClient, phone: SoftwareAuthenticator
) -> None:
    await register_passkey(customer, phone)
    made = await heard(agent, customer)
    t = await anonymous.post(
        f"/demo/requests/{made['id']}/tamper", headers=TOKEN, json={"amount_kobo": 20_000 * NAIRA}
    )
    assert t.json()["amount_kobo"] == 20_000 * NAIRA
    # the customer asking for the challenge, or listening again, is told too
    assert problem(await customer.post(f"/requests/{made['id']}/challenge")) == (
        409,
        "INTENT_CHANGED",
    )
    assert problem(await customer.get(f"/requests/{made['id']}/readback")) == (
        409,
        "INTENT_CHANGED",
    )


@pytest.mark.parametrize(
    "body,status",
    [
        ({"amount_kobo": 0}, 422),
        ({"amount_kobo": -5}, 422),
        ({"amount_kobo": 150}, 422),
        ({"amount_kobo": "lots"}, 422),
    ],
)
async def test_tamper_rejects_nonsense_amounts(
    agent: AsyncClient, customer: AsyncClient, anonymous: AsyncClient, body: dict, status: int
) -> None:  # type: ignore[type-arg]
    made = await heard(agent, customer)
    assert (
        await anonymous.post(f"/demo/requests/{made['id']}/tamper", headers=TOKEN, json=body)
    ).status_code == status


async def test_tamper_only_applies_after_the_readback(
    agent: AsyncClient, customer: AsyncClient, anonymous: AsyncClient
) -> None:
    created = await new_request(agent)  # CREATED, not yet read back
    assert problem(
        await anonymous.post(f"/demo/requests/{created['id']}/tamper", headers=TOKEN)
    ) == (409, "STATE_CONFLICT")
    await customer.post("/requests/claim", json={"claim_code": created["claim_code"]})
    await customer.post(f"/requests/{created['id']}/decline")  # still not READ_BACK
    assert problem(
        await anonymous.post(f"/demo/requests/{uuid.uuid4()}/tamper", headers=TOKEN)
    ) == (404, "NOT_FOUND")


# ======================================================================= replay


async def test_replaying_the_last_approval_is_already_used_and_pays_nothing_more(
    agent: AsyncClient,
    customer: AsyncClient,
    anonymous: AsyncClient,
    phone: SoftwareAuthenticator,
    sessionmaker,
) -> None:  # type: ignore[no-untyped-def]
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    assert (
        await customer.post(f"/requests/{made['id']}/approve", json=phone.assert_(options))
    ).json()["state"] == "SETTLED"
    r = await anonymous.post(f"/demo/requests/{made['id']}/replay", headers=TOKEN)
    assert problem(r) == (409, "ALREADY_USED")
    async with sessionmaker() as s:
        assert (await s.execute(text("SELECT count(*) FROM mock_transfers"))).scalar_one() == 1
        assert (
            await s.execute(
                text("SELECT balance_kobo FROM mock_accounts WHERE account_number='2000000001'")
            )
        ).scalar_one() == 235_000 * NAIRA
    assert (await agent.get(f"/requests/{made['id']}")).json()["state"] == "SETTLED"  # unchanged


async def test_there_is_nothing_to_replay_before_an_approval(
    agent: AsyncClient, customer: AsyncClient, anonymous: AsyncClient, phone: SoftwareAuthenticator
) -> None:
    await register_passkey(customer, phone)
    made, _ = await ready(agent, customer, phone)
    assert problem(await anonymous.post(f"/demo/requests/{made['id']}/replay", headers=TOKEN)) == (
        409,
        "STATE_CONFLICT",
    )
    assert problem(await anonymous.post(f"/demo/requests/{uuid.uuid4()}/replay", headers=TOKEN))[
        0
    ] in (404, 409)


async def test_a_refused_approval_is_not_what_gets_replayed(
    agent: AsyncClient, customer: AsyncClient, anonymous: AsyncClient, phone: SoftwareAuthenticator
) -> None:
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    await customer.post(
        f"/requests/{made['id']}/approve", json=phone.assert_(options, corrupt_signature=True)
    )
    assert problem(await anonymous.post(f"/demo/requests/{made['id']}/replay", headers=TOKEN)) == (
        409,
        "STATE_CONFLICT",
    )


# ======================================================================= expire


async def test_expiring_a_request_makes_everything_after_it_410(
    agent: AsyncClient,
    customer: AsyncClient,
    anonymous: AsyncClient,
    phone: SoftwareAuthenticator,
    sessionmaker,
) -> None:  # type: ignore[no-untyped-def]
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    assertion = phone.assert_(options)
    e = await anonymous.post(f"/demo/requests/{made['id']}/expire", headers=TOKEN)
    assert e.status_code == 200
    assert problem(await customer.post(f"/requests/{made['id']}/approve", json=assertion)) == (
        410,
        "REQUEST_EXPIRED",
    )
    assert (await agent.get(f"/requests/{made['id']}")).json()["state"] == "EXPIRED"
    async with sessionmaker() as s:
        assert (await s.execute(text("SELECT count(*) FROM mock_transfers"))).scalar_one() == 0


async def test_an_unclaimed_request_that_is_expired_answers_410_to_a_claim(
    agent: AsyncClient, customer: AsyncClient, anonymous: AsyncClient
) -> None:
    made = await new_request(agent)
    await anonymous.post(f"/demo/requests/{made['id']}/expire", headers=TOKEN)
    assert problem(
        await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
    ) == (410, "REQUEST_EXPIRED")


async def test_only_a_live_request_can_be_expired(
    agent: AsyncClient, customer: AsyncClient, anonymous: AsyncClient
) -> None:
    made = await heard(agent, customer)
    await customer.post(f"/requests/{made['id']}/decline")
    assert problem(await anonymous.post(f"/demo/requests/{made['id']}/expire", headers=TOKEN)) == (
        409,
        "STATE_CONFLICT",
    )
    assert problem(
        await anonymous.post(f"/demo/requests/{uuid.uuid4()}/expire", headers=TOKEN)
    ) == (404, "NOT_FOUND")


# ======================================================================= timeline


async def test_the_timeline_tells_the_whole_story_in_order(
    agent: AsyncClient, customer: AsyncClient, anonymous: AsyncClient, phone: SoftwareAuthenticator
) -> None:
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    await customer.post(
        f"/requests/{made['id']}/approve",
        json=phone.assert_(options, origin="https://evil.example"),
    )
    await anonymous.post(f"/demo/requests/{made['id']}/tamper", headers=TOKEN)
    await customer.post(f"/requests/{made['id']}/approve", json=phone.assert_(options))
    body = (await anonymous.get(f"/demo/requests/{made['id']}/timeline", headers=TOKEN)).json()
    assert [e["event"] for e in body["events"]] == [
        "request.created", "request.claimed", "request.read_back", "challenge.issued",
        "approve.signature_invalid", "demo.tampered", "approve.intent_changed",
    ]  # fmt: skip
    ids = [e["id"] for e in body["events"]]
    assert ids == sorted(ids)
    assert body["request"]["state"] == "READ_BACK" and body["request"]["amount_kobo"] == 5_100_000
    sig = body["events"][4]
    assert sig["details"] == {
        "code": "SIGNATURE_INVALID",
        "reason": "wrong_origin",
    }  # internal reason: demo console only
    assert body["events"][5]["details"] == {"changed": "amount"}  # that it changed, never to what


async def test_the_timeline_of_a_full_cash_out_and_a_replay(
    agent: AsyncClient, customer: AsyncClient, anonymous: AsyncClient, phone: SoftwareAuthenticator
) -> None:
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    await customer.post(f"/requests/{made['id']}/approve", json=phone.assert_(options))
    await anonymous.post(f"/demo/requests/{made['id']}/replay", headers=TOKEN)
    events = [
        e["event"]
        for e in (
            await anonymous.get(f"/demo/requests/{made['id']}/timeline", headers=TOKEN)
        ).json()["events"]
    ]
    assert events == [
        "request.created", "request.claimed", "request.read_back", "challenge.issued", "request.approved",
        "transfer.submitted", "transfer.settled", "approve.replayed",
    ]  # fmt: skip


async def test_timeline_events_hold_no_personal_data(
    agent: AsyncClient, customer: AsyncClient, anonymous: AsyncClient, phone: SoftwareAuthenticator
) -> None:
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    await customer.post(f"/requests/{made['id']}/approve", json=phone.assert_(options))
    events = (await anonymous.get(f"/demo/requests/{made['id']}/timeline", headers=TOKEN)).json()[
        "events"
    ]
    dump = json.dumps(events)
    for private in (
        "BISI",
        "Bisi",
        "Amaka",
        "0123456789",
        "2000000001",
        "1500000",
        "+234",
        made["claim_code"] + '"',
    ):
        assert private not in dump, private


async def test_the_timeline_applies_lazy_expiry_and_404s_for_unknown_requests(
    agent: AsyncClient, customer: AsyncClient, anonymous: AsyncClient, clock
) -> None:  # type: ignore[no-untyped-def]
    made = await heard(agent, customer)
    clock.advance(130)
    body = (await anonymous.get(f"/demo/requests/{made['id']}/timeline", headers=TOKEN)).json()
    assert (
        body["request"]["state"] == "EXPIRED" and body["events"][-1]["event"] == "request.expired"
    )
    assert problem(
        await anonymous.get(f"/demo/requests/{uuid.uuid4()}/timeline", headers=TOKEN)
    ) == (404, "NOT_FOUND")


# ======================================================================= boundaries


def test_the_demo_router_never_touches_a_table_itself() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "zolo" / "api" / "routes_demo.py").read_text()
    for forbidden in (
        "PaymentRequest",
        "apply_transition",
        ".transfer(",
        "update(",
        "delete(",
        "consent.models",
    ):
        assert forbidden not in source, forbidden


async def test_a_logged_in_customer_still_works_after_a_reset(
    customer: AsyncClient, anonymous: AsyncClient
) -> None:
    await anonymous.post("/demo/reset", headers=TOKEN)
    assert (await customer.get("/me/activity")).json() == {"items": []}
    assert AMAKA_PHONE and login is not None


# ======================================================================= defence in depth: every layer refuses on its own


async def test_even_if_the_demo_router_were_mounted_by_mistake_the_gate_refuses(
    sessionmaker, clock, limiter_clock
) -> None:  # type: ignore[no-untyped-def]
    from tests.api.conftest import build_app
    from zolo.api import routes_demo

    app = await build_app(
        sessionmaker, make_settings(demo_mode=False, demo_token=""), clock, limiter_clock
    )
    app.include_router(routes_demo.router)  # someone mounts it by mistake
    async with browser(app) as c:
        for method, path in ALL_DEMO:
            r = await c.request(method, path, headers={"X-Demo-Token": "anything-at-all"})
            assert problem(r) == (404, "NOT_FOUND"), (
                path
            )  # not 401: the answer does not depend on the token


async def test_even_past_the_gate_the_consent_service_refuses_outside_demo_mode(
    sessionmaker, clock
) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import select

    from tests.integration.test_consent_engine import Flaky, StubAudio
    from zolo.bank.mock import Latency, MockBankAdapter
    from zolo.consent.models import PaymentRequest
    from zolo.consent.service import ConsentService
    from zolo.core.errors import ApiError
    from zolo.demo import seed_data as seed
    from zolo.demo.seed import reset_demo

    settings = make_settings(demo_mode=False, demo_token="")
    await reset_demo(sessionmaker, settings)
    svc = ConsentService(
        settings,
        Flaky(MockBankAdapter(sessionmaker, latency=Latency(0, 0))),
        audio=StubAudio(),
        clock=clock,
    )  # type: ignore[arg-type]
    async with sessionmaker() as s:  # a REAL request, read back: every demo action would work on it
        made = await svc.create_agent_request(s, seed.BISI.id, 15_000 * NAIRA)
    async with sessionmaker() as s:
        await svc.claim(s, seed.AMAKA.id, made.claim_code)  # type: ignore[arg-type]
    async with sessionmaker() as s:
        await svc.get_readback(s, seed.AMAKA.id, made.id, "pcm")

    async def snapshot() -> tuple[object, ...]:
        async with sessionmaker() as s:
            r = (
                await s.execute(select(PaymentRequest).where(PaymentRequest.id == made.id))
            ).scalar_one()
            return (r.state, r.amount_kobo, r.expires_at, r.intent_hash)

    before = await snapshot()
    calls = [
        lambda s: svc.demo_tamper(s, made.id, 5_100_000),
        lambda s: svc.demo_expire(s, made.id),
        lambda s: svc.demo_replay(s, made.id, {"id": "x"}),
        lambda s: svc.demo_timeline(s, made.id),
    ]
    for call in calls:
        async with sessionmaker() as s:
            with pytest.raises(ApiError) as exc:
                await call(s)
        assert (exc.value.status, exc.value.code.value) == (404, "NOT_FOUND")
    assert await snapshot() == before  # and it changed nothing
