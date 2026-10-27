
"""create users wallets and lots

Revision ID: a1ac3fa0dd38
Revises:
Create Date: 2026-10-23 16:31:20.673861
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores da migração.
revision: str = "a1ac3fa0dd38"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Enums nomeados para o PostgreSQL.
user_role_enum = sa.Enum(
    "AUCTIONEER",
    "BIDDER",
    name="user_role",
)

lot_status_enum = sa.Enum(
    "SCHEDULED",
    "LIVE",
    "CLOSED",
    "CANCELLED",
    name="lot_status",
)


def upgrade() -> None:
    """Cria as tabelas iniciais da Casa de Leilões."""

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role_enum, nullable=False),
    )

    op.create_index(
        "ix_users_email",
        "users",
        ["email"],
        unique=True,
    )

    op.create_table(
        "lots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("auctioneer_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=1000), nullable=True),
        sa.Column(
            "initial_bid",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
        ),
        sa.Column(
            "minimum_increment",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
        ),
        sa.Column(
            "starts_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "ends_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            lot_status_enum,
            server_default=sa.text("'SCHEDULED'"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["auctioneer_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "initial_bid > 0",
            name="ck_lots_initial_bid_positive",
        ),
        sa.CheckConstraint(
            "minimum_increment > 0",
            name="ck_lots_increment_positive",
        ),
        sa.CheckConstraint(
            "ends_at > starts_at",
            name="ck_lots_end_after_start",
        ),
    )

    op.create_table(
        "wallets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "balance",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "committed_balance",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "user_id",
            name="uq_wallets_user_id",
        ),
        sa.CheckConstraint(
            "balance >= 0",
            name="ck_wallets_balance_nonnegative",
        ),
        sa.CheckConstraint(
            "committed_balance >= 0",
            name="ck_wallets_committed_nonnegative",
        ),
        sa.CheckConstraint(
            "committed_balance <= balance",
            name="ck_wallets_committed_lte_balance",
        ),
    )


def downgrade() -> None:
    """Remove as tabelas na ordem das dependências."""

    op.drop_table("wallets")
    op.drop_table("lots")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    # Remove os tipos ENUM criados no PostgreSQL.
    lot_status_enum.drop(op.get_bind(), checkfirst=True)
    user_role_enum.drop(op.get_bind(), checkfirst=True)
