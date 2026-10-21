import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from zolo.core.base import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Deferrable: an agent and its account reference each other, so both are inserted in one
    # transaction and checked at commit.
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "bank_accounts.id",
            deferrable=True,
            initially="DEFERRED",
            name="fk_agents_account_id_bank_accounts",
        )
    )
    business_name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text, unique=True)  # needed for mock login; see PRD notes
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
