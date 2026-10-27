
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Bid(Base):
    __tablename__ = "bids"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_bids_amount_positive",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    lot_id: Mapped[int] = mapped_column(
        ForeignKey("lots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    bidder_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
