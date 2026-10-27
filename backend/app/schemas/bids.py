from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BidCreate(BaseModel):
    lot_id: int = Field(gt=0)
    amount: Decimal = Field(
        gt=0,
        max_digits=14,
        decimal_places=2,
    )


class BidResponse(BaseModel):
    id: int
    lot_id: int
    bidder_id: int
    amount: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)



class PublicBidResponse(BaseModel):
    id: int
    lot_id: int
    amount: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
