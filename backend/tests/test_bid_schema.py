import pytest
from pydantic import ValidationError

from app.schemas.bids import BidCreate


def test_bid_accepts_positive_amount():
    bid = BidCreate(lot_id=1, amount="100.00")

    assert bid.lot_id == 1
    assert bid.amount == "100.00" or bid.amount == 100


@pytest.mark.parametrize(
    "lot_id, amount",
    [
        (0, "100.00"),
        (-1, "100.00"),
        (1, "0"),
        (1, "-10.00"),
    ],
)
def test_bid_rejects_invalid_values(lot_id, amount):
    with pytest.raises(ValidationError):
        BidCreate(lot_id=lot_id, amount=amount)