import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from zolo.core.base import Base

STAGES = ("menu", "pin", "done")


class PhoneEnrolment(Base):
    """One customer's phone number and Zolo PIN (never a card or bank PIN). Only a salted hash of
    the PIN is kept."""

    __tablename__ = "phone_enrolments"
    __table_args__ = (
        CheckConstraint("language IN ('en', 'pcm')", name="language_known"),
        CheckConstraint("failed_attempts >= 0", name="failed_attempts_non_negative"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), primary_key=True)
    phone_e164: Mapped[str] = mapped_column(Text, unique=True)
    language: Mapped[str] = mapped_column(Text, server_default="en")
    pin_hash: Mapped[bytes] = mapped_column(LargeBinary)
    failed_attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # set only when an enrolled number is replaced; the cooling-off period runs from here
    phone_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PhoneCall(Base):
    __tablename__ = "phone_calls"
    __table_args__ = (
        CheckConstraint(f"stage IN ({', '.join(repr(s) for s in STAGES)})", name="stage_known"),
        CheckConstraint(
            "heard_hash IS NULL OR octet_length(heard_hash) = 32", name="heard_hash_sha256"
        ),
        Index("ix_phone_calls_request_id", "request_id"),
        # at most one live call per request
        Index(
            "uq_phone_calls_one_live_per_request",
            "request_id",
            unique=True,
            postgresql_where=text("stage <> 'done'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment_requests.id"))
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"))
    stage: Mapped[str] = mapped_column(Text, server_default="menu")
    heard_hash: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    pin_used: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
