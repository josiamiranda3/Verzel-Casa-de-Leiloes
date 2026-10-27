
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LotStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class Lot(Base):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(primary_key=True)

    auctioneer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(1000))

    initial_bid: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )

    minimum_increment: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )

    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    status: Mapped[LotStatus] = mapped_column(
        Enum(LotStatus, name="lot_status"),
        default=LotStatus.SCHEDULED,
        nullable=False,
    )
