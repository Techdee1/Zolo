import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from zolo.ai.types import LANGS  # one list of languages for the whole system
from zolo.core.base import Base

_UUID_DEFAULT = text("gen_random_uuid()")


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint(
            f"language IN ({', '.join(repr(x) for x in LANGS)})", name="language_known"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT
    )
    display_name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text, unique=True)
    language: Mapped[str] = mapped_column(Text, server_default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SavedRecipient(Base):
    """A person the customer pays often. Phase 1 has no endpoints for it; the AI package's
    `DraftService.list_saved_recipients` reads it in Phase 2 (see zolo.voice.recipients)."""

    __tablename__ = "saved_recipients"
    __table_args__ = (
        UniqueConstraint("customer_id", "bank_code", "account_number"),
        CheckConstraint("account_number ~ '^[0-9]{10}$'", name="account_number_10_digits"),
        Index("ix_saved_recipients_customer_id", "customer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    display_name: Mapped[str] = mapped_column(Text)  # what the customer calls them: "My sister"
    bank_code: Mapped[str] = mapped_column(Text)
    account_number: Mapped[str] = mapped_column(CHAR(10))
    account_name: Mapped[str] = mapped_column(Text)  # as verified by name enquiry
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
