"""The Phase 1 API over HTTP: every endpoint, every error code, the whole cash-out."""

import json
import logging
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, update

from tests.api.conftest import AMAKA_PHONE, BISI_PHONE, MAMA_PHONE, browser, login
from tests.integration.test_consent_engine import NAIRA
from tests.webauthn_software import SoftwareAuthenticator
from zolo.consent.models import PaymentRequest
from zolo.passkeys.models import PasskeyCredential

PROBLEM_KEYS = {"type", "title", "status", "code", "detail"}


def problem(r: Any) -> tuple[int, str]:
    assert r.headers["content-type"].startswith("application/problem+json"), r.text
    body = r.json()
    assert set(body) == PROBLEM_KEYS
    return r.status_code, body["code"]


async def register_passkey(customer: AsyncClient, phone: SoftwareAuthenticator) -> None:
    options = (await customer.post("/passkeys/register/options")).json()
    r = await customer.post(
        "/passkeys/register/verify",
        json={"credential": phone.register(options), "device_label": "test phone"},
    )
    assert r.status_code == 201, r.text


async def new_request(agent: AsyncClient, naira: int = 15_000) -> dict[str, Any]:
    r = await agent.post("/agent/requests", json={"amount_kobo": naira * NAIRA})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def heard(agent: AsyncClient, customer: AsyncClient, naira: int = 15_000) -> dict[str, Any]:
    made = await new_request(agent, naira)
    assert (
        await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
    ).status_code == 200
    assert (await customer.get(f"/requests/{made['id']}/readback?lang=pcm")).status_code == 200
    return made


async def ready(
    agent: AsyncClient, customer: AsyncClient, phone: SoftwareAuthenticator, naira: int = 15_000
):  # type: ignore[no-untyped-def]
    made = await heard(agent, customer, naira)
    options = (await customer.post(f"/requests/{made['id']}/challenge")).json()
    return made, options


# ======================================================================= mock login and sessions


async def test_mock_login_signs_in_a_customer_and_an_agent(api: FastAPI) -> None:
    async with browser(api) as c:
        r = await c.post("/auth/mock-login", json={"phone": AMAKA_PHONE, "otp": "123456"})
        assert (
            r.status_code == 200
            and r.json()["role"] == "customer"
            and r.json()["display_name"] == "Amaka Obi"
        )
    async with browser(api) as c:
        r = await c.post("/auth/mock-login", json={"phone": BISI_PHONE, "otp": "123456"})
        assert r.json()["role"] == "agent" and r.json()["display_name"] == "Bisi Ventures"


async def test_the_session_cookie_is_httponly_samesite_lax_and_twelve_hours(api: FastAPI) -> None:
    async with browser(api) as c:
        r = await c.post("/auth/mock-login", json={"phone": AMAKA_PHONE, "otp": "123456"})
    cookie = r.headers["set-cookie"].lower()
    assert "zolo_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "max-age=43200" in cookie and "path=/" in cookie


async def test_the_cookie_is_secure_when_cookie_secure_is_on(
    sessionmaker, clock, limiter_clock
) -> None:  # type: ignore[no-untyped-def]
    from tests.api.conftest import build_app
    from tests.conftest import make_settings

    app = await build_app(sessionmaker, make_settings(cookie_secure=True), clock, limiter_clock)
    async with browser(app) as c:
        r = await c.post("/auth/mock-login", json={"phone": AMAKA_PHONE, "otp": "123456"})
    assert "secure" in r.headers["set-cookie"].lower()


@pytest.mark.parametrize(
    "body",
    [
        {"phone": AMAKA_PHONE, "otp": "000000"},  # wrong code
        {"phone": "+2349999999999", "otp": "123456"},  # unknown phone
    ],
)
async def test_a_wrong_code_and_an_unknown_phone_get_the_same_answer(
    anonymous: AsyncClient, body: dict[str, str]
) -> None:
    r = await anonymous.post("/auth/mock-login", json=body)
    assert (
        problem(r) == (401, "UNAUTHENTICATED")
        and r.json()["title"] == "Invalid phone number or code"
    )
    assert "set-cookie" not in r.headers


