
import enum

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditEventType(str, enum.Enum):
    USER_REGISTERED = "USER_REGISTERED"
    LOT_CREATED = "LOT_CREATED"
    LOT_STATUS_CHANGED = "LOT_STATUS_CHANGED"
    BID_PLACED = "BID_PLACED"
    BID_REJECTED = "BID_REJECTED"
    WALLET_TRANSACTION = "WALLET_TRANSACTION"
    AUCTION_SETTLED = "AUCTION_SETTLED"


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )

    event_type: Mapped[AuditEventType] = mapped_column(
        Enum(
            AuditEventType,
            name="audit_event_type",
            values_callable=lambda enum_cls: [
                item.value for item in enum_cls
            ],
            create_constraint=False,
        ),
        nullable=False,
    )

    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    entity_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    event_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )

    previous_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    event_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "event_hash",
            name="uq_audit_events_event_hash",
        ),
        Index(
            "ix_audit_events_entity",
            "entity_type",
            "entity_id",
        ),
        Index(
            "ix_audit_events_created_at",
            "created_at",
        ),
        Index(
            "ix_audit_events_event_type",
            "event_type",
        ),
    )
