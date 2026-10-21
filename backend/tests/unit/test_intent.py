import hashlib
import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zolo.consent.intent import Intent, canonical_bytes, intent_hash

GOLDEN = json.loads((Path(__file__).parent / "data" / "golden_intents.json").read_text("utf-8"))[
    "cases"
]


def build(fields: dict[str, object]) -> Intent:
    return Intent(
        request_id=uuid.UUID(str(fields["request_id"])),
        customer_id=uuid.UUID(str(fields["customer_id"])),
        payee_account=str(fields["payee_account"]),
        payee_bank_code=str(fields["payee_bank_code"]),
        payee_name=str(fields["payee_name"]),
        amount_kobo=int(fields["amount_kobo"]),  # type: ignore[call-overload]
        currency=str(fields["currency"]),
        nonce=bytes.fromhex(str(fields["nonce_hex"])),
        expires_at=datetime.fromisoformat(str(fields["expires_at"]).replace("Z", "+00:00")),
    )


# --- golden fixtures: the exact bytes must never change without bumping the version ---


@pytest.mark.parametrize("case", GOLDEN, ids=[c["name"] for c in GOLDEN])
def test_canonical_bytes_and_hash_match_the_golden_fixture(case: dict[str, object]) -> None:
    intent = build(case["fields"])  # type: ignore[arg-type]
    assert canonical_bytes(intent) == str(case["canonical"]).encode("utf-8")
    assert intent_hash(intent).hex() == case["sha256_hex"]


@pytest.mark.parametrize("case", GOLDEN, ids=[c["name"] for c in GOLDEN])
def test_the_fixture_itself_is_internally_consistent(case: dict[str, object]) -> None:
    # catches a typo in the fixture file: the stored digest is the digest of the stored string
    assert hashlib.sha256(str(case["canonical"]).encode("utf-8")).hexdigest() == case["sha256_hex"]


def test_golden_shape_follows_the_spec() -> None:
    raw = str(GOLDEN[0]["canonical"])
    doc = json.loads(raw)
    assert list(doc) == sorted(doc)  # keys sorted
    assert ", " not in raw and ": " not in raw and "\n" not in raw  # no whitespace
    assert doc["v"] == 1 and isinstance(doc["amount_kobo"], int)
    assert doc["expires_at"].endswith("Z") and "." not in doc["expires_at"]
    assert "=" not in doc["nonce"]  # unpadded base64url


def test_non_ascii_names_are_raw_utf8_not_escaped() -> None:
    raw = canonical_bytes(build(GOLDEN[1]["fields"]))
    assert "ṢADÉ ỌLÁ".encode() in raw and b"\\u" not in raw


def test_offset_times_are_converted_to_utc_and_floored_to_the_second() -> None:
    fields = dict(GOLDEN[1]["fields"])
    assert b'"expires_at":"2026-10-21T10:02:59Z"' in canonical_bytes(build(fields))


# --- validation: nothing ambiguous gets through ---


def base() -> Intent:
    return build(GOLDEN[0]["fields"])


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "100"])
def test_amount_must_be_a_positive_integer(bad: object) -> None:
    with pytest.raises(ValueError):
        replace(base(), amount_kobo=bad)  # type: ignore[arg-type]


def test_nonce_must_be_16_bytes_and_time_must_have_a_zone() -> None:
    with pytest.raises(ValueError):
        replace(base(), nonce=b"short")
    with pytest.raises(ValueError):
        replace(base(), expires_at=datetime(2026, 10, 21, 10, 2))


# --- hypothesis: any change to what matters changes the hash ---

uuids = st.uuids(version=4)
accounts = st.from_regex(r"[0-9]{10}", fullmatch=True)
names = st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != "")
amounts = st.integers(min_value=1, max_value=10**13)
nonces = st.binary(min_size=16, max_size=16)
moments = st.datetimes(
    min_value=datetime(2026, 1, 1), max_value=datetime(2030, 1, 1), timezones=st.just(UTC)
)


@st.composite
def intents(draw: st.DrawFn) -> Intent:
    return Intent(
        request_id=draw(uuids), customer_id=draw(uuids), payee_account=draw(accounts),
        payee_bank_code=draw(st.sampled_from(["057", "058", "044", "100004"])),
        payee_name=draw(names), amount_kobo=draw(amounts), currency="NGN",
        nonce=draw(nonces), expires_at=draw(moments),
    )  # fmt: skip


@settings(max_examples=300, deadline=None)
@given(intents())
def test_hashing_is_deterministic_and_32_bytes(i: Intent) -> None:
    assert intent_hash(i) == intent_hash(replace(i)) and len(intent_hash(i)) == 32
    assert json.loads(canonical_bytes(i))["amount_kobo"] == i.amount_kobo  # stays an integer
    assert isinstance(json.loads(canonical_bytes(i))["amount_kobo"], int)


@settings(max_examples=300, deadline=None)
@given(intents(), amounts)
def test_any_change_of_amount_changes_the_hash(i: Intent, other: int) -> None:
    if other != i.amount_kobo:
        assert intent_hash(replace(i, amount_kobo=other)) != intent_hash(i)


@settings(max_examples=300, deadline=None)
@given(intents(), accounts, names)
def test_any_change_of_payee_changes_the_hash(i: Intent, account: str, name: str) -> None:
    if account != i.payee_account:
        assert intent_hash(replace(i, payee_account=account)) != intent_hash(i)
    if name != i.payee_name:
        assert intent_hash(replace(i, payee_name=name)) != intent_hash(i)


@settings(max_examples=300, deadline=None)
@given(intents(), st.integers(min_value=1, max_value=10**6))
def test_any_change_of_expiry_beyond_a_second_changes_the_hash(i: Intent, seconds: int) -> None:
    assert intent_hash(
        replace(i, expires_at=i.expires_at + timedelta(seconds=seconds))
    ) != intent_hash(i)


@settings(max_examples=300, deadline=None)
@given(intents(), uuids, nonces)
def test_ids_and_nonce_are_bound_too(i: Intent, other: uuid.UUID, nonce: bytes) -> None:
    if other != i.request_id:
        assert intent_hash(replace(i, request_id=other)) != intent_hash(i)
    if other != i.customer_id:
        assert intent_hash(replace(i, customer_id=other)) != intent_hash(i)
    if nonce != i.nonce:
        assert intent_hash(replace(i, nonce=nonce)) != intent_hash(i)


@settings(max_examples=200, deadline=None)
@given(intents(), st.integers(min_value=0, max_value=999_999))
def test_sub_second_noise_in_the_expiry_does_not_change_the_hash(i: Intent, micros: int) -> None:
    floored = i.expires_at.replace(microsecond=0)
    assert intent_hash(
        replace(i, expires_at=floored + timedelta(microseconds=micros))
    ) == intent_hash(replace(i, expires_at=floored))