async def test_login_is_rate_limited_with_retry_after(
    anonymous: AsyncClient, limiter_clock
) -> None:  # type: ignore[no-untyped-def]
    for _ in range(10):
        assert (
            await anonymous.post("/auth/mock-login", json={"phone": AMAKA_PHONE, "otp": "000000"})
        ).status_code == 401
    r = await anonymous.post(
        "/auth/mock-login", json={"phone": AMAKA_PHONE, "otp": "123456"}
    )  # even the right code
    assert problem(r) == (429, "RATE_LIMITED") and int(r.headers["retry-after"]) >= 1
    limiter_clock.advance(61)
    assert (
        await anonymous.post("/auth/mock-login", json={"phone": AMAKA_PHONE, "otp": "123456"})
    ).status_code == 200


async def test_login_limit_is_per_phone_too(api: FastAPI) -> None:
    for _ in range(
        10
    ):  # ten attempts on one phone from ten "different browsers" still hit the phone limit
        async with browser(api) as c:
            await c.post("/auth/mock-login", json={"phone": AMAKA_PHONE, "otp": "000000"})
    async with browser(api) as c:
        r = await c.post("/auth/mock-login", json={"phone": AMAKA_PHONE, "otp": "123456"})
    assert r.status_code == 429


async def test_mock_login_does_not_exist_outside_demo_mode(
    sessionmaker, clock, limiter_clock
) -> None:  # type: ignore[no-untyped-def]
    from tests.api.conftest import build_app
    from tests.conftest import make_settings

    app = await build_app(
        sessionmaker, make_settings(demo_mode=False, demo_token=""), clock, limiter_clock
    )
    async with browser(app) as c:
        for method, path in (("POST", "/auth/mock-login"), ("GET", "/dev/passkey-test")):
            r = await c.request(
                method,
                path,
                json={"phone": AMAKA_PHONE, "otp": "123456"} if method == "POST" else None,
            )
            assert problem(r) == (404, "NOT_FOUND")
        assert "/auth/mock-login" not in (await c.get("/openapi.json")).json()["paths"]
        assert (await c.get("/healthz")).status_code == 200


async def test_even_if_the_login_router_were_mounted_the_handler_refuses_without_demo_mode(
    sessionmaker, clock, limiter_clock
) -> None:  # type: ignore[no-untyped-def]
    from tests.api.conftest import build_app
    from tests.conftest import make_settings
    from zolo.api import routes_auth

    app = await build_app(
        sessionmaker, make_settings(demo_mode=False, demo_token=""), clock, limiter_clock
    )
    app.include_router(routes_auth.router)  # someone mounts it by mistake
    async with browser(app) as c:
        r = await c.post("/auth/mock-login", json={"phone": AMAKA_PHONE, "otp": "123456"})
    assert problem(r) == (404, "NOT_FOUND") and "set-cookie" not in r.headers


def test_demo_mode_cannot_be_switched_on_without_a_real_token() -> None:
    from tests.conftest import make_settings

    for token in ("", "short"):
        with pytest.raises(ValueError, match="DEMO_TOKEN"):
            make_settings(demo_mode=True, demo_token=token)
    assert make_settings(demo_mode=False, demo_token="").demo_mode is False


async def test_a_forged_or_foreign_cookie_is_no_session(api: FastAPI, agent: AsyncClient) -> None:
    from zolo.core.security import SessionCodec

    forged = SessionCodec("some-other-secret-0123456789-abcdef", 43200).dumps(
        "customer", uuid.uuid4()
    )
    async with browser(api) as c:
        c.cookies.set("zolo_session", forged)
        assert problem(await c.get("/me/activity")) == (401, "UNAUTHENTICATED")
        c.cookies.set("zolo_session", "not-a-token")
        assert problem(await c.get("/me/activity")) == (401, "UNAUTHENTICATED")


