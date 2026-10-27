from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class PublicAuditedBid(BaseModel):
    bidder_label: str
    amount: Decimal
    created_at: datetime


class PublicAuditIntegrity(BaseModel):
    valid: bool
    message: str
    checked_events: int


class PublicLotAuditResponse(BaseModel):
    lot_id: int
    integrity: PublicAuditIntegrity
    bids: list[PublicAuditedBid]



from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.audit_event import AuditEvent, AuditEventType
from app.models.bid import Bid
from app.models.lot import Lot
from app.schemas.audit import (
    PublicAuditedBid,
    PublicAuditIntegrity,
    PublicLotAuditResponse,
)
from app.services.audit_service import verify_audit_chain


router = APIRouter(prefix="/audit", tags=["Auditoria"])


@router.get(
    "/lots/{lot_id}",
    response_model=PublicLotAuditResponse,
)
def get_public_lot_audit(
    lot_id: int,
    db: Session = Depends(get_db),
):
    lot = db.get(Lot, lot_id)

    if lot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lote não encontrado.",
        )

    integrity_result = verify_audit_chain(db)

    bids = list(
        db.scalars(
            select(Bid)
            .where(Bid.lot_id == lot_id)
            .order_by(Bid.created_at.asc(), Bid.id.asc())
        ).all()
    )

    # Pseudônimos estáveis dentro da auditoria deste lote.
    bidder_labels: dict[int, str] = {}

    public_bids = []

    for bid in bids:
        if bid.bidder_id not in bidder_labels:
            bidder_labels[bid.bidder_id] = (
                f"Licitante {len(bidder_labels) + 1}"
            )

        public_bids.append(
            PublicAuditedBid(
                bidder_label=bidder_labels[bid.bidder_id],
                amount=bid.amount,
                created_at=bid.created_at,
            )
        )

    return PublicLotAuditResponse(
        lot_id=lot.id,
        integrity=PublicAuditIntegrity(
            valid=integrity_result["valid"],
            message=(
                "Cadeia de auditoria íntegra."
                if integrity_result["valid"]
                else "Adulteração ou inconsistência detectada na cadeia de auditoria."
            ),
            checked_events=integrity_result["checked_events"],
        ),
        bids=public_bids,
    )
