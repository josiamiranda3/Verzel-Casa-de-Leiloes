
"""create audit events

Revision ID: 3e4e6292c770
Revises: a6e4b37858a3
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "3e4e6292c770"
down_revision: Union[str, Sequence[str], None] = "a6e4b37858a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

audit_event_type = postgresql.ENUM(
    "USER_REGISTERED",
    "LOT_CREATED",
    "LOT_STATUS_CHANGED",
    "BID_PLACED",
    "BID_REJECTED",
    "WALLET_TRANSACTION",
    "AUCTION_SETTLED",
    name="audit_event_type",
    create_type=False,
)


def upgrade() -> None:
    audit_event_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("event_type", audit_event_type, nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "event_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("previous_hash", sa.String(length=64), nullable=True),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("event_hash", name="uq_audit_events_event_hash"),
    )

    op.create_index(
        "ix_audit_events_created_at",
        "audit_events",
        ["created_at"],
    )
    op.create_index(
        "ix_audit_events_entity",
        "audit_events",
        ["entity_type", "entity_id"],
    )
    op.create_index(
        "ix_audit_events_event_type",
        "audit_events",
        ["event_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_entity", table_name="audit_events")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")
    audit_event_type.drop(op.get_bind(), checkfirst=True)
