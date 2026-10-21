import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from zolo.core.base import Base


class BankAccount(Base):
    """An account at the (mock) bank. Owned by a customer, an agent, or neither (an outside
    account such as a sister's, or the account behind the wrong-recipient demo)."""

    __tablename__ = "bank_accounts"
    __table_args__ = (
        UniqueConstraint("account_number", "bank_code"),
        CheckConstraint("account_number ~ '^[0-9]{10}$'", name="account_number_10_digits"),
        CheckConstraint("bank_code ~ '^[0-9]{2,6}$'", name="bank_code_digits"),
        CheckConstraint("NOT (customer_id IS NOT NULL AND agent_id IS NOT NULL)", name="one_owner"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", use_alter=True, name="fk_bank_accounts_agent_id_agents"),
        nullable=True,
    )
    account_number: Mapped[str] = mapped_column(CHAR(10))
    bank_code: Mapped[str] = mapped_column(Text)
    verified_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
