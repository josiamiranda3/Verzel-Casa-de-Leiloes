
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.models.lot import LotStatus


class LotCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = None
    image_url: HttpUrl | None = None
    initial_bid: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    minimum_increment: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def validate_dates(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("As datas devem incluir o fuso horário.")

        if self.ends_at <= self.starts_at:
            raise ValueError("O encerramento deve ocorrer após o início.")

        return self


class LotResponse(BaseModel):
    id: int
    auctioneer_id: int
    title: str
    description: str | None
    image_url: str | None
    initial_bid: Decimal
    minimum_increment: Decimal
    starts_at: datetime
    ends_at: datetime
    status: LotStatus

    model_config = ConfigDict(from_attributes=True)
