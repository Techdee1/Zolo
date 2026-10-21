"""WebAuthn registration and assertion verification, and the credential and challenge storage.

The approval challenge IS the request's intent hash, so a valid signature covers that exact
amount and payee. This module verifies signatures; the consent module decides what they mean.
"""

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.exceptions import InvalidJSONStructure, WebAuthnException
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from zolo.audit.service import record
from zolo.core.config import Settings
from zolo.core.errors import ApiError, ErrorCode
from zolo.passkeys.models import PasskeyCredential, WebAuthnChallenge

log = logging.getLogger("zolo.passkeys")
REGISTRATION_TTL = timedelta(minutes=5)
_TRANSPORTS = {t.value for t in AuthenticatorTransport}


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class RegisteredPasskey:
    id: uuid.UUID
    device_label: str | None
    replaced_previous: bool


@dataclass(frozen=True)
class VerifiedAssertion:
    credential_pk: uuid.UUID
    new_sign_count: int


class SignatureInvalid(ApiError):
    """The client only ever sees SIGNATURE_INVALID. `reason` is for the server's own logs and
    audit trail and never goes into a response."""

    def __init__(self, reason: str) -> None:
        super().__init__(401, ErrorCode.SIGNATURE_INVALID, "The passkey signature is not valid")
        self.reason = reason


# Why py_webauthn refused, by the start of its message. Only the code we choose is ever
# recorded; the message itself can contain the attacker's origin or other payload data.
_REASONS = (
    ("Unexpected client data origin", "wrong_origin"),
    ("Unexpected RP ID hash", "wrong_rp"),
    ("User verification is required", "uv_missing"),
    ("User was not present", "up_missing"),
    ("Client data challenge was not expected", "wrong_challenge"),
    ("Could not verify authentication signature", "bad_signature"),
    ("Unexpected client data type", "wrong_type"),
)


def reason_for(exc: Exception) -> str:
    if isinstance(exc, InvalidJSONStructure):
        return "malformed_assertion"
    message = str(exc)
    for prefix, reason in _REASONS:
        if message.startswith(prefix):
            return reason
    if "malformed" in message or "raw_id" in message:
        return "malformed_assertion"
    return "invalid_response"


def _reject(reason: str) -> SignatureInvalid:
    log.warning("signature rejected", extra={"event": "signature_invalid", "code": reason})
    return SignatureInvalid(reason)


