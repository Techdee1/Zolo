"""initial schema: the Backend PRD data model plus saved_recipients (and agents.phone)

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=True),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"], unique=False)
    # Append-only: the trail cannot be edited or deleted row by row. (TRUNCATE is still allowed,
    # which is how the demo reset starts a clean slate.)
    op.execute("""
        CREATE FUNCTION audit_events_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER audit_events_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()
    """)
    op.create_table(
        "customers",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), server_default="en", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "language IN ('en', 'pcm', 'yo', 'ha', 'ig')", name=op.f("ck_customers_language_known")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("phone", name=op.f("uq_customers_phone")),
    )
    op.create_table(
        "bank_accounts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("agent_id", sa.UUID(), nullable=True),
        sa.Column("account_number", sa.CHAR(length=10), nullable=False),
        sa.Column("bank_code", sa.Text(), nullable=False),
        sa.Column("verified_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "account_number ~ '^[0-9]{10}$'", name=op.f("ck_bank_accounts_account_number_10_digits")
        ),
        sa.CheckConstraint(
            "bank_code ~ '^[0-9]{2,6}$'", name=op.f("ck_bank_accounts_bank_code_digits")
        ),
        sa.CheckConstraint(
            "NOT (customer_id IS NOT NULL AND agent_id IS NOT NULL)",
            name=op.f("ck_bank_accounts_one_owner"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_bank_accounts_customer_id_customers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_accounts")),
        sa.UniqueConstraint(
            "account_number", "bank_code", name=op.f("uq_bank_accounts_account_number")
        ),
    )
    op.create_table(
        "card_guard_windows",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("card_ref", sa.Text(), nullable=False),
        sa.Column("max_amount_kobo", sa.BigInteger(), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "closes_at > opens_at", name=op.f("ck_card_guard_windows_closes_after_opens")
        ),
        sa.CheckConstraint(
            "max_amount_kobo > 0", name=op.f("ck_card_guard_windows_max_amount_positive")
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_card_guard_windows_customer_id_customers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_card_guard_windows")),
    )
    op.create_table(
        "passkey_credentials",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("transports", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("device_label", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "sign_count >= 0", name=op.f("ck_passkey_credentials_sign_count_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_passkey_credentials_customer_id_customers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passkey_credentials")),
        sa.UniqueConstraint("credential_id", name=op.f("uq_passkey_credentials_credential_id")),
    )
    op.create_index(
        "ix_passkey_credentials_customer_id", "passkey_credentials", ["customer_id"], unique=False
    )
    op.create_table(
        "risk_limits",
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("per_payment_kobo", sa.BigInteger(), nullable=False),
        sa.Column("daily_kobo", sa.BigInteger(), nullable=False),
        sa.Column("new_payee_kobo", sa.BigInteger(), nullable=False),
        sa.Column("call_channel_kobo", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "call_channel_kobo > 0", name=op.f("ck_risk_limits_call_channel_positive")
        ),
        sa.CheckConstraint("daily_kobo > 0", name=op.f("ck_risk_limits_daily_positive")),
        sa.CheckConstraint("new_payee_kobo > 0", name=op.f("ck_risk_limits_new_payee_positive")),
        sa.CheckConstraint(
            "per_payment_kobo > 0", name=op.f("ck_risk_limits_per_payment_positive")
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_risk_limits_customer_id_customers")
        ),
        sa.PrimaryKeyConstraint("customer_id", name=op.f("pk_risk_limits")),
    )
    op.create_table(
        "saved_recipients",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("bank_code", sa.Text(), nullable=False),
        sa.Column("account_number", sa.CHAR(length=10), nullable=False),
        sa.Column("account_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "account_number ~ '^[0-9]{10}$'",
            name=op.f("ck_saved_recipients_account_number_10_digits"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_saved_recipients_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_recipients")),
        sa.UniqueConstraint(
            "customer_id",
            "bank_code",
            "account_number",
            name=op.f("uq_saved_recipients_customer_id"),
        ),
    )
    op.create_index(
        "ix_saved_recipients_customer_id", "saved_recipients", ["customer_id"], unique=False
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("business_name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["bank_accounts.id"],
            name="fk_agents_account_id_bank_accounts",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agents")),
        sa.UniqueConstraint("phone", name=op.f("uq_agents_phone")),
    )
    # bank_accounts and agents reference each other: add this side once both exist
    op.create_foreign_key(
        "fk_bank_accounts_agent_id_agents", "bank_accounts", "agents", ["agent_id"], ["id"]
    )
    op.create_table(
        "payment_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("initiator", sa.Text(), nullable=False),
        sa.Column("payee_account_id", sa.UUID(), nullable=False),
        sa.Column("payee_verified_name", sa.Text(), nullable=False),
        sa.Column("amount_kobo", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), server_default="NGN", nullable=False),
        sa.Column("claim_code", sa.CHAR(length=4), nullable=True),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("intent_hash", sa.LargeBinary(), nullable=True),
        sa.Column("idempotency_key", sa.UUID(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), server_default="app", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bank_reference", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "channel IN ('app', 'call')", name=op.f("ck_payment_requests_channel_known")
        ),
        sa.CheckConstraint(
            "claim_code ~ '^[0-9]{4}$'", name=op.f("ck_payment_requests_claim_code_4_digits")
        ),
        sa.CheckConstraint("currency = 'NGN'", name=op.f("ck_payment_requests_currency_ngn")),
        sa.CheckConstraint(
            "initiator IN ('agent', 'customer', 'ai')",
            name=op.f("ck_payment_requests_initiator_known"),
        ),
        sa.CheckConstraint(
            "state <> 'FAILED' OR failure_reason IS NOT NULL",
            name=op.f("ck_payment_requests_failed_has_reason"),
        ),
        sa.CheckConstraint(
            "state <> 'SETTLED' OR (bank_reference IS NOT NULL AND settled_at IS NOT NULL)",
            name=op.f("ck_payment_requests_settled_has_reference"),
        ),
        sa.CheckConstraint(
            "state IN ('CREATED', 'READ_BACK', 'APPROVED', 'SUBMITTED', 'SETTLED', 'DECLINED', 'EXPIRED', 'FAILED')",
            name=op.f("ck_payment_requests_state_known"),
        ),
        sa.CheckConstraint(
            "state NOT IN ('APPROVED', 'SUBMITTED', 'SETTLED') OR approved_at IS NOT NULL",
            name=op.f("ck_payment_requests_signed_has_time"),
        ),
        sa.CheckConstraint(
            "state NOT IN ('READ_BACK', 'APPROVED', 'SUBMITTED', 'SETTLED') OR customer_id IS NOT NULL",
            name=op.f("ck_payment_requests_heard_has_customer"),
        ),
        sa.CheckConstraint(
            "state NOT IN ('READ_BACK', 'APPROVED', 'SUBMITTED', 'SETTLED') OR intent_hash IS NOT NULL",
            name=op.f("ck_payment_requests_heard_has_hash"),
        ),
        sa.CheckConstraint("amount_kobo > 0", name=op.f("ck_payment_requests_amount_positive")),
        sa.CheckConstraint(
            "intent_hash IS NULL OR octet_length(intent_hash) = 32",
            name=op.f("ck_payment_requests_intent_hash_sha256"),
        ),
        sa.CheckConstraint(
            "octet_length(nonce) = 16", name=op.f("ck_payment_requests_nonce_16_bytes")
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_payment_requests_customer_id_customers"),
        ),
        sa.ForeignKeyConstraint(
            ["payee_account_id"],
            ["bank_accounts.id"],
            name=op.f("fk_payment_requests_payee_account_id_bank_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_requests")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_payment_requests_idempotency_key")),
        sa.UniqueConstraint("nonce", name=op.f("uq_payment_requests_nonce")),
    )
    op.create_index(
        "ix_payment_requests_customer_created",
        "payment_requests",
        ["customer_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ux_payment_requests_live_claim_code",
        "payment_requests",
        ["claim_code"],
        unique=True,
        postgresql_where=sa.text("state IN ('CREATED', 'READ_BACK')"),
    )
    op.create_table(
        "webauthn_challenges",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=True),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("challenge", sa.LargeBinary(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('register', 'authenticate')",
            name=op.f("ck_webauthn_challenges_purpose_known"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_webauthn_challenges_customer_id_customers"),
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["payment_requests.id"],
            name=op.f("fk_webauthn_challenges_request_id_payment_requests"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webauthn_challenges")),
    )
    op.create_index(
        "ix_webauthn_challenges_request_id", "webauthn_challenges", ["request_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_webauthn_challenges_request_id", table_name="webauthn_challenges")
    op.drop_table("webauthn_challenges")
    op.drop_index(
        "ux_payment_requests_live_claim_code",
        table_name="payment_requests",
        postgresql_where=sa.text("state IN ('CREATED', 'READ_BACK')"),
    )
    op.drop_index("ix_payment_requests_customer_created", table_name="payment_requests")
    op.drop_table("payment_requests")
    op.drop_constraint("fk_bank_accounts_agent_id_agents", "bank_accounts", type_="foreignkey")
    op.drop_table("agents")
    op.drop_index("ix_saved_recipients_customer_id", table_name="saved_recipients")
    op.drop_table("saved_recipients")
    op.drop_table("risk_limits")
    op.drop_index("ix_passkey_credentials_customer_id", table_name="passkey_credentials")
    op.drop_table("passkey_credentials")
    op.drop_table("card_guard_windows")
    op.drop_table("bank_accounts")
    op.drop_table("customers")
    op.execute("DROP TRIGGER audit_events_no_update_delete ON audit_events")
    op.execute("DROP FUNCTION audit_events_append_only()")
    op.drop_index("ix_audit_events_request_id", table_name="audit_events")
    op.drop_table("audit_events")
