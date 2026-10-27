
"""Protect audit actor references.

Revision ID: 13848bb9d5b4
Revises: 3e4e6292c770
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "13848bb9d5b4"
down_revision: Union[str, Sequence[str], None] = "3e4e6292c770"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Prevent deleting users referenced by audit events."""
    op.drop_constraint(
        "audit_events_actor_user_id_fkey",
        "audit_events",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "audit_events_actor_user_id_fkey",
        "audit_events",
        "users",
        ["actor_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Restore the previous SET NULL behavior."""
    op.drop_constraint(
        "audit_events_actor_user_id_fkey",
        "audit_events",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "audit_events_actor_user_id_fkey",
        "audit_events",
        "users",
        ["actor_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
