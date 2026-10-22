"""Phone-call approval: the call hears the same readback, a PIN on the keypad approves, a voice on
its own never does, and the lower call cap and every consent guard still apply."""

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.api.test_endpoints import new_request, problem
from tests.integration.test_consent_engine import NAIRA, Clock
from zolo.api.services import build_services
from zolo.core.config import Settings
from zolo.core.errors import ApiError, ErrorCode
from zolo.phone.pin import hash_pin, is_weak, verify_pin

NUMBER, PIN = "+2348055550142", "7391"


@pytest.fixture(autouse=True)
def phone_on(settings: Settings) -> None:
    settings.feature_phone_call = True


async def enrol(customer: AsyncClient, pin: str = PIN, **extra: Any) -> Any:
    return await customer.post("/phone/enrol", json={"phone": NUMBER, "pin": pin, **extra})


async def claimed(agent: AsyncClient, customer: AsyncClient, naira: int = 15_000) -> str:
    made = await new_request(agent, naira)
    r = await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
    assert r.status_code == 200, r.text
    return str(made["id"])


async def ring(customer: AsyncClient, request_id: str) -> dict[str, Any]:
    r = await customer.post("/phone/calls", json={"request_id": request_id})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def keys(customer: AsyncClient, call: dict[str, Any], digits: str) -> dict[str, Any]:
    r = await customer.post(f"/phone/calls/{call['call_id']}/keys", json={"digits": digits})
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


async def state(customer: AsyncClient, request_id: str) -> str:
    return str((await customer.get(f"/requests/{request_id}")).json()["state"])


async def method(sessionmaker: async_sessionmaker[AsyncSession], request_id: str) -> str | None:
    async with sessionmaker() as s:
        row = await s.execute(
            text("SELECT approval_method FROM payment_requests WHERE id = :i"), {"i": request_id}
        )
        return row.scalar_one()  # type: ignore[no-any-return]


# ======================================================================= the flag and enrolment


async def test_the_routes_do_not_exist_while_the_feature_is_off(
    customer: AsyncClient, settings: Settings
) -> None:
    settings.feature_phone_call = False
    off = await customer.get("/phone/enrolment")
    assert off.status_code == 200 and off.json()["enabled"] is False
    assert problem(await enrol(customer)) == (404, "NOT_FOUND")


async def test_only_a_customer_can_use_phone_approval(agent: AsyncClient) -> None:
    assert problem(await agent.get("/phone/enrolment")) == (403, "FORBIDDEN")


