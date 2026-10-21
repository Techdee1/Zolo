"""A software WebAuthn authenticator for tests: a real P-256 key that builds real registration
and assertion responses, so every check in py_webauthn runs for real. It can also misbehave on
purpose (wrong origin, no user verification, bad signature, stale counter)."""

import hashlib
import json
import os
import struct
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

FLAG_UP, FLAG_UV, FLAG_AT = 0x01, 0x04, 0x40


class SoftwareAuthenticator:
    def __init__(self, rp_id: str = "localhost", origin: str = "http://localhost:3000") -> None:
        self.rp_id, self.origin = rp_id, origin
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(16)
        self.sign_count = 0
        self.counter_mode = "increment"  # increment | zero | frozen

    # --------------------------------------------------------------- helpers

    def _rp_hash(self, rp_id: str | None = None) -> bytes:
        return hashlib.sha256((rp_id or self.rp_id).encode()).digest()

    def _client_data(self, kind: str, challenge: bytes, origin: str | None = None) -> bytes:
        return json.dumps(
            {
                "type": kind,
                "challenge": bytes_to_base64url(challenge),
                "origin": origin or self.origin,
                "crossOrigin": False,
            },
            separators=(",", ":"),
        ).encode()

    def _cose_key(self) -> bytes:
        n = self.key.public_key().public_numbers()
        return cbor2.dumps(
            {1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, "big"), -3: n.y.to_bytes(32, "big")}
        )

    def _next_count(self) -> int:
        if self.counter_mode == "zero":
            return 0
        if self.counter_mode == "increment":
            self.sign_count += 1
        return self.sign_count

    # --------------------------------------------------------------- registration

    def register(self, options: dict[str, Any], *, origin: str | None = None) -> dict[str, Any]:
        challenge = base64url_to_bytes(options["challenge"])
        flags = FLAG_UP | FLAG_UV | FLAG_AT
        auth_data = (
            self._rp_hash(options.get("rp", {}).get("id"))
            + bytes([flags])
            + struct.pack(">I", 0)
            + b"\x00" * 16
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + self._cose_key()
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        cid = bytes_to_base64url(self.credential_id)
        return {
            "id": cid,
            "rawId": cid,
            "type": "public-key",
            "authenticatorAttachment": "platform",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": bytes_to_base64url(
                    self._client_data("webauthn.create", challenge, origin)
                ),
                "attestationObject": bytes_to_base64url(attestation),
                "transports": ["internal"],
            },
        }

    # --------------------------------------------------------------- assertion

    def assert_(
        self,
        options: dict[str, Any] | None = None,
        *,
        challenge: bytes | None = None,
        origin: str | None = None,
        rp_id: str | None = None,
        user_verified: bool = True,
        corrupt_signature: bool = False,
        key: ec.EllipticCurvePrivateKey | None = None,
        sign_count: int | None = None,
    ) -> dict[str, Any]:
        if challenge is None:
            assert options is not None
            challenge = base64url_to_bytes(options["challenge"])
        count = self._next_count() if sign_count is None else sign_count
        flags = FLAG_UP | (FLAG_UV if user_verified else 0)
        auth_data = self._rp_hash(rp_id) + bytes([flags]) + struct.pack(">I", count)
        client_data = self._client_data("webauthn.get", challenge, origin)
        signature = (key or self.key).sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        if corrupt_signature:
            signature = signature[:-1] + bytes([signature[-1] ^ 0xFF])
        cid = bytes_to_base64url(self.credential_id)
        return {
            "id": cid,
            "rawId": cid,
            "type": "public-key",
            "clientExtensionResults": {},
            "response": {
                "authenticatorData": bytes_to_base64url(auth_data),
                "clientDataJSON": bytes_to_base64url(client_data),
                "signature": bytes_to_base64url(signature),
                "userHandle": None,
            },
        }