async def test_an_old_session_expires(
    api: FastAPI, customer: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    assert (await customer.get("/me/activity")).status_code == 200
    real = time.time()
    monkeypatch.setattr("itsdangerous.timed.time.time", lambda: real + 13 * 3600)
    assert problem(await customer.get("/me/activity")) == (401, "UNAUTHENTICATED")


PROTECTED = [
    ("POST", "/passkeys/register/options"), ("POST", "/passkeys/register/verify"),
    ("POST", "/agent/requests"), ("POST", "/requests/claim"),
    ("GET", f"/requests/{uuid.uuid4()}/readback"), ("POST", f"/requests/{uuid.uuid4()}/challenge"),
    ("POST", f"/requests/{uuid.uuid4()}/approve"), ("POST", f"/requests/{uuid.uuid4()}/decline"),
    ("GET", f"/requests/{uuid.uuid4()}"), ("GET", "/me/activity"),
]  # fmt: skip


@pytest.mark.parametrize("method,path", PROTECTED)
async def test_every_protected_endpoint_needs_a_login(
    anonymous: AsyncClient, method: str, path: str
) -> None:
    r = await anonymous.request(method, path, json={})
    assert problem(r) == (401, "UNAUTHENTICATED")


@pytest.mark.parametrize("who,method,path", [
    ("customer", "POST", "/agent/requests"),
    ("agent", "POST", "/requests/claim"),
    ("agent", "GET", f"/requests/{uuid.uuid4()}/readback"),
    ("agent", "POST", f"/requests/{uuid.uuid4()}/approve"),
    ("agent", "POST", "/passkeys/register/options"),
    ("agent", "GET", "/me/activity"),
])  # fmt: skip
async def test_the_wrong_role_is_forbidden(
    agent: AsyncClient, customer: AsyncClient, who: str, method: str, path: str
) -> None:
    client = agent if who == "agent" else customer
    assert problem(
        await client.request(method, path, json={"amount_kobo": 100, "claim_code": "1234"})
    ) == (403, "FORBIDDEN")


# ======================================================================= errors


async def test_validation_errors_name_the_field_but_never_echo_the_value(
    agent: AsyncClient,
) -> None:
    r = await agent.post("/agent/requests", json={"amount_kobo": "fifteen thousand SECRET-VALUE"})
    assert problem(r) == (422, "VALIDATION_ERROR")
    assert "amount_kobo" in r.json()["detail"] and "SECRET-VALUE" not in r.text
    assert problem(await agent.get("/requests/not-a-uuid")) == (422, "VALIDATION_ERROR")


async def test_an_unexpected_failure_is_a_generic_500_with_the_request_id_logged(
    api: FastAPI,
    agent: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def boom(*a: Any, **k: Any) -> None:
        raise RuntimeError("secret database detail 0123456789")

    monkeypatch.setattr(api.state.services.consent, "create_agent_request", boom)
    with caplog.at_level(logging.ERROR):
        r = await agent.post(
            "/agent/requests",
            json={"amount_kobo": 100_00},
            headers={"X-Request-Id": "trace-me-1234"},
        )
    assert (
        problem(r) == (500, "INTERNAL_ERROR")
        and "secret" not in r.text
        and "0123456789" not in r.text
    )
    assert r.headers["x-request-id"] == "trace-me-1234"
    record = next(rec for rec in caplog.records if rec.name == "zolo.api")
    assert record.error_type == "RuntimeError"  # type: ignore[attr-defined]
    assert "secret" not in record.getMessage() and "0123456789" not in str(record.__dict__)


# ======================================================================= create


async def test_an_agent_creates_a_request_and_gets_exactly_the_prd_fields(
    agent: AsyncClient,
) -> None:
    r = await agent.post("/agent/requests", json={"amount_kobo": 1_500_000})
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "claim_code", "qr_payload", "expires_at", "payee_name"}
    assert len(body["claim_code"]) == 4 and body["payee_name"] == "BISI VENTURES"
    assert body["qr_payload"] == f"http://localhost:3000/claim?code={body['claim_code']}"


async def test_over_the_cap_is_limit_exceeded(agent: AsyncClient) -> None:
    assert (
        await agent.post("/agent/requests", json={"amount_kobo": 100_000 * NAIRA})
    ).status_code == 201
    assert problem(await agent.post("/agent/requests", json={"amount_kobo": 100_001 * NAIRA})) == (
        422,
        "LIMIT_EXCEEDED",
    )
    for bad in (0, -5, 1_500_050):
        assert problem(await agent.post("/agent/requests", json={"amount_kobo": bad}))[0] == 422


async def test_the_idempotency_key_header_makes_a_retry_safe(agent: AsyncClient) -> None:
    key = str(uuid.uuid4())
    a = await agent.post(
        "/agent/requests", json={"amount_kobo": 1_500_000}, headers={"Idempotency-Key": key}
    )
    b = await agent.post(
        "/agent/requests", json={"amount_kobo": 1_500_000}, headers={"Idempotency-Key": key}
    )
    assert a.json()["id"] == b.json()["id"] and a.json()["claim_code"] == b.json()["claim_code"]
    other = await agent.post(
        "/agent/requests", json={"amount_kobo": 9_000_00}, headers={"Idempotency-Key": key}
    )
    assert problem(other) == (409, "STATE_CONFLICT")
    assert problem(
        await agent.post(
            "/agent/requests", json={"amount_kobo": 100_00}, headers={"Idempotency-Key": "nope"}
        )
    ) == (422, "VALIDATION_ERROR")


async def test_creating_requests_is_rate_limited(agent: AsyncClient, limiter_clock) -> None:  # type: ignore[no-untyped-def]
    for _ in range(10):
        assert (
            await agent.post("/agent/requests", json={"amount_kobo": 100_00})
        ).status_code == 201
    r = await agent.post("/agent/requests", json={"amount_kobo": 100_00})
    assert problem(r) == (429, "RATE_LIMITED") and "retry-after" in r.headers
    limiter_clock.advance(61)
    assert (await agent.post("/agent/requests", json={"amount_kobo": 100_00})).status_code == 201


# ======================================================================= claim


async def test_claim_by_code_and_by_qr_payload(agent: AsyncClient, customer: AsyncClient) -> None:
    a = await new_request(agent)
    r = await customer.post("/requests/claim", json={"claim_code": a["claim_code"]})
    assert r.status_code == 200 and r.json()["id"] == a["id"] and r.json()["claimed"] is True
    b = await new_request(agent)
    r = await customer.post("/requests/claim", json={"qr_payload": b["qr_payload"]})
    assert r.status_code == 200 and r.json()["id"] == b["id"]


@pytest.mark.parametrize("body", [
    {}, {"claim_code": "12"}, {"claim_code": "12345"}, {"claim_code": "abcd"},
    {"claim_code": "1234", "qr_payload": "x"}, {"qr_payload": "http://x/claim"}, {"qr_payload": "http://x/claim?code=12"},
])  # fmt: skip
async def test_malformed_claims_are_422(customer: AsyncClient, body: dict[str, str]) -> None:
    assert problem(await customer.post("/requests/claim", json=body)) == (422, "VALIDATION_ERROR")


async def test_a_wrong_code_is_404_and_an_expired_one_is_410(
    agent: AsyncClient, customer: AsyncClient, clock
) -> None:  # type: ignore[no-untyped-def]
    made = await new_request(agent)
    wrong = "0000" if made["claim_code"] != "0000" else "1111"
    assert problem(await customer.post("/requests/claim", json={"claim_code": wrong})) == (
        404,
        "CODE_NOT_FOUND",
    )
    clock.advance(121)
    assert problem(
        await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
    ) == (410, "REQUEST_EXPIRED")


async def test_five_wrong_codes_lock_the_customer_for_five_minutes(
    api: FastAPI, agent: AsyncClient, customer: AsyncClient, limiter_clock
) -> None:  # type: ignore[no-untyped-def]
    made = await new_request(agent)
    wrong = "0000" if made["claim_code"] != "0000" else "1111"
    for _ in range(5):
        assert (
            problem(await customer.post("/requests/claim", json={"claim_code": wrong}))[1]
            == "CODE_NOT_FOUND"
        )
    locked = await customer.post(
        "/requests/claim", json={"claim_code": made["claim_code"]}
    )  # even the RIGHT code
    assert (
        problem(locked) == (429, "RATE_LIMITED")
        and 290 <= int(locked.headers["retry-after"]) <= 300
    )
    # logging in again does not clear it: the lock belongs to the customer, not the session
    async with browser(api) as fresh:
        await login(fresh, AMAKA_PHONE)
        assert (
            problem(await fresh.post("/requests/claim", json={"claim_code": made["claim_code"]}))[0]
            == 429
        )
    limiter_clock.advance(301)
    assert (
        await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
    ).status_code == 200


async def test_claims_are_limited_to_five_attempts_a_minute(
    agent: AsyncClient, customer: AsyncClient, limiter_clock
) -> None:  # type: ignore[no-untyped-def]
    made = await new_request(agent)
    for _ in range(5):
        assert (
            await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
        ).status_code == 200
    assert (
        problem(await customer.post("/requests/claim", json={"claim_code": made["claim_code"]}))[0]
        == 429
    )
    limiter_clock.advance(61)
    assert (
        await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
    ).status_code == 200


async def test_a_successful_claim_clears_the_wrong_tries(
    agent: AsyncClient, customer: AsyncClient, limiter_clock
) -> None:  # type: ignore[no-untyped-def]
    made = await new_request(agent)
    wrong = "0000" if made["claim_code"] != "0000" else "1111"
    for _ in range(4):
        await customer.post("/requests/claim", json={"claim_code": wrong})
    assert (
        await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
    ).status_code == 200
    limiter_clock.advance(61)
    for _ in range(4):  # four more wrong ones: still not locked, the count started over
        assert (
            problem(await customer.post("/requests/claim", json={"claim_code": wrong}))[1]
            == "CODE_NOT_FOUND"
        )


# ======================================================================= readback


async def test_the_readback_in_pidgin_and_english(
    agent: AsyncClient, customer: AsyncClient
) -> None:
    made = await new_request(agent)
    await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
    r = await customer.get(f"/requests/{made['id']}/readback")  # pcm is the default
    body = r.json()
    assert (
        body["text"]
        == "Bisi Ventures dey ask for fifteen thousand naira. One five, zero zero zero. You wan approve?"
    )
    assert {k: body[k] for k in ("lang", "amount_words", "payee_name", "amount_kobo")} == {
        "lang": "pcm", "amount_words": "fifteen thousand", "payee_name": "Bisi Ventures", "amount_kobo": 1_500_000,
    }  # fmt: skip
    assert body["audio_url"].startswith("/voice/audio/") and "expires_at" in body
    en = (await customer.get(f"/requests/{made['id']}/readback?lang=en")).json()
    assert en["text"].startswith("Bisi Ventures is asking for fifteen thousand naira")


async def test_unsupported_languages_and_other_peoples_requests(
    agent: AsyncClient, customer: AsyncClient, api: FastAPI
) -> None:
    made = await new_request(agent)
    await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
    assert problem(await customer.get(f"/requests/{made['id']}/readback?lang=yo")) == (
        422,
        "VALIDATION_ERROR",
    )
    assert problem(await customer.get(f"/requests/{uuid.uuid4()}/readback")) == (404, "NOT_FOUND")


# ======================================================================= passkeys and the cash-out


async def test_registering_a_passkey_over_http(
    customer: AsyncClient, phone: SoftwareAuthenticator, sessionmaker
) -> None:  # type: ignore[no-untyped-def]
    r = await customer.post("/passkeys/register/options")
    assert r.status_code == 200 and r.json()["rp"] == {"name": "Zolo", "id": "localhost"}
    v = await customer.post(
        "/passkeys/register/verify",
        json={"credential": phone.register(r.json()), "device_label": "demo phone"},
    )
    assert v.status_code == 201 and set(v.json()) == {"id", "device_label", "replaced_previous"}
    async with sessionmaker() as s:
        assert (
            await s.execute(select(PasskeyCredential))
        ).scalar_one().device_label == "demo phone"


async def test_a_bad_registration_is_a_clean_400(
    customer: AsyncClient, phone: SoftwareAuthenticator
) -> None:
    options = (await customer.post("/passkeys/register/options")).json()
    bad = phone.register(options, origin="https://evil.example")
    r = await customer.post("/passkeys/register/verify", json={"credential": bad})
    assert problem(r) == (400, "PASSKEY_REGISTRATION_FAILED") and "evil.example" not in r.text
    assert problem(await customer.post("/passkeys/register/verify", json={"credential": {}}))[
        0
    ] in (400, 409)


async def test_the_challenge_needs_a_passkey_and_carries_the_intent_hash(
    agent: AsyncClient, customer: AsyncClient, phone: SoftwareAuthenticator, sessionmaker
) -> None:  # type: ignore[no-untyped-def]
    from webauthn.helpers import base64url_to_bytes

    made = await heard(agent, customer)
    assert problem(await customer.post(f"/requests/{made['id']}/challenge")) == (409, "NO_PASSKEY")
    await register_passkey(customer, phone)
    options = (await customer.post(f"/requests/{made['id']}/challenge")).json()
    async with sessionmaker() as s:
        row = (
            await s.execute(
                select(PaymentRequest).where(PaymentRequest.id == uuid.UUID(made["id"]))
            )
        ).scalar_one()
    assert base64url_to_bytes(options["challenge"]) == row.intent_hash
    assert options["userVerification"] == "required"


async def test_the_whole_cash_out_over_http(
    agent: AsyncClient, customer: AsyncClient, phone: SoftwareAuthenticator, sessionmaker
) -> None:  # type: ignore[no-untyped-def]
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    assert (await agent.get(f"/requests/{made['id']}")).json()[
        "state"
    ] == "READ_BACK"  # the agent watches
    r = await customer.post(f"/requests/{made['id']}/approve", json=phone.assert_(options))
    assert r.status_code == 200
    body = r.json()
    assert (
        body["state"] == "SETTLED"
        and body["bank_reference"].startswith("MOCK-")
        and body["amount_kobo"] == 1_500_000
    )
    paid = (await agent.get(f"/requests/{made['id']}")).json()  # the agent sees Paid
    assert paid["state"] == "SETTLED" and paid["amount_kobo"] == 1_500_000
    from sqlalchemy import text

    async with sessionmaker() as s:
        balances = dict(
            (await s.execute(text("SELECT account_number, balance_kobo FROM mock_accounts"))).all()
        )
    assert balances["2000000001"] == 235_000 * NAIRA and balances["0123456789"] == 515_000 * NAIRA
    lines = (await customer.get("/me/activity")).json()["items"]
    assert lines[0]["line"] == "Paid ₦15,000 to Bisi Ventures"


async def test_tamper_replay_and_decline_over_http(
    agent: AsyncClient, customer: AsyncClient, phone: SoftwareAuthenticator, sessionmaker
) -> None:  # type: ignore[no-untyped-def]
    await register_passkey(customer, phone)
    # tamper: the amount changes after the customer heard it
    made, options = await ready(agent, customer, phone)
    assertion = phone.assert_(options)
    async with sessionmaker() as s:
        await s.execute(
            update(PaymentRequest)
            .where(PaymentRequest.id == uuid.UUID(made["id"]))
            .values(amount_kobo=5_100_000)
        )
        await s.commit()
    assert problem(await customer.post(f"/requests/{made['id']}/approve", json=assertion)) == (
        409,
        "INTENT_CHANGED",
    )
    # replay: approve one honestly, then send the same assertion again
    made2, options2 = await ready(agent, customer, phone, 5_000)
    good = phone.assert_(options2)
    assert (await customer.post(f"/requests/{made2['id']}/approve", json=good)).json()[
        "state"
    ] == "SETTLED"
    assert problem(await customer.post(f"/requests/{made2['id']}/approve", json=good)) == (
        409,
        "ALREADY_USED",
    )
    # decline
    made3 = await heard(agent, customer, 3_000)
    d = await customer.post(f"/requests/{made3['id']}/decline")
    assert d.status_code == 200 and d.json()["state"] == "DECLINED"
    assert (await agent.get(f"/requests/{made3['id']}")).json()["state"] == "DECLINED"


async def test_an_unreadable_request_cannot_be_declined_and_a_stranger_cannot_see_it(
    api: FastAPI, agent: AsyncClient, customer: AsyncClient
) -> None:
    made = await new_request(agent)
    await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
    assert problem(await customer.post(f"/requests/{made['id']}/decline")) == (
        409,
        "STATE_CONFLICT",
    )  # not read back yet
    async with browser(api) as other_agent:
        await login(other_agent, MAMA_PHONE)
        assert problem(await other_agent.get(f"/requests/{made['id']}")) == (404, "NOT_FOUND")


async def test_an_expired_request_reads_as_expired(
    agent: AsyncClient, customer: AsyncClient, clock
) -> None:  # type: ignore[no-untyped-def]
    made = await heard(agent, customer)
    clock.advance(121)
    assert (await agent.get(f"/requests/{made['id']}")).json()["state"] == "EXPIRED"
    assert problem(await customer.get(f"/requests/{made['id']}/readback")) == (
        410,
        "REQUEST_EXPIRED",
    )


async def test_a_bad_signature_is_opaque_over_http_and_its_reason_is_only_in_the_logs(
    agent: AsyncClient,
    customer: AsyncClient,
    phone: SoftwareAuthenticator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    with caplog.at_level(logging.WARNING, logger="zolo.passkeys"):
        r = await customer.post(
            f"/requests/{made['id']}/approve",
            json=phone.assert_(options, origin="https://evil.example"),
        )
    assert problem(r) == (401, "SIGNATURE_INVALID")
    assert r.json() == {
        "type": "https://zolo.app/problems/signature-invalid", "title": "The passkey signature is not valid",
        "status": 401, "code": "SIGNATURE_INVALID", "detail": "",
    }  # fmt: skip
    visible = r.text + str(dict(r.headers))
    for reason in (
        "wrong_origin",
        "wrong_rp",
        "uv_missing",
        "bad_signature",
        "wrong_challenge",
        "stale_counter",
        "evil.example",
    ):
        assert reason not in visible
    assert [rec.code for rec in caplog.records if rec.name == "zolo.passkeys"] == ["wrong_origin"]  # type: ignore[attr-defined]


async def test_approve_attempts_are_rate_limited_even_when_they_fail(
    agent: AsyncClient, customer: AsyncClient, phone: SoftwareAuthenticator, limiter_clock
) -> None:  # type: ignore[no-untyped-def]
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    for _ in range(10):
        r = await customer.post(
            f"/requests/{made['id']}/approve", json=phone.assert_(options, corrupt_signature=True)
        )
        assert problem(r) == (401, "SIGNATURE_INVALID")
    blocked = await customer.post(
        f"/requests/{made['id']}/approve", json=phone.assert_(options)
    )  # a good one
    assert problem(blocked) == (429, "RATE_LIMITED") and "retry-after" in blocked.headers
    limiter_clock.advance(61)
    assert (
        await customer.post(f"/requests/{made['id']}/approve", json=phone.assert_(options))
    ).json()["state"] == "SETTLED"


async def test_challenge_requests_are_rate_limited(
    agent: AsyncClient, customer: AsyncClient, phone: SoftwareAuthenticator, limiter_clock
) -> None:  # type: ignore[no-untyped-def]
    await register_passkey(customer, phone)
    made = await heard(agent, customer)
    for _ in range(10):
        assert (await customer.post(f"/requests/{made['id']}/challenge")).status_code == 200
    assert problem(await customer.post(f"/requests/{made['id']}/challenge")) == (
        429,
        "RATE_LIMITED",
    )
    limiter_clock.advance(61)
    assert (await customer.post(f"/requests/{made['id']}/challenge")).status_code == 200


# ======================================================================= activity, audio


async def test_activity_shows_readable_lines_newest_first_and_at_most_twenty(
    agent: AsyncClient, customer: AsyncClient, phone: SoftwareAuthenticator, limiter_clock, clock
) -> None:  # type: ignore[no-untyped-def]
    await register_passkey(customer, phone)
    paid, options = await ready(agent, customer, phone, 5_000)
    await customer.post(f"/requests/{paid['id']}/approve", json=phone.assert_(options))
    clock.advance(1)
    declined = await heard(agent, customer, 2_000)
    await customer.post(f"/requests/{declined['id']}/decline")
    clock.advance(1)
    await heard(agent, customer, 3_000)
    clock.advance(200)  # the last one runs out
    items = (await customer.get("/me/activity")).json()["items"]
    assert [i["line"] for i in items] == [
        "Expired: ₦3,000 to Bisi Ventures", "You declined ₦2,000 to Bisi Ventures", "Paid ₦5,000 to Bisi Ventures",
    ]  # fmt: skip
    assert [i["state"] for i in items] == ["EXPIRED", "DECLINED", "SETTLED"]


async def test_activity_is_capped_at_twenty(
    api: FastAPI, agent: AsyncClient, customer: AsyncClient, limiter_clock, clock
) -> None:  # type: ignore[no-untyped-def]
    for _ in range(25):
        made = await new_request(agent, 1_000)
        await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
        clock.advance(1)
        limiter_clock.advance(61)
    assert len((await customer.get("/me/activity")).json()["items"]) == 20


async def test_audio_is_served_from_the_cache_and_only_by_exact_key(
    api: FastAPI, anonymous: AsyncClient, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zolo.ai.tts.base import AudioClip
    from zolo.ai.tts.cache import AudioCache, cache_key

    cache = AudioCache(tmp_path)
    key = cache_key("yarngpt", "pcm", "idera", "hello")
    cache.put(key, AudioClip(b"ID3-fake-mp3"))
    api.state.services = None  # rebuild with the temp cache
    monkeypatch.setenv("AUDIO_CACHE_DIR", str(tmp_path))
    r = await anonymous.get(f"/voice/audio/{key}.mp3")
    assert (
        r.status_code == 200
        and r.content == b"ID3-fake-mp3"
        and r.headers["content-type"] == "audio/mpeg"
    )
    for bad in ("0" * 64, "../../etc/passwd", "short", "Z" * 64):
        assert problem(await anonymous.get(f"/voice/audio/{bad}.mp3")) == (404, "NOT_FOUND")


# ======================================================================= privacy and the demo store


async def test_nothing_personal_reaches_the_logs_during_a_whole_cash_out(
    agent: AsyncClient,
    customer: AsyncClient,
    phone: SoftwareAuthenticator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        await register_passkey(customer, phone)
        made, options = await ready(agent, customer, phone)
        await customer.post(f"/requests/{made['id']}/approve", json=phone.assert_(options))
        await customer.get("/me/activity")
    logged = " ".join(
        f"{r.getMessage()} {json.dumps(r.__dict__, default=str)}" for r in caplog.records
    )
    for private in (
        "BISI",
        "Bisi",
        "Amaka",
        "0123456789",
        "2000000001",
        "1500000",
        "15,000",
        "+2348011111111",
        made["claim_code"] + "&",
        "123456",
    ):
        assert private not in logged, private


async def test_the_last_valid_assertion_is_kept_for_the_demo_replay_only_when_it_worked(
    api: FastAPI, agent: AsyncClient, customer: AsyncClient, phone: SoftwareAuthenticator
) -> None:
    demo = api.state.services.demo
    assert demo is not None
    await register_passkey(customer, phone)
    made, options = await ready(agent, customer, phone)
    request_id = uuid.UUID(made["id"])
    await customer.post(
        f"/requests/{made['id']}/approve", json=phone.assert_(options, corrupt_signature=True)
    )
    assert demo.last_assertion(request_id) is None  # a refused attempt is not kept
    good = phone.assert_(options)
    await customer.post(f"/requests/{made['id']}/approve", json=good)
    assert demo.last_assertion(request_id) == good
    demo.clear()  # what /demo/reset does
    assert demo.last_assertion(request_id) is None


async def test_nothing_is_kept_outside_demo_mode(sessionmaker, clock, limiter_clock) -> None:  # type: ignore[no-untyped-def]
    from tests.api.conftest import build_app
    from tests.conftest import make_settings

    app = await build_app(
        sessionmaker, make_settings(demo_mode=False, demo_token=""), clock, limiter_clock
    )
    async with browser(app) as c:
        await c.get("/me/activity")  # any call that needs the services builds them
        assert app.state.services.demo is None  # no store exists at all


# ======================================================================= the dev page for a real phone


async def test_the_dev_page_exists_in_demo_mode_with_a_tight_csp(anonymous: AsyncClient) -> None:
    r = await anonymous.get("/dev/passkey-test")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    csp = r.headers["content-security-policy"]
    assert "connect-src 'self'" in csp and "default-src 'none'" in csp
    for endpoint in ("/auth/mock-login", "/passkeys/register/options", "/passkeys/register/verify",
                     "/agent/requests", "/requests/claim", "/readback", "/challenge", "/approve"):  # fmt: skip
        assert endpoint in r.text
    assert "navigator.credentials.create" in r.text and "navigator.credentials.get" in r.text
    assert "location.hostname" in r.text  # shows the host that must equal RP_ID
