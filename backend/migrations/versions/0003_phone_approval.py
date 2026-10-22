"""phone approval

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22 20:09:40.947868
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "phone_enrolments",
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("phone_e164", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), server_default="en", nullable=False),
        sa.Column("pin_hash", sa.LargeBinary(), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phone_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "language IN ('en', 'pcm')", name=op.f("ck_phone_enrolments_language_known")
        ),
        sa.CheckConstraint(
            "failed_attempts >= 0", name=op.f("ck_phone_enrolments_failed_attempts_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_phone_enrolments_customer_id_customers"),
        ),
        sa.PrimaryKeyConstraint("customer_id", name=op.f("pk_phone_enrolments")),
        sa.UniqueConstraint("phone_e164", name=op.f("uq_phone_enrolments_phone_e164")),
    )
    op.create_table(
        "phone_calls",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("stage", sa.Text(), server_default="menu", nullable=False),
        sa.Column("heard_hash", sa.LargeBinary(), nullable=True),
        sa.Column("pin_used", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "stage IN ('menu', 'pin', 'done')", name=op.f("ck_phone_calls_stage_known")
        ),
        sa.CheckConstraint(
            "heard_hash IS NULL OR octet_length(heard_hash) = 32",
            name=op.f("ck_phone_calls_heard_hash_sha256"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_phone_calls_customer_id_customers")
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["payment_requests.id"],
            name=op.f("fk_phone_calls_request_id_payment_requests"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_phone_calls")),
    )
    op.create_index("ix_phone_calls_request_id", "phone_calls", ["request_id"], unique=False)
    op.create_index(
        "uq_phone_calls_one_live_per_request",
        "phone_calls",
        ["request_id"],
        unique=True,
        postgresql_where=sa.text("stage <> 'done'"),
    )
    op.add_column("payment_requests", sa.Column("approval_method", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_payment_requests_approval_method_known"),
        "payment_requests",
        "approval_method IS NULL OR approval_method IN ('passkey', 'phone_pin')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_payment_requests_approval_method_known"), "payment_requests", type_="check"
    )
    op.drop_column("payment_requests", "approval_method")
    op.drop_index(
        "uq_phone_calls_one_live_per_request",
        table_name="phone_calls",
        postgresql_where=sa.text("stage <> 'done'"),
    )
    op.drop_index("ix_phone_calls_request_id", table_name="phone_calls")
    op.drop_table("phone_calls")
    op.drop_table("phone_enrolments")
