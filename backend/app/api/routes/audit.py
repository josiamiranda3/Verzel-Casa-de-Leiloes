
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.audit_event import AuditEvent, AuditEventType
from app.models.lot import Lot
from app.schemas.audit import (
    PublicAuditedBid,
    PublicAuditIntegrity,
    PublicLotAuditResponse,
)
from app.services.audit_checkpoint import verify_audit_checkpoint
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

    # Verifica a cadeia de hashes e o checkpoint independente.
    chain_result = verify_audit_chain(db)
    checkpoint_result = verify_audit_checkpoint(db)

    integrity_valid = (
        chain_result["valid"] is True
        and checkpoint_result["valid"] is True
    )

    if integrity_valid:
        integrity_message = (
            "Cadeia de auditoria e checkpoint íntegros."
        )
    elif not chain_result["valid"]:
        integrity_message = (
            "Adulteração ou inconsistência detectada "
            "na cadeia de auditoria."
        )
    else:
        integrity_message = (
            "Integridade não confirmada: "
            "checkpoint ausente, inválido ou divergente."
        )

    events = list(
        db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.event_type == AuditEventType.BID_PLACED,
                AuditEvent.entity_type == "bid",
            )
            .order_by(
                AuditEvent.created_at.asc(),
                AuditEvent.id.asc(),
            )
        ).all()
    )

    # Mantém apenas os eventos pertencentes ao lote consultado.
    lot_events = [
        event
        for event in events
        if isinstance(event.event_data, dict)
        and event.event_data.get("lot_id") == lot_id
    ]

    bidder_labels: dict[int, str] = {}
    public_bids = []
    invalid_bid_event = False

    for event in lot_events:
        event_data = event.event_data or {}
        bidder_id = event_data.get("bidder_id")
        amount_value = event_data.get("amount")

        # Dados obrigatórios ausentes indicam inconsistência.
        if bidder_id is None or amount_value is None:
            invalid_bid_event = True
            continue

        # O ID do participante precisa ser um inteiro positivo.
        if (
            isinstance(bidder_id, bool)
            or not isinstance(bidder_id, int)
            or bidder_id <= 0
        ):
            invalid_bid_event = True
            continue

        try:
            amount = Decimal(str(amount_value))
        except (InvalidOperation, ValueError, TypeError):
            invalid_bid_event = True
            continue

        if not amount.is_finite() or amount <= 0:
            invalid_bid_event = True
            continue

        if bidder_id not in bidder_labels:
            bidder_labels[bidder_id] = (
                f"Licitante {len(bidder_labels) + 1}"
            )

        public_bids.append(
            PublicAuditedBid(
                bidder_label=bidder_labels[bidder_id],
                amount=amount,
                created_at=event.created_at,
            )
        )

    # A cadeia pode ser criptograficamente válida mesmo que os dados
    # de um evento de lance estejam incompletos ou inválidos.
    if invalid_bid_event:
        integrity_valid = False
        integrity_message = (
            "Integridade não confirmada: "
            "foram encontrados eventos de lance com dados inválidos."
        )

    return PublicLotAuditResponse(
        lot_id=lot.id,
        integrity=PublicAuditIntegrity(
            valid=integrity_valid,
            message=integrity_message,
            checked_events=chain_result["checked_events"],
        ),
        bids=public_bids,
    )
