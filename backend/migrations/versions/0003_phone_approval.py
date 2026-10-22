"""phone approval tables and constraints

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Phone Enrolments table
    op.create_table(
        'phone_approval_enrolments',
        sa.Column('customer_id', sa.String(36), primary_key=True),
        sa.Column('phone_e164', sa.String(20), nullable=False, unique=True),
        sa.Column('language', sa.String(10), nullable=False, server_default='en'),
        sa.Column('pin_hash', sa.String(255), nullable=False),
        sa.Column('failed_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('phone_changed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 2. Phone Calls table
    op.create_table(
        'phone_calls',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('request_id', sa.String(36), sa.ForeignKey('payment_requests.id'), nullable=False),
        sa.Column('provider_call_id', sa.String(255), nullable=True),
        sa.Column('public_id', sa.String(64), nullable=False, unique=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='initiated'),
        sa.Column('intent_hash', sa.String(64), nullable=True),
        sa.Column('pin_consumed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('outcome', sa.String(32), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Partial unique index: ensure at most one active/live call per payment request
    op.execute(
        "CREATE UNIQUE INDEX idx_one_live_call_per_request "
        "ON phone_calls (request_id) "
        "WHERE status NOT IN ('completed', 'failed', 'timeout', 'declined')"
    )

    # 3. Alter payment_requests to support phone channel and approval method tracking
    with op.batch_alter_table('payment_requests') as batch_op:
        batch_op.add_column(sa.Column('channel', sa.String(16), nullable=False, server_default='app'))
        batch_op.add_column(sa.Column('approval_method', sa.String(32), nullable=True))
        batch_op.create_check_constraint(
            'chk_payment_requests_channel',
            "channel IN ('app', 'call')"
        )
        batch_op.create_check_constraint(
            'chk_payment_requests_approval_method',
            "approval_method IS NULL OR approval_method IN ('passkey', 'phone_pin')"
        )


def downgrade() -> None:
    with op.batch_alter_table('payment_requests') as batch_op:
        batch_op.drop_constraint('chk_payment_requests_approval_method', type_='check')
        batch_op.drop_constraint('chk_payment_requests_channel', type_='check')
        batch_op.drop_column('approval_method')
        batch_op.drop_column('channel')

    op.execute("DROP INDEX IF EXISTS idx_one_live_call_per_request")
    op.drop_table('phone_calls')
    op.drop_table('phone_approval_enrolments')