async def test_enrolment_keeps_only_a_hash_and_shows_the_last_four_digits(
    customer: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    assert (await customer.get("/phone/enrolment")).json()["enrolled"] is False
    r = await enrol(customer, language="pcm")
    assert r.status_code == 200
    assert r.json() == {
        "enabled": True, "enrolled": True, "language": "pcm", "phone_last4": "0142", "locked": False, "paused": False,
    }  # fmt: skip
    async with sessionmaker() as s:
        stored = (await s.execute(text("SELECT pin_hash FROM phone_enrolments"))).scalar_one()
    assert PIN.encode() not in bytes(stored) and len(bytes(stored)) == 48


@pytest.mark.parametrize("weak", ["0000", "1234", "4321", "0142"])
async def test_easy_pins_are_refused(customer: AsyncClient, weak: str) -> None:
    assert problem(await enrol(customer, weak)) == (422, "VALIDATION_ERROR")


async def test_a_pin_must_be_four_digits_and_the_number_international(
    customer: AsyncClient,
) -> None:
    assert problem(await enrol(customer, "73910")) == (422, "VALIDATION_ERROR")
    r = await customer.post("/phone/enrol", json={"phone": "08055550142", "pin": PIN})
    assert problem(r) == (422, "VALIDATION_ERROR")


async def test_changing_the_number_pauses_phone_approval(
    agent: AsyncClient, customer: AsyncClient
) -> None:
    await enrol(customer)
    r = await customer.post("/phone/enrol", json={"phone": "+2348055550199", "pin": PIN})
    assert r.json()["paused"] is True
    request_id = await claimed(agent, customer)
    r = await customer.post("/phone/calls", json={"request_id": request_id})
    assert problem(r) == (409, "STATE_CONFLICT")


# ======================================================================= the call


async def test_an_approved_call_pays_and_records_how(
    agent: AsyncClient,
    customer: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await enrol(customer)
    request_id = await claimed(agent, customer)
    call = await ring(customer, request_id)
    assert [p["key"] for p in call["prompts"]] == ["intro", "readback", "menu"]
    assert (
        "15,000" in call["prompts"][1]["text"] or "fifteen thousand" in call["prompts"][1]["text"]
    )
    assert call["expects"] == "choice" and call["done"] is False
    assert await state(customer, request_id) == "READ_BACK"  # heard, not approved

    asked = await keys(customer, call, "1")
    assert asked["expects"] == "pin" and [p["key"] for p in asked["prompts"]] == ["privacy", "pin"]
    assert await state(customer, request_id) == "READ_BACK"

    done = await keys(customer, call, PIN)
    assert done["done"] and done["outcome"] == "approved"
    assert await state(customer, request_id) == "SETTLED"
    assert await method(sessionmaker, request_id) == "phone_pin"
    assert (await agent.get(f"/requests/{request_id}")).json()["state"] == "SETTLED"


async def test_pressing_two_declines_and_sends_nothing(
    agent: AsyncClient, customer: AsyncClient
) -> None:
    await enrol(customer)
    request_id = await claimed(agent, customer)
    done = await keys(customer, await ring(customer, request_id), "2")
    assert done["outcome"] == "declined"
    assert await state(customer, request_id) == "DECLINED"


async def test_nine_plays_the_readback_again(agent: AsyncClient, customer: AsyncClient) -> None:
    await enrol(customer)
    request_id = await claimed(agent, customer)
    again = await keys(customer, await ring(customer, request_id), "9")
    assert [p["key"] for p in again["prompts"]] == ["readback", "menu"] and not again["done"]


@pytest.mark.parametrize("digit", ["0", "5", "7"])
async def test_any_other_key_ends_the_call_without_approving(
    agent: AsyncClient, customer: AsyncClient, digit: str
) -> None:
    await enrol(customer)
    request_id = await claimed(agent, customer)
    done = await keys(customer, await ring(customer, request_id), digit)
    assert done["done"] and done["outcome"] == "ended"
    assert await state(customer, request_id) == "READ_BACK"


async def test_the_pin_typed_at_the_menu_is_not_a_pin(
    agent: AsyncClient, customer: AsyncClient
) -> None:
    await enrol(customer)
    request_id = await claimed(agent, customer)
    done = await keys(customer, await ring(customer, request_id), PIN)
    assert done["outcome"] == "ended"
    assert await state(customer, request_id) == "READ_BACK"


async def test_a_wrong_pin_ends_the_call_and_a_call_gets_one_try(
    agent: AsyncClient, customer: AsyncClient
) -> None:
    await enrol(customer)
    request_id = await claimed(agent, customer)
    call = await ring(customer, request_id)
    await keys(customer, call, "1")
    wrong = await keys(customer, call, "1111")
    assert wrong["done"] and wrong["prompts"][0]["key"] == "wrong_pin"
    after = await keys(customer, call, PIN)  # the right PIN on the dead call does nothing
    assert after["done"] and after["outcome"] != "approved"
    assert await state(customer, request_id) == "READ_BACK"


async def test_three_wrong_pins_lock_phone_approval_for_a_while(
    agent: AsyncClient, customer: AsyncClient, clock: Clock, settings: Settings
) -> None:
    settings.phone_calls_per_hour = 10  # so the hourly limit is not what stops the fourth call
    await enrol(customer)
    for _ in range(3):
        request_id = await claimed(agent, customer)
        call = await ring(customer, request_id)
        await keys(customer, call, "1")
        await keys(customer, call, "2580")
    assert (await customer.get("/phone/enrolment")).json()["locked"] is True
    request_id = await claimed(agent, customer)
    assert problem(await customer.post("/phone/calls", json={"request_id": request_id})) == (
        409, "STATE_CONFLICT",
    )  # fmt: skip
    clock.advance(1801)
    request_id = await claimed(agent, customer)
    call = await ring(customer, request_id)  # unlocked after the lock time
    assert (await keys(customer, call, "1"))["expects"] == "pin"


async def test_calls_are_limited_per_hour(agent: AsyncClient, customer: AsyncClient) -> None:
    await enrol(customer)
    for _ in range(3):
        await ring(customer, await claimed(agent, customer))
    r = await customer.post("/phone/calls", json={"request_id": await claimed(agent, customer)})
    assert problem(r) == (429, "RATE_LIMITED")


async def test_over_the_call_cap_nothing_is_sent_even_with_the_right_pin(
    agent: AsyncClient, customer: AsyncClient
) -> None:
    await enrol(customer)
    request_id = await claimed(agent, customer, naira=25_000)  # fine for a passkey, not a call
    call = await ring(customer, request_id)
    await keys(customer, call, "1")
    done = await keys(customer, call, PIN)
    assert done["prompts"][0]["key"] == "limit" and done["outcome"] == "ended"
    assert await state(customer, request_id) == "READ_BACK"


async def test_a_payment_changed_after_the_call_read_it_is_not_approved(
    agent: AsyncClient,
    customer: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await enrol(customer)
    request_id = await claimed(agent, customer)
    call = await ring(customer, request_id)
    await keys(customer, call, "1")
    async with sessionmaker() as s:
        await s.execute(
            text("UPDATE payment_requests SET amount_kobo = :a WHERE id = :i"),
            {"a": 1_900_000, "i": request_id},
        )
        await s.commit()
    done = await keys(customer, call, PIN)
    assert done["prompts"][0]["key"] == "changed" and done["outcome"] == "ended"
    assert await state(customer, request_id) == "READ_BACK"
    assert await method(sessionmaker, request_id) is None


async def test_an_expired_request_cannot_be_approved_by_phone(
    agent: AsyncClient, customer: AsyncClient, clock: Clock
) -> None:
    await enrol(customer)
    request_id = await claimed(agent, customer)
    call = await ring(customer, request_id)
    await keys(customer, call, "1")
    clock.advance(121)
    done = await keys(customer, call, PIN)
    assert done["prompts"][0]["key"] == "expired"
    assert await state(customer, request_id) == "EXPIRED"


async def test_the_agent_cannot_ring_or_press_anything(
    agent: AsyncClient, customer: AsyncClient
) -> None:
    await enrol(customer)
    request_id = await claimed(agent, customer)
    call = await ring(customer, request_id)
    r = await agent.post(f"/phone/calls/{call['call_id']}/keys", json={"digits": "1"})
    assert problem(r) == (403, "FORBIDDEN")
    r = await agent.post("/phone/calls", json={"request_id": request_id})
    assert problem(r) == (403, "FORBIDDEN")


async def test_a_call_needs_enrolment_first(agent: AsyncClient, customer: AsyncClient) -> None:
    request_id = await claimed(agent, customer)
    r = await customer.post("/phone/calls", json={"request_id": request_id})
    assert problem(r) == (409, "STATE_CONFLICT")


async def test_an_app_request_cannot_be_approved_by_phone_directly(
    api: FastAPI,
    agent: AsyncClient,
    customer: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Even the consent method refuses a request that was never set up for a call."""
    request_id = await claimed(agent, customer)
    async with sessionmaker() as s:
        owner = (await s.execute(text("SELECT customer_id FROM payment_requests"))).scalar_one()
    consent = build_services(api).consent
    async with sessionmaker() as s:
        with pytest.raises(ApiError) as exc:
            await consent.approve_by_phone(s, owner, uuid.UUID(request_id), b"\0" * 32)
    assert (exc.value.status, exc.value.code) == (409, ErrorCode.STATE_CONFLICT)
    assert await state(customer, request_id) in {"CREATED", "CLAIMED"}


async def test_the_audit_trail_never_holds_the_pin_or_the_number(
    agent: AsyncClient, customer: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await enrol(customer)
    request_id = await claimed(agent, customer)
    call = await ring(customer, request_id)
    await keys(customer, call, "1")
    await keys(customer, call, PIN)
    async with sessionmaker() as s:
        rows = (await s.execute(text("SELECT event, actor, details::text FROM audit_events"))).all()
    dump = " ".join(" ".join(map(str, r)) for r in rows)
    assert PIN not in dump and "0142" not in dump and NUMBER not in dump
    assert "request.call_channel" in dump and "request.approved" in dump


async def test_a_lone_voice_has_no_way_to_approve(api: FastAPI) -> None:
    """The only paths to APPROVED are a passkey assertion and a keypad PIN."""
    paths = {p for p in api.openapi()["paths"] if p.startswith("/phone")}
    assert paths == {
        "/phone/enrolment", "/phone/enrol", "/phone/calls", "/phone/calls/{call_id}/keys",
    }  # fmt: skip


# ======================================================================= the PIN itself


def test_pin_hashing_is_salted_and_verifies() -> None:
    a, b = hash_pin(PIN), hash_pin(PIN)
    assert a != b and verify_pin(a, PIN) and verify_pin(b, PIN)
    assert not verify_pin(a, "7392") and not verify_pin(a, "73910") and not verify_pin(b"", PIN)


@pytest.mark.parametrize(
    ("pin", "weak"),
    [
        ("7391", False),
        ("1111", True),
        ("1234", True),
        ("9876", True),
        ("12a4", True),
        ("123", True),
    ],
)
def test_weak_pins(pin: str, weak: bool) -> None:
    assert is_weak(pin) is weak


def test_the_naira_unit_is_what_the_call_cap_assumes() -> None:
    assert Settings.model_fields["call_channel_cap_kobo"].default == 20_000 * NAIRA


# ======================================================================= Yoruba


async def test_a_yoruba_call_uses_the_yoruba_prompts_and_still_needs_the_pin(
    agent: AsyncClient, customer: AsyncClient
) -> None:
    r = await enrol(customer, language="yo")
    assert r.json()["language"] == "yo"
    request_id = await claimed(agent, customer)
    call = await ring(customer, request_id)
    assert call["lang"] == "yo"
    by_key = {p["key"]: p["text"] for p in call["prompts"]}
    assert "Zolo" in by_key["intro"] and "tẹ ọ̀kan" in by_key["menu"]  # not the English lines
    assert call["expects"] == "choice" and await state(customer, request_id) == "READ_BACK"
    asked = await keys(customer, call, "1")
    assert asked["lang"] == "yo" and asked["expects"] == "pin"
    done = await keys(customer, call, PIN)
    assert done["outcome"] == "approved" and await state(customer, request_id) == "SETTLED"


async def test_a_wrong_pin_is_told_in_yoruba_and_sends_nothing(
    agent: AsyncClient, customer: AsyncClient
) -> None:
    await enrol(customer, language="yo")
    request_id = await claimed(agent, customer)
    call = await ring(customer, request_id)
    await keys(customer, call, "1")
    wrong = await keys(customer, call, "2580")
    assert wrong["prompts"][0]["key"] == "wrong_pin" and "O dìgbà" in wrong["prompts"][0]["text"]
    assert await state(customer, request_id) == "READ_BACK"