class PasskeyService:
    def __init__(self, settings: Settings, clock: Callable[[], datetime] = utcnow) -> None:
        self.settings, self.clock = settings, clock

    # ------------------------------------------------------------------ helpers

    async def active_credentials(
        self, session: AsyncSession, customer_id: uuid.UUID
    ) -> list[PasskeyCredential]:
        return list(
            (
                await session.execute(
                    select(PasskeyCredential).where(
                        PasskeyCredential.customer_id == customer_id,
                        PasskeyCredential.revoked_at.is_(None),
                    )
                )
            ).scalars()
        )

    async def has_passkey(self, session: AsyncSession, customer_id: uuid.UUID) -> bool:
        return bool(await self.active_credentials(session, customer_id))

    @staticmethod
    def _descriptor(cred: PasskeyCredential) -> PublicKeyCredentialDescriptor:
        transports = [
            AuthenticatorTransport(t) for t in (cred.transports or []) if t in _TRANSPORTS
        ]
        return PublicKeyCredentialDescriptor(id=cred.credential_id, transports=transports or None)

    # ------------------------------------------------------------------ registration

    async def registration_options(
        self, session: AsyncSession, customer_id: uuid.UUID, user_name: str, display_name: str
    ) -> dict[str, Any]:
        """Options for navigator.credentials.create(): platform authenticator, resident key
        preferred, user verification required, no attestation."""
        existing = await self.active_credentials(session, customer_id)
        options = generate_registration_options(
            rp_id=self.settings.rp_id,
            rp_name=self.settings.rp_name,
            user_id=customer_id.bytes,
            user_name=user_name,
            user_display_name=display_name,
            attestation=AttestationConveyancePreference.NONE,
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=[self._descriptor(c) for c in existing],
        )
        # Only the latest registration attempt can complete.
        await session.execute(
            delete(WebAuthnChallenge).where(
                WebAuthnChallenge.customer_id == customer_id,
                WebAuthnChallenge.purpose == "register",
                WebAuthnChallenge.used_at.is_(None),
            )
        )
        session.add(
            WebAuthnChallenge(
                customer_id=customer_id,
                challenge=options.challenge,
                purpose="register",
                expires_at=self.clock() + REGISTRATION_TTL,
            )
        )
        await record(
            session,
            "passkey.registration_started",
            f"customer:{customer_id}",
            customer_id=customer_id,
        )
        await session.commit()
        return json.loads(options_to_json(options))  # type: ignore[no-any-return]

    async def verify_registration(
        self,
        session: AsyncSession,
        customer_id: uuid.UUID,
        credential: dict[str, Any],
        device_label: str | None = None,
    ) -> RegisteredPasskey:
        """Verify the browser's answer and store the passkey. One active passkey per customer
        in Phase 1: registering again revokes the previous one."""
        now = self.clock()
        challenge = (
            await session.execute(
                select(WebAuthnChallenge)
                .where(
                    WebAuthnChallenge.customer_id == customer_id,
                    WebAuthnChallenge.purpose == "register",
                    WebAuthnChallenge.used_at.is_(None),
                    WebAuthnChallenge.expires_at > now,
                )
                .order_by(WebAuthnChallenge.expires_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if challenge is None:
            raise ApiError(409, ErrorCode.CHALLENGE_NOT_FOUND, "Start registration first")
        try:
            verified = verify_registration_response(
                credential=credential,
                expected_challenge=challenge.challenge,
                expected_rp_id=self.settings.rp_id,
                expected_origin=self.settings.origins,
                require_user_verification=True,
            )
        except (WebAuthnException, ValueError, KeyError, TypeError) as exc:
            log.warning(
                "registration rejected",
                extra={"event": "registration_failed", "code": reason_for(exc)},
            )
            await record(
                session,
                "passkey.registration_failed",
                f"customer:{customer_id}",
                customer_id=customer_id,
            )
            await session.commit()
            raise ApiError(
                400, ErrorCode.PASSKEY_REGISTRATION_FAILED, "Could not register the passkey"
            ) from None

        used = await session.execute(
            update(WebAuthnChallenge)
            .where(WebAuthnChallenge.id == challenge.id, WebAuthnChallenge.used_at.is_(None))
            .values(used_at=now)
            .returning(WebAuthnChallenge.id)
        )
        if used.first() is None:  # two registrations raced on one challenge
            await session.rollback()
            raise ApiError(409, ErrorCode.STATE_CONFLICT, "Registration was already completed")

        previous = await self.active_credentials(session, customer_id)
        for old in previous:
            old.revoked_at = now
        transports = [
            t for t in credential.get("response", {}).get("transports", []) if t in _TRANSPORTS
        ]
        row = PasskeyCredential(
            customer_id=customer_id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            transports=transports or None,
            device_label=device_label,
        )
        session.add(row)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise ApiError(
                409, ErrorCode.STATE_CONFLICT, "That passkey is already registered"
            ) from None
        await record(
            session, "passkey.registered", f"customer:{customer_id}", customer_id=customer_id,
            replaced=bool(previous),
        )  # fmt: skip
        await session.commit()
        return RegisteredPasskey(row.id, device_label, replaced_previous=bool(previous))

    # ------------------------------------------------------------------ approval challenge

    async def issue_challenge(
        self,
        session: AsyncSession,
        customer_id: uuid.UUID,
        request_id: uuid.UUID,
        challenge: bytes,
        expires_at: datetime,
    ) -> dict[str, Any]:
        """Authentication options whose challenge is `challenge` (the intent hash). Only one
        unused challenge exists per request: asking again replaces the earlier one."""
        credentials = await self.active_credentials(session, customer_id)
        if not credentials:
            raise ApiError(409, ErrorCode.NO_PASSKEY, "Register a passkey first")
        await session.execute(
            delete(WebAuthnChallenge).where(
                WebAuthnChallenge.request_id == request_id,
                WebAuthnChallenge.purpose == "authenticate",
                WebAuthnChallenge.used_at.is_(None),
            )
        )
        session.add(
            WebAuthnChallenge(
                request_id=request_id,
                customer_id=customer_id,
                challenge=challenge,
                purpose="authenticate",
                expires_at=expires_at,  # a challenge never outlives its request
            )
        )
        options = generate_authentication_options(
            rp_id=self.settings.rp_id,
            challenge=challenge,
            allow_credentials=[self._descriptor(c) for c in credentials],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        return json.loads(options_to_json(options))  # type: ignore[no-any-return]

    async def current_challenge(
        self, session: AsyncSession, request_id: uuid.UUID
    ) -> WebAuthnChallenge | None:
        return (
            await session.execute(
                select(WebAuthnChallenge)
                .where(
                    WebAuthnChallenge.request_id == request_id,
                    WebAuthnChallenge.purpose == "authenticate",
                    WebAuthnChallenge.used_at.is_(None),
                    WebAuthnChallenge.expires_at > self.clock(),
                )
                .order_by(WebAuthnChallenge.expires_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def challenge_was_used(self, session: AsyncSession, request_id: uuid.UUID) -> bool:
        return (
            await session.execute(
                select(WebAuthnChallenge.id).where(
                    WebAuthnChallenge.request_id == request_id,
                    WebAuthnChallenge.purpose == "authenticate",
                    WebAuthnChallenge.used_at.is_not(None),
                )
            )
        ).first() is not None

    async def consume_challenge(self, session: AsyncSession, challenge_id: uuid.UUID) -> bool:
        """Mark the challenge used. False if someone else already did (single use)."""
        done = await session.execute(
            update(WebAuthnChallenge)
            .where(WebAuthnChallenge.id == challenge_id, WebAuthnChallenge.used_at.is_(None))
            .values(used_at=self.clock())
            .returning(WebAuthnChallenge.id)
        )
        return done.first() is not None

    # ------------------------------------------------------------------ assertion

    async def verify_assertion(
        self,
        session: AsyncSession,
        customer_id: uuid.UUID,
        expected_challenge: bytes,
        assertion: dict[str, Any],
    ) -> VerifiedAssertion:
        """Check a signed assertion against the customer's own active passkey.

        Wrong credential, wrong challenge, wrong origin or RP ID, missing user verification, a
        bad signature and a stale signature counter all end in SIGNATURE_INVALID, with no hint
        of which, so a probe learns nothing.
        """
        try:
            raw_id = base64url_to_bytes(str(assertion["rawId"]))
        except (KeyError, ValueError, TypeError):
            raise _reject("malformed_assertion") from None
        if not raw_id:  # base64url decoding is lenient: junk can decode to nothing
            raise _reject("malformed_assertion")
        credential = (
            await session.execute(
                select(PasskeyCredential).where(
                    PasskeyCredential.credential_id == raw_id,
                    PasskeyCredential.customer_id == customer_id,
                    PasskeyCredential.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if credential is None:
            raise _reject("revoked_or_foreign_passkey")
        try:
            verified = verify_authentication_response(
                credential=assertion,
                expected_challenge=expected_challenge,
                expected_rp_id=self.settings.rp_id,
                expected_origin=self.settings.origins,
                credential_public_key=credential.public_key,
                # py_webauthn's own counter rule is always strict; we apply ours below, so the
                # strictness can be a setting. 0 here turns its check off.
                credential_current_sign_count=0,
                require_user_verification=True,
            )
        except (WebAuthnException, ValueError, KeyError, TypeError) as exc:
            raise _reject(reason_for(exc)) from None
        self._check_counter(credential.sign_count, verified.new_sign_count)
        return VerifiedAssertion(credential.id, verified.new_sign_count)

    def _check_counter(self, stored: int, new: int) -> None:
        """Zero stays zero (many platform passkeys never count). Otherwise the count must go up.
        Backwards is always refused. Equal and non-zero is refused when strict, and allowed with
        a warning when not (demo environments)."""
        if new == 0 and stored == 0:
            return
        if new > stored:
            return
        if new == stored and not self.settings.webauthn_strict_counter:
            log.warning(
                "signature counter did not increase (allowed: strict counter is off)",
                extra={"event": "counter_not_increased", "code": "equal_counter"},
            )
            return
        raise _reject("stale_counter")

    async def record_use(
        self, session: AsyncSession, credential_pk: uuid.UUID, new_sign_count: int
    ) -> None:
        await session.execute(
            update(PasskeyCredential)
            .where(PasskeyCredential.id == credential_pk)
            .values(sign_count=new_sign_count)
        )
