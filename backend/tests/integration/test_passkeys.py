"""Registration and the approval ceremony, with a software authenticator."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.test_consent_engine import (
    AMAKA,
    NAIRA,
    START,
    Clock,
    StubAudio,
    balance,
    claim,
    create,
    readback,
    row,
)
from tests.webauthn_software import SoftwareAuthenticator
from zolo.audit.models import AuditEvent
from zolo.bank.mock import Latency, MockBankAdapter
from zolo.bank.models import MockTransfer
from zolo.consent.intent import Intent, intent_hash
from zolo.consent.models import PaymentRequest
from zolo.consent.service import ConsentService
from zolo.core.config import Settings
from zolo.core.errors import ApiError
from zolo.demo.seed import reset_demo
from zolo.passkeys.models import PasskeyCredential, WebAuthnChallenge
from zolo.passkeys.service import PasskeyService

SM = async_sessionmaker[AsyncSession]


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
async def world(sessionmaker: SM, settings: Settings, clock: Clock):  # type: ignore[no-untyped-def]
    await reset_demo(sessionmaker, settings)
    bank = MockBankAdapter(sessionmaker, latency=Latency(0, 0))
    svc = ConsentService(settings, bank, audio=StubAudio(), clock=clock)  # type: ignore[arg-type]
    return svc, bank, sessionmaker


@pytest.fixture
def phone(settings: Settings) -> SoftwareAuthenticator:
    return SoftwareAuthenticator(settings.rp_id, settings.origins[0])


async def register(
    world,
    phone: SoftwareAuthenticator,
    customer: uuid.UUID = AMAKA,
    label: str | None = "demo phone",
):  # type: ignore[no-untyped-def]
    svc, _, sm = world
    async with sm() as s:
        options = await svc.passkeys.registration_options(
            s, customer, "+2348011111111", "Amaka Obi"
        )
    async with sm() as s:
        return options, await svc.passkeys.verify_registration(
            s, customer, phone.register(options), label
        )


async def ready_to_sign(world, phone: SoftwareAuthenticator, amount: int = 15_000 * NAIRA):  # type: ignore[no-untyped-def]
    """A request the customer has heard, with a registered passkey and a challenge issued."""
    svc, _, sm = world
    if not await _has_passkey(sm):
        await register(world, phone)
    made = await create(world, amount)
    await claim(world, made.claim_code)  # type: ignore[arg-type]
    await readback(world, made.id)
    async with sm() as s:
        options = await svc.issue_challenge(s, AMAKA, made.id)
    return made, options


async def _has_passkey(sm: SM) -> bool:
    async with sm() as s:
        return (
            await s.execute(select(func.count()).select_from(PasskeyCredential))
        ).scalar_one() > 0


async def approve(world, request_id: uuid.UUID, assertion: dict):  # type: ignore[no-untyped-def,type-arg]
    svc, _, sm = world
    async with sm() as s:
        return await svc.approve(s, AMAKA, request_id, assertion)


def code(exc: pytest.ExceptionInfo[ApiError]) -> tuple[int, str]:
    return exc.value.status, exc.value.code.value


# ======================================================================= registration


async def test_registration_options_follow_the_spec(world, settings) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    async with sm() as s:
        o = await svc.passkeys.registration_options(s, AMAKA, "+2348011111111", "Amaka Obi")
    assert o["rp"] == {"name": "Zolo", "id": "localhost"}
    assert o["authenticatorSelection"]["authenticatorAttachment"] == "platform"
    assert o["authenticatorSelection"]["residentKey"] == "preferred"
    assert o["authenticatorSelection"]["userVerification"] == "required"
    assert o["attestation"] == "none"
    from webauthn.helpers import base64url_to_bytes

    assert base64url_to_bytes(o["user"]["id"]) == AMAKA.bytes  # the customer's UUID is the user id
    assert len(base64url_to_bytes(o["challenge"])) >= 32


async def test_a_passkey_can_be_registered_and_is_stored(world, phone) -> None:  # type: ignore[no-untyped-def]
    _, result = await register(world, phone)
    assert result.device_label == "demo phone" and not result.replaced_previous
    async with world[2]() as s:
        cred = (await s.execute(select(PasskeyCredential))).scalar_one()
    assert cred.customer_id == AMAKA and cred.credential_id == phone.credential_id
    assert cred.revoked_at is None and cred.sign_count == 0 and cred.transports == ["internal"]


async def test_registering_again_replaces_the_old_passkey(world, phone) -> None:  # type: ignore[no-untyped-def]
    await register(world, phone)
    second = SoftwareAuthenticator()
    _, result = await register(world, second)
    assert result.replaced_previous
    async with world[2]() as s:
        creds = (
            (await s.execute(select(PasskeyCredential).order_by(PasskeyCredential.created_at)))
            .scalars()
            .all()
        )
    assert [c.revoked_at is not None for c in creds] == [
        True,
        False,
    ]  # one active passkey per customer


async def test_registration_needs_a_started_ceremony_and_each_challenge_works_once(
    world, phone
) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    options, _ = await register(world, phone)
    async with sm() as s:
        with pytest.raises(ApiError) as exc:  # the challenge was consumed
            await svc.passkeys.verify_registration(s, AMAKA, phone.register(options), None)
    assert code(exc) == (409, "CHALLENGE_NOT_FOUND")


@pytest.mark.parametrize("origin", ["https://evil.example", "http://localhost:3001"])
async def test_registration_from_another_origin_is_refused(world, phone, origin) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    async with sm() as s:
        options = await svc.passkeys.registration_options(s, AMAKA, "u", "U")
    async with sm() as s:
        with pytest.raises(ApiError) as exc:
            await svc.passkeys.verify_registration(
                s, AMAKA, phone.register(options, origin=origin), None
            )
    assert code(exc) == (400, "PASSKEY_REGISTRATION_FAILED")
    assert not await _has_passkey(sm)


async def test_registration_with_a_challenge_for_someone_else_is_refused(world, phone) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    async with sm() as s:
        options = await svc.passkeys.registration_options(s, AMAKA, "u", "U")
    options = {**options, "challenge": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}
    async with sm() as s:
        with pytest.raises(ApiError) as exc:
            await svc.passkeys.verify_registration(s, AMAKA, phone.register(options), None)
    assert code(exc) == (400, "PASSKEY_REGISTRATION_FAILED")


# ======================================================================= the challenge


async def test_the_challenge_is_the_intent_hash_of_exactly_this_request(world, phone) -> None:  # type: ignore[no-untyped-def]
    from webauthn.helpers import base64url_to_bytes

    made, options = await ready_to_sign(world, phone)
    r = await row(world[2], made.id)
    assert base64url_to_bytes(options["challenge"]) == r.intent_hash
    assert options["userVerification"] == "required" and options["rpId"] == "localhost"
    assert len(options["allowCredentials"]) == 1
    expected = intent_hash(Intent(
        request_id=r.id, customer_id=AMAKA, payee_account="0123456789", payee_bank_code="057",
        payee_name="BISI VENTURES", amount_kobo=1_500_000, currency="NGN", nonce=r.nonce, expires_at=r.expires_at,
    ))  # fmt: skip
    assert r.intent_hash == expected


async def test_a_challenge_needs_a_passkey_and_a_readback(world, phone) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made = await create(world)
    await claim(world, made.claim_code)  # type: ignore[arg-type]
    async with sm() as s:
        with pytest.raises(ApiError) as early:  # not read back yet
            await svc.issue_challenge(s, AMAKA, made.id)
    assert code(early) == (409, "STATE_CONFLICT")
    await readback(world, made.id)
    async with sm() as s:
        with pytest.raises(ApiError) as nopasskey:
            await svc.issue_challenge(s, AMAKA, made.id)
    assert code(nopasskey) == (409, "NO_PASSKEY")


async def test_asking_for_a_challenge_again_replaces_the_old_one(world, phone) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made, _ = await ready_to_sign(world, phone)
    async with sm() as s:
        await svc.issue_challenge(s, AMAKA, made.id)
        assert (
            await s.execute(
                select(func.count())
                .select_from(WebAuthnChallenge)
                .where(WebAuthnChallenge.request_id == made.id)
            )
        ).scalar_one() == 1


async def test_a_change_after_the_readback_is_caught_when_the_challenge_is_requested(
    world, phone
) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made, _ = await ready_to_sign(world, phone)
    async with sm() as s:
        await s.execute(
            update(PaymentRequest).where(PaymentRequest.id == made.id).values(amount_kobo=5_100_000)
        )
        await s.commit()
    async with sm() as s:
        with pytest.raises(ApiError) as exc:
            await svc.issue_challenge(s, AMAKA, made.id)
    assert code(exc) == (409, "INTENT_CHANGED")


# ======================================================================= the happy path


async def test_a_valid_signature_approves_and_the_money_moves(world, phone) -> None:  # type: ignore[no-untyped-def]
    made, options = await ready_to_sign(world, phone)
    done = await approve(world, made.id, phone.assert_(options))
    assert done.state == "SETTLED" and (done.bank_reference or "").startswith("MOCK-")
    assert await balance(world[2], "2000000001") == 235_000 * NAIRA
    assert await balance(world[2], "0123456789") == 515_000 * NAIRA
    r = await row(world[2], made.id)
    assert r.approved_at == START and r.settled_at == START
    async with world[2]() as s:
        cred = (await s.execute(select(PasskeyCredential))).scalar_one()
        used = (
            await s.execute(
                select(WebAuthnChallenge).where(WebAuthnChallenge.request_id == made.id)
            )
        ).scalar_one()
    assert (
        cred.sign_count == 1 and used.used_at == START
    )  # the counter moved, the challenge is spent


async def test_the_audit_trail_records_the_whole_ceremony_without_personal_data(
    world, phone
) -> None:  # type: ignore[no-untyped-def]
    made, options = await ready_to_sign(world, phone)
    await approve(world, made.id, phone.assert_(options))
    async with world[2]() as s:
        events = [
            e.event for e in (await s.execute(select(AuditEvent).order_by(AuditEvent.id))).scalars()
        ]
    assert events == [
        "passkey.registration_started", "passkey.registered", "request.created", "request.claimed",
        "request.read_back", "challenge.issued", "request.approved", "transfer.submitted", "transfer.settled",
    ]  # fmt: skip


# ======================================================================= tamper, replay, expiry


async def test_tampering_after_the_challenge_is_caught_and_nothing_is_sent(world, phone) -> None:  # type: ignore[no-untyped-def]
    made, options = await ready_to_sign(world, phone)
    assertion = phone.assert_(options)  # the customer signed the ₦15,000 they heard
    async with world[2]() as s:
        await s.execute(
            update(PaymentRequest).where(PaymentRequest.id == made.id).values(amount_kobo=5_100_000)
        )
        await s.commit()
    with pytest.raises(ApiError) as exc:
        await approve(world, made.id, assertion)
    assert code(exc) == (409, "INTENT_CHANGED")
    r = await row(world[2], made.id)
    assert r.state == "READ_BACK" and await balance(world[2], "2000000001") == 250_000 * NAIRA
    async with world[2]() as s:
        assert (await s.execute(select(func.count()).select_from(MockTransfer))).scalar_one() == 0


async def test_changing_the_payee_after_the_readback_is_caught_too(world, phone) -> None:  # type: ignore[no-untyped-def]
    made, options = await ready_to_sign(world, phone)
    async with world[2]() as s:
        await s.execute(
            update(PaymentRequest)
            .where(PaymentRequest.id == made.id)
            .values(payee_verified_name="OKONKWO PETER")
        )
        await s.commit()
    with pytest.raises(ApiError) as exc:
        await approve(world, made.id, phone.assert_(options))
    assert code(exc) == (409, "INTENT_CHANGED")


async def test_replaying_the_same_assertion_is_already_used_and_pays_nothing_more(
    world, phone
) -> None:  # type: ignore[no-untyped-def]
    made, options = await ready_to_sign(world, phone)
    assertion = phone.assert_(options)
    assert (await approve(world, made.id, assertion)).state == "SETTLED"
    with pytest.raises(ApiError) as exc:
        await approve(world, made.id, assertion)
    assert code(exc) == (409, "ALREADY_USED")
    assert await balance(world[2], "2000000001") == 235_000 * NAIRA  # debited once


async def test_a_fresh_signature_on_a_finished_request_is_also_already_used(world, phone) -> None:  # type: ignore[no-untyped-def]
    made, options = await ready_to_sign(world, phone)
    await approve(world, made.id, phone.assert_(options))
    with pytest.raises(ApiError) as exc:
        await approve(world, made.id, phone.assert_(options))
    assert code(exc) == (409, "ALREADY_USED")


async def test_two_approvals_at_once_give_one_success_and_one_409(world, phone) -> None:  # type: ignore[no-untyped-def]
    made, options = await ready_to_sign(world, phone)
    assertion = phone.assert_(options)  # a double click: the same assertion twice
    results = await asyncio.gather(
        approve(world, made.id, assertion),
        approve(world, made.id, assertion),
        return_exceptions=True,
    )
    wins = [r for r in results if not isinstance(r, BaseException)]
    losses = [r for r in results if isinstance(r, ApiError)]
    assert len(wins) == 1 and len(losses) == 1 and wins[0].state == "SETTLED"
    # Which 409 depends on whether the loser arrived before or after the winner finished:
    # STATE_CONFLICT if it lost the race, ALREADY_USED if it came in afterwards as a replay.
    assert losses[0].status == 409
    assert losses[0].code.value in ("STATE_CONFLICT", "ALREADY_USED")
    assert await balance(world[2], "2000000001") == 235_000 * NAIRA


async def _wait_for_a_lock_waiter(sm: SM) -> None:
    """Block until some session is waiting on a row lock (so the race is real, not hoped for)."""
    from sqlalchemy import text

    for _ in range(100):
        async with sm() as s:
            waiting = (
                await s.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'")
                )
            ).scalar_one()
        if waiting:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("nobody ever waited on the lock")


async def test_losing_a_real_race_to_another_approval_is_state_conflict(world, phone) -> None:  # type: ignore[no-untyped-def]
    _, _, sm = world
    made, options = await ready_to_sign(world, phone)
    assertion = phone.assert_(options)
    async with sm() as winner:  # plays the other phone: it holds the row while the loser arrives
        await winner.execute(
            select(PaymentRequest).where(PaymentRequest.id == made.id).with_for_update()
        )
        loser = asyncio.create_task(approve(world, made.id, assertion))
        await _wait_for_a_lock_waiter(
            sm
        )  # the loser has looked (READ_BACK) and is now stuck behind us
        await winner.execute(
            update(WebAuthnChallenge)
            .where(WebAuthnChallenge.request_id == made.id)
            .values(used_at=START)
        )
        await winner.execute(
            update(PaymentRequest)
            .where(PaymentRequest.id == made.id)
            .values(state="APPROVED", approved_at=START)
        )
        await winner.commit()
    with pytest.raises(ApiError) as exc:
        await loser
    assert code(exc) == (409, "STATE_CONFLICT")  # it lost the race: not a replay of an old approval
    assert await balance(sm, "2000000001") == 250_000 * NAIRA  # and it moved nothing


async def test_eight_simultaneous_approvals_still_pay_exactly_once(world, phone) -> None:  # type: ignore[no-untyped-def]
    made, options = await ready_to_sign(world, phone)
    assertion = phone.assert_(options)
    results = await asyncio.gather(
        *[approve(world, made.id, assertion) for _ in range(8)], return_exceptions=True
    )
    assert sum(not isinstance(r, BaseException) for r in results) == 1
    assert all(
        isinstance(r, ApiError) and r.status == 409 for r in results if isinstance(r, BaseException)
    )
    async with world[2]() as s:
        assert (await s.execute(select(func.count()).select_from(MockTransfer))).scalar_one() == 1
    assert await balance(world[2], "2000000001") == 235_000 * NAIRA


async def test_approving_after_the_deadline_is_410_and_nothing_moves(world, phone, clock) -> None:  # type: ignore[no-untyped-def]
    made, options = await ready_to_sign(world, phone)
    assertion = phone.assert_(options)
    clock.advance(121)
    with pytest.raises(ApiError) as exc:
        await approve(world, made.id, assertion)
    assert code(exc) == (410, "REQUEST_EXPIRED")
    assert (await row(world[2], made.id)).state == "EXPIRED" and await balance(
        world[2], "2000000001"
    ) == 250_000 * NAIRA


async def test_a_declined_request_cannot_be_approved(world, phone) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made, options = await ready_to_sign(world, phone)
    async with sm() as s:
        await svc.decline(s, AMAKA, made.id)
    with pytest.raises(ApiError) as exc:
        await approve(world, made.id, phone.assert_(options))
    assert code(exc) == (409, "STATE_CONFLICT")


async def test_approving_without_a_challenge_is_refused(world, phone) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    await register(world, phone)
    made = await create(world)
    await claim(world, made.claim_code)  # type: ignore[arg-type]
    await readback(world, made.id)
    r = await row(sm, made.id)
    with pytest.raises(ApiError) as exc:
        await approve(world, made.id, phone.assert_(challenge=r.intent_hash))  # type: ignore[arg-type]
    assert code(exc) == (409, "CHALLENGE_NOT_FOUND")


async def test_another_customer_cannot_approve(world, phone) -> None:  # type: ignore[no-untyped-def]
    svc, _, sm = world
    made, options = await ready_to_sign(world, phone)
    async with sm() as s:
        with pytest.raises(ApiError) as exc:
            await svc.approve(s, uuid.uuid4(), made.id, phone.assert_(options))
    assert code(exc) == (404, "NOT_FOUND")


# ======================================================================= bad signatures


@pytest.mark.parametrize(
    "tweak",
    [
        {"origin": "https://evil.example"},
        {"rp_id": "evil.example"},
        {"user_verified": False},
        {"corrupt_signature": True},
        {"challenge": b"\x00" * 32},
        {"key": ec.generate_private_key(ec.SECP256R1())},
    ],
    ids=[
        "wrong-origin",
        "wrong-rp",
        "no-user-verification",
        "bad-signature",
        "wrong-challenge",
        "other-key",
    ],
)
async def test_a_bad_assertion_is_refused_and_the_challenge_survives(world, phone, tweak) -> None:  # type: ignore[no-untyped-def]
    made, options = await ready_to_sign(world, phone)
    with pytest.raises(ApiError) as exc:
        await approve(world, made.id, phone.assert_(options, **tweak))
    assert code(exc) == (401, "SIGNATURE_INVALID")
    assert (await row(world[2], made.id)).state == "READ_BACK"
    assert await balance(world[2], "2000000001") == 250_000 * NAIRA
    # the customer can still sign properly
    assert (await approve(world, made.id, phone.assert_(options))).state == "SETTLED"


async def test_a_passkey_that_is_not_theirs_or_is_revoked_is_refused(world, phone) -> None:  # type: ignore[no-untyped-def]
    made, options = await ready_to_sign(world, phone)
    stranger = SoftwareAuthenticator()  # never registered
    with pytest.raises(ApiError) as exc:
        await approve(world, made.id, stranger.assert_(options))
    assert code(exc) == (401, "SIGNATURE_INVALID")
    async with world[2]() as s:
        await s.execute(update(PasskeyCredential).values(revoked_at=datetime.now(UTC)))
        await s.commit()
    with pytest.raises(ApiError) as revoked:
        await approve(world, made.id, phone.assert_(options))
    assert code(revoked) == (401, "SIGNATURE_INVALID")


@pytest.mark.parametrize(
    "garbage", [{}, {"rawId": "!!!"}, {"rawId": 5}, {"rawId": "AAAA", "response": {}}]
)
async def test_malformed_assertions_are_just_invalid(world, phone, garbage) -> None:  # type: ignore[no-untyped-def]
    made, _ = await ready_to_sign(world, phone)
    with pytest.raises(ApiError) as exc:
        await approve(world, made.id, garbage)
    assert code(exc) == (401, "SIGNATURE_INVALID")


# ======================================================================= signature counter


async def test_platform_passkeys_that_always_send_zero_are_accepted(world, phone) -> None:  # type: ignore[no-untyped-def]
    phone.counter_mode = "zero"
    made, options = await ready_to_sign(world, phone)
    assert (await approve(world, made.id, phone.assert_(options))).state == "SETTLED"
    second = await create(world, 5_000 * NAIRA)
    await claim(world, second.claim_code)  # type: ignore[arg-type]
    await readback(world, second.id)
    async with world[2]() as s:
        options2 = await world[0].issue_challenge(s, AMAKA, second.id)
    assert (await approve(world, second.id, phone.assert_(options2))).state == "SETTLED"


async def test_the_counter_must_keep_increasing(world, phone) -> None:  # type: ignore[no-untyped-def]
    made, options = await ready_to_sign(world, phone)
    await approve(world, made.id, phone.assert_(options, sign_count=10))
    second = await create(world, 5_000 * NAIRA)
    await claim(world, second.claim_code)  # type: ignore[arg-type]
    await readback(world, second.id)
    async with world[2]() as s:
        options2 = await world[0].issue_challenge(s, AMAKA, second.id)
    for stale in (9, 10):  # a decrease, and the same count again: a cloned authenticator
        with pytest.raises(ApiError) as exc:
            await approve(world, second.id, phone.assert_(options2, sign_count=stale))
        assert code(exc) == (401, "SIGNATURE_INVALID")
    assert (
        await approve(world, second.id, phone.assert_(options2, sign_count=11))
    ).state == "SETTLED"


# ======================================================================= risk


async def test_the_daily_cap_blocks_the_approval_and_leaves_the_request_unsigned(
    world, phone, settings
) -> None:  # type: ignore[no-untyped-def]
    # three ₦90,000 payments fit under ₦200,000 only twice
    for _ in range(2):
        made, options = await ready_to_sign(world, phone, 90_000 * NAIRA)
        assert (await approve(world, made.id, phone.assert_(options))).state == "SETTLED"
    made, options = await ready_to_sign(world, phone, 90_000 * NAIRA)
    with pytest.raises(ApiError) as exc:
        await approve(world, made.id, phone.assert_(options))
    assert code(exc) == (422, "LIMIT_EXCEEDED")
    assert (await row(world[2], made.id)).state == "READ_BACK"
    assert await balance(world[2], "2000000001") == 250_000 * NAIRA - 180_000 * NAIRA
    async with world[2]() as s:
        blocked = (
            await s.execute(select(AuditEvent).where(AuditEvent.event == "approve.blocked"))
        ).scalar_one()
    assert blocked.details == {"code": "DAILY_CAP"}


async def test_a_customer_can_lower_their_own_cap_but_not_raise_it(world, phone) -> None:  # type: ignore[no-untyped-def]
    from zolo.risk.models import RiskLimit

    async with world[2]() as s:
        await s.execute(update(RiskLimit).values(per_payment_kobo=10_000 * NAIRA))
        await s.commit()
    made, options = await ready_to_sign(world, phone, 15_000 * NAIRA)
    with pytest.raises(ApiError) as exc:
        await approve(world, made.id, phone.assert_(options))
    assert code(exc) == (422, "LIMIT_EXCEEDED")
    async with world[2]() as s:  # a stored limit above the hard cap does not raise it
        await s.execute(update(RiskLimit).values(per_payment_kobo=10**12, daily_kobo=10**12))
        await s.commit()
    big = await create(world, 100_000 * NAIRA)
    assert big.amount_kobo == 100_000 * NAIRA
    with pytest.raises(ApiError) as over:
        await create(world, 100_001 * NAIRA)
    assert code(over) == (422, "LIMIT_EXCEEDED")


# ======================================================================= a dropped network


async def test_approval_survives_a_dropped_network_and_pays_once(
    world, phone, settings, sessionmaker, clock
) -> None:  # type: ignore[no-untyped-def]
    from tests.integration.test_consent_engine import Flaky

    svc, _, sm = world
    flaky = Flaky(MockBankAdapter(sm, latency=Latency(0, 0)), fail_times=1)
    svc.bank = flaky  # type: ignore[assignment]
    made, options = await ready_to_sign(world, phone)
    pending = await approve(world, made.id, phone.assert_(options))
    assert pending.state == "SUBMITTED" and await balance(sm, "2000000001") == 250_000 * NAIRA
    async with (
        sm() as s
    ):  # the client (or the Phase 2 reconciler) retries the settle with the same key
        assert (await svc.settle(s, made.id)).state == "SETTLED"
    assert await balance(sm, "2000000001") == 235_000 * NAIRA
    async with sm() as s:
        assert (await s.execute(select(func.count()).select_from(MockTransfer))).scalar_one() == 1


def test_clock_helper_is_frozen_by_default() -> None:
    assert (
        Clock().now == START and timedelta(0) == timedelta(seconds=0) and PasskeyService is not None
    )
