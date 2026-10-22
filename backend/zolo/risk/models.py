import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from zolo.core.base import Base


class RiskLimit(Base):
    __tablename__ = "risk_limits"
    __table_args__ = (
        CheckConstraint("per_payment_kobo > 0", name="per_payment_positive"),
        CheckConstraint("daily_kobo > 0", name="daily_positive"),
        CheckConstraint("new_payee_kobo > 0", name="new_payee_positive"),
        CheckConstraint("call_channel_kobo > 0", name="call_channel_positive"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), primary_key=True)
    per_payment_kobo: Mapped[int] = mapped_column(BigInteger)
    daily_kobo: Mapped[int] = mapped_column(BigInteger)
    new_payee_kobo: Mapped[int] = mapped_column(BigInteger)
    call_channel_kobo: Mapped[int] = mapped_column(BigInteger)


class CardGuardWindow(Base):
    """Phase 2+. Created now so the schema matches the PRD; nothing writes to it in Phase 1."""

    __tablename__ = "card_guard_windows"
    __table_args__ = (
        CheckConstraint("max_amount_kobo > 0", name="max_amount_positive"),
        CheckConstraint("closes_at > opens_at", name="closes_after_opens"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"))
    card_ref: Mapped[str] = mapped_column(Text)
    max_amount_kobo: Mapped[int] = mapped_column(BigInteger)
    opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
