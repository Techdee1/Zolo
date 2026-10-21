import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from zolo.consent.states import LIVE_STATES, State
from zolo.core.base import Base


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


_ALL = _in(tuple(s.value for s in State))
_LIVE = _in(tuple(s.value for s in LIVE_STATES))
_HEARD = _in(("READ_BACK", "APPROVED", "SUBMITTED", "SETTLED"))
_SIGNED = _in(("APPROVED", "SUBMITTED", "SETTLED"))


class PaymentRequest(Base):
    __tablename__ = "payment_requests"
    __table_args__ = (
        CheckConstraint("initiator IN ('agent', 'customer', 'ai')", name="initiator_known"),
        CheckConstraint("amount_kobo > 0", name="amount_positive"),
        CheckConstraint("currency = 'NGN'", name="currency_ngn"),
        CheckConstraint("claim_code ~ '^[0-9]{4}$'", name="claim_code_4_digits"),
        CheckConstraint("octet_length(nonce) = 16", name="nonce_16_bytes"),
        CheckConstraint(
            "intent_hash IS NULL OR octet_length(intent_hash) = 32", name="intent_hash_sha256"
        ),
        CheckConstraint(f"state IN ({_ALL})", name="state_known"),
        CheckConstraint("channel IN ('app', 'call')", name="channel_known"),
        # The database refuses states the code could reach by mistake:
        CheckConstraint(
            f"state NOT IN ({_HEARD}) OR customer_id IS NOT NULL", name="heard_has_customer"
        ),
        CheckConstraint(
            f"state NOT IN ({_HEARD}) OR intent_hash IS NOT NULL", name="heard_has_hash"
        ),
        CheckConstraint(
            f"state NOT IN ({_SIGNED}) OR approved_at IS NOT NULL", name="signed_has_time"
        ),
        CheckConstraint(
            "state <> 'SETTLED' OR (bank_reference IS NOT NULL AND settled_at IS NOT NULL)",
            name="settled_has_reference",
        ),
        CheckConstraint(
            "state <> 'FAILED' OR failure_reason IS NOT NULL", name="failed_has_reason"
        ),
        # One live claim code at a time.
        Index(
            "ux_payment_requests_live_claim_code",
            "claim_code",
            unique=True,
            postgresql_where=text(f"state IN ({_LIVE})"),
        ),
        Index("ix_payment_requests_customer_created", "customer_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    initiator: Mapped[str] = mapped_column(Text)
    payee_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bank_accounts.id"))
    payee_verified_name: Mapped[str] = mapped_column(Text)
    amount_kobo: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(CHAR(3), server_default="NGN")
    claim_code: Mapped[str | None] = mapped_column(CHAR(4), nullable=True)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    intent_hash: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    state: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text, server_default="app")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bank_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
