
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    BID_RESERVE = "bid_reserve"
    BID_RELEASE = "bid_release"
    AUCTION_PAYMENT = "auction_payment"
    REFUND = "refund"


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_wallet_transactions_amount_positive",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    lot_id: Mapped[int | None] = mapped_column(
        ForeignKey("lots.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="wallet_transaction_type"),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
