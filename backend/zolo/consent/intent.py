"""Canonical intent (version 1) and its SHA-256 hash.

The passkey signs this hash, and approval recomputes it from the database row. If the amount,
payee, expiry or anything else in the row changed after the customer heard it, the hashes differ
and nothing is sent.

Serialisation: keys sorted, no whitespace, UTF-8, money as integers only, UTC timestamps with a
`Z` and whole seconds, the nonce as unpadded base64url. Do not change any of this without
bumping `v`: stored hashes and golden fixtures depend on these exact bytes.
"""

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

INTENT_VERSION = 1
NONCE_BYTES = 16


@dataclass(frozen=True)
class Intent:
    request_id: uuid.UUID
    customer_id: uuid.UUID
    payee_account: str
    payee_bank_code: str
    payee_name: str
    amount_kobo: int
    currency: str
    nonce: bytes
    expires_at: datetime

    def __post_init__(self) -> None:
        # Refuse anything that could make two different requests serialise identically.
        if isinstance(self.amount_kobo, bool) or not isinstance(self.amount_kobo, int):
            raise ValueError("amount_kobo must be an integer")
        if self.amount_kobo <= 0:
            raise ValueError("amount_kobo must be positive")
        if len(self.nonce) != NONCE_BYTES:
            raise ValueError("nonce must be 16 bytes")
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_bytes(intent: Intent) -> bytes:
    document = {
        "v": INTENT_VERSION,
        "request_id": str(intent.request_id),
        "customer_id": str(intent.customer_id),
        "payee_account": intent.payee_account,
        "payee_bank_code": intent.payee_bank_code,
        "payee_name": intent.payee_name,
        "amount_kobo": intent.amount_kobo,
        "currency": intent.currency,
        "nonce": base64.urlsafe_b64encode(intent.nonce).rstrip(b"=").decode("ascii"),
        "expires_at": _timestamp(intent.expires_at),
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def intent_hash(intent: Intent) -> bytes:
    """SHA-256 of the canonical bytes: 32 bytes, used as the WebAuthn challenge."""
    return hashlib.sha256(canonical_bytes(intent)).digest()
