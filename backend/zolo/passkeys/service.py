"""WebAuthn registration and assertion verification, and the credential and challenge storage.

The approval challenge IS the request's intent hash, so a valid signature covers that exact
amount and payee. This module verifies signatures; the consent module decides what they mean.
"""

import json
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
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
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


def _signature_invalid() -> ApiError:
    return ApiError(401, ErrorCode.SIGNATURE_INVALID, "The passkey signature is not valid")


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
        except (InvalidRegistrationResponse, ValueError, KeyError, TypeError):
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
            raise _signature_invalid() from None
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
            raise _signature_invalid()
        try:
            verified = verify_authentication_response(
                credential=assertion,
                expected_challenge=expected_challenge,
                expected_rp_id=self.settings.rp_id,
                expected_origin=self.settings.origins,
                credential_public_key=credential.public_key,
                credential_current_sign_count=credential.sign_count,
                require_user_verification=True,
            )
        except (InvalidAuthenticationResponse, ValueError, KeyError, TypeError):
            raise _signature_invalid() from None
        return VerifiedAssertion(credential.id, verified.new_sign_count)

    async def record_use(
        self, session: AsyncSession, credential_pk: uuid.UUID, new_sign_count: int
    ) -> None:
        await session.execute(
            update(PasskeyCredential)
            .where(PasskeyCredential.id == credential_pk)
            .values(sign_count=new_sign_count)
        )
