"""mock bank ledger

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21 10:12:46.570303
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mock_accounts",
        sa.Column("account_number", sa.CHAR(length=10), nullable=False),
        sa.Column("bank_code", sa.Text(), nullable=False),
        sa.Column("account_name", sa.Text(), nullable=False),
        sa.Column("balance_kobo", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "account_number ~ '^[0-9]{10}$'", name=op.f("ck_mock_accounts_account_number_10_digits")
        ),
        sa.CheckConstraint("balance_kobo >= 0", name=op.f("ck_mock_accounts_balance_non_negative")),
        sa.PrimaryKeyConstraint("account_number", "bank_code", name=op.f("pk_mock_accounts")),
    )
    op.create_table(
        "mock_transfers",
        sa.Column("idempotency_key", sa.UUID(), nullable=False),
        sa.Column("from_account", sa.CHAR(length=10), nullable=False),
        sa.Column("to_account", sa.CHAR(length=10), nullable=False),
        sa.Column("to_bank", sa.Text(), nullable=False),
        sa.Column("amount_kobo", sa.BigInteger(), nullable=False),
        sa.Column("narration", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status <> 'REJECTED' OR reason IS NOT NULL",
            name=op.f("ck_mock_transfers_rejected_has_reason"),
        ),
        sa.CheckConstraint(
            "status <> 'SUCCESS' OR reference IS NOT NULL",
            name=op.f("ck_mock_transfers_success_has_reference"),
        ),
        sa.CheckConstraint(
            "status IN ('SUCCESS', 'REJECTED')", name=op.f("ck_mock_transfers_status_known")
        ),
        sa.CheckConstraint("amount_kobo > 0", name=op.f("ck_mock_transfers_amount_positive")),
        sa.PrimaryKeyConstraint("idempotency_key", name=op.f("pk_mock_transfers")),
        sa.UniqueConstraint("reference", name=op.f("uq_mock_transfers_reference")),
    )


def downgrade() -> None:
    op.drop_table("mock_transfers")
    op.drop_table("mock_accounts")
