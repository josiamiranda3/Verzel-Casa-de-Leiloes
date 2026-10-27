from datetime import datetime, timezone
from decimal import Decimal
import httpx

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.bid import Bid
from app.models.audit_event import AuditEvent, AuditEventType
from app.models.lot import Lot, LotStatus
from app.services.audit_service import record_event
from app.models.user import User, UserRole
from app.schemas.lots import LotCreate, LotResponse
from app.services.auction_settlement import settle_auction


router = APIRouter(prefix="/lots", tags=["Lotes"])


def _synchronize_time_based_statuses(db: Session, lots: list[Lot]) -> None:
    """
    Sincroniza o status persistido com o período já definido para cada lote.
    Lotes expirados sem lances passam pelo serviço de liquidação existente,
    que os encerra e registra a auditoria sem movimentar carteiras.
    Lotes com lances continuam dependendo do fluxo explícito de liquidação.
    """
    now = datetime.now(timezone.utc)

    for lot in lots:
        if lot.status in (LotStatus.CLOSED, LotStatus.CANCELLED):
            continue

        starts_at = lot.starts_at
        ends_at = lot.ends_at
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=timezone.utc)
        if ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=timezone.utc)

        if ends_at <= now:
            # Não alterar o mecanismo de lances nem liquidar pagamentos aqui.
            # O serviço existente já trata o encerramento sem lances de forma
            # transacional, com eventos de auditoria e sem transações financeiras.
            has_bid = db.scalar(
                select(Bid.id).where(Bid.lot_id == lot.id).limit(1)
            )
            if has_bid is None:
                auctioneer = db.get(User, lot.auctioneer_id)
                if auctioneer is not None:
                    settle_auction(db, lot_id=lot.id, actor=auctioneer)
            elif lot.status != LotStatus.CLOSED:
                # O prazo de ofertas terminou. Encerrar o lote não liquida
                # o arremate: a transferência financeira continua explícita.
                old_status = lot.status
                lot.status = LotStatus.CLOSED
                record_event(
                    db,
                    event_type=AuditEventType.LOT_STATUS_CHANGED,
                    actor_user_id=lot.auctioneer_id,
                    entity_type="lot",
                    entity_id=lot.id,
                    description="Lote encerrado após o prazo de ofertas; aguardando liquidação.",
                    event_data={
                        "old_status": old_status.value,
                        "new_status": LotStatus.CLOSED.value,
                        "has_bids": True,
                        "settled": False,
                    },
                    commit=False,
                )
                db.commit()
                db.refresh(lot)
            continue

        if starts_at <= now < ends_at and lot.status == LotStatus.SCHEDULED:
            old_status = lot.status
            lot.status = LotStatus.LIVE
            record_event(
                db,
                event_type=AuditEventType.LOT_STATUS_CHANGED,
                actor_user_id=lot.auctioneer_id,
                entity_type="lot",
                entity_id=lot.id,
                description="Lote aberto automaticamente conforme o horário programado.",
                event_data={
                    "old_status": old_status.value,
                    "new_status": LotStatus.LIVE.value,
                },
                commit=False,
            )
            db.commit()
            db.refresh(lot)


@router.get("/", response_model=list[LotResponse])
def list_lots(
    lot_status: LotStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
):
    # Sincroniza estados vencidos antes de aplicar filtros por status, para
    # que lotes expirados não permaneçam presos em "scheduled".
    all_lots = list(db.scalars(select(Lot).order_by(Lot.starts_at.asc())).all())
    _synchronize_time_based_statuses(db, all_lots)

    visible_lots = [
        lot for lot in all_lots
        if (
            lot.status == lot_status
            if lot_status is not None
            else lot.status != LotStatus.CANCELLED
        )
    ]
    return visible_lots




@router.get("/external/search")
def search_external_items(
    q: str = Query(min_length=2, max_length=120),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Busca livros na API pública Open Library para apoiar a criação de lotes."""
    if current_user.role != UserRole.AUCTIONEER:
        raise HTTPException(status_code=403, detail="Somente leiloeiros podem buscar itens para lotes.")
    try:
        response = httpx.get(
            "https://openlibrary.org/search.json",
            params={"q": q, "limit": 8, "fields": "key,title,author_name,first_publish_year,cover_i"},
            timeout=5.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A API externa está indisponível no momento. Tente novamente mais tarde.",
        )
    items = []
    for item in payload.get("docs", []):
        key = item.get("key")
        title = item.get("title")
        if not key or not title:
            continue
        cover_id = item.get("cover_i")
        items.append({
            "external_id": key,
            "title": title,
            "authors": item.get("author_name", [])[:3],
            "year": item.get("first_publish_year"),
            "image_url": f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None,
            "source_url": f"https://openlibrary.org{key}",
        })
    return {"source": "Open Library", "items": items}


@router.post("/{lot_id}/cancel", status_code=status.HTTP_200_OK)
def cancel_lot(
    lot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancela lote do próprio leiloeiro apenas se não houver lances."""
    if current_user.role != UserRole.AUCTIONEER:
        raise HTTPException(status_code=403, detail="Somente leiloeiros podem cancelar lotes.")
    lot = db.scalar(select(Lot).where(Lot.id == lot_id).with_for_update())
    if lot is None:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    if lot.auctioneer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Você só pode cancelar seus próprios lotes.")
    if lot.status in (LotStatus.CLOSED, LotStatus.CANCELLED):
        raise HTTPException(status_code=409, detail="O lote já foi encerrado ou cancelado.")
    bid_count = db.scalar(select(Bid.id).where(Bid.lot_id == lot.id).limit(1))
    if bid_count is not None:
        raise HTTPException(status_code=409, detail="Não é possível cancelar um lote que já recebeu lances.")
    old_status = lot.status
    lot.status = LotStatus.CANCELLED
    record_event(
        db,
        event_type=AuditEventType.LOT_STATUS_CHANGED,
        actor_user_id=current_user.id,
        entity_type="lot",
        entity_id=lot.id,
        description="Lote cancelado pelo leiloeiro antes de receber lances.",
        event_data={"old_status": old_status.value, "new_status": LotStatus.CANCELLED.value},
        commit=False,
    )
    db.commit()
    db.refresh(lot)
    return {"lot_id": lot.id, "status": lot.status.value}


@router.get("/mine/managed")
def list_my_lots(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.AUCTIONEER:
        raise HTTPException(status_code=403, detail="Somente leiloeiros podem consultar seus lotes.")
    managed_lots = list(
        db.scalars(
            select(Lot)
            .where(Lot.auctioneer_id == current_user.id)
            .order_by(Lot.starts_at.desc())
        ).all()
    )
    _synchronize_time_based_statuses(db, managed_lots)
    result = []
    total_received = Decimal("0.00")
    for managed_lot in managed_lots:
        winning_bid = db.scalar(
            select(Bid)
            .where(Bid.lot_id == managed_lot.id)
            .order_by(Bid.amount.desc(), Bid.created_at.desc(), Bid.id.desc())
            .limit(1)
        )
        is_settled = db.scalar(
            select(AuditEvent.id)
            .where(
                AuditEvent.entity_type == "lot",
                AuditEvent.entity_id == managed_lot.id,
                AuditEvent.event_type == AuditEventType.AUCTION_SETTLED,
            )
            .limit(1)
        ) is not None
        winning_amount = winning_bid.amount if winning_bid else None
        if is_settled and winning_amount is not None:
            total_received += winning_amount
        result.append({
            "id": managed_lot.id,
            "auctioneer_id": managed_lot.auctioneer_id,
            "title": managed_lot.title,
            "description": managed_lot.description,
            "image_url": managed_lot.image_url,
            "initial_bid": managed_lot.initial_bid,
            "minimum_increment": managed_lot.minimum_increment,
            "starts_at": managed_lot.starts_at,
            "ends_at": managed_lot.ends_at,
            "status": managed_lot.status.value,
            "winner_reference": "Arrematante vencedor" if is_settled and winning_bid else None,
            "winning_amount": winning_amount if is_settled else None,
            "is_settled": is_settled,
        })
    return {"lots": result, "total_received": total_received}


@router.get("/{lot_id}/receipt")
def get_public_receipt(lot_id: int, db: Session = Depends(get_db)):
    """Comprovante público sem dados pessoais; disponível após o encerramento."""
    lot = db.get(Lot, lot_id)
    if lot is None:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    if lot.status != LotStatus.CLOSED:
        raise HTTPException(status_code=409, detail="O comprovante fica disponível após o encerramento.")
    settled_event = db.scalar(
        select(AuditEvent.id)
        .where(
            AuditEvent.entity_type == "lot",
            AuditEvent.entity_id == lot_id,
            AuditEvent.event_type == AuditEventType.AUCTION_SETTLED,
        ).limit(1)
    )
    if settled_event is None:
        raise HTTPException(status_code=409, detail="O lote foi encerrado, mas a liquidação ainda não foi registrada.")
    bid = db.scalar(select(Bid).where(Bid.lot_id == lot_id).order_by(Bid.amount.desc(), Bid.created_at.desc(), Bid.id.desc()).limit(1))
    return {
        "receipt_id": f"VERZEL-{lot.id}",
        "lot_id": lot.id,
        "lot_title": lot.title,
        "status": lot.status.value,
        "winner_reference": "Arrematante vencedor" if bid else None,
        "winning_amount": bid.amount if bid else None,
        "closed_at": lot.ends_at,
        "message": "Comprovante público de arremate. Dados pessoais do vencedor não são exibidos." if bid else "Lote encerrado sem lances; não houve arrematante.",
    }


@router.get("/mine/wins")
def list_my_wins(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.BIDDER:
        raise HTTPException(status_code=403, detail="Somente arrematantes podem consultar seus arremates.")
    # Só considera lotes fechados e o maior lance do usuário em cada lote.
    wins = []
    closed_lots = db.scalars(select(Lot).where(Lot.status == LotStatus.CLOSED).order_by(Lot.ends_at.desc())).all()
    for lot in closed_lots:
        winning_bid = db.scalar(select(Bid).where(Bid.lot_id == lot.id).order_by(Bid.amount.desc(), Bid.created_at.desc(), Bid.id.desc()).limit(1))
        if winning_bid and winning_bid.bidder_id == current_user.id:
            wins.append({
                "lot_id": lot.id,
                "title": lot.title,
                "winning_amount": winning_bid.amount,
                "ends_at": lot.ends_at,
                "receipt_url": f"/lots/{lot.id}/receipt",
            })
    return wins

@router.get("/{lot_id}", response_model=LotResponse)
def get_lot(
    lot_id: int,
    db: Session = Depends(get_db),
):
    lot = db.get(Lot, lot_id)

    if lot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lote não encontrado.",
        )

    _synchronize_time_based_statuses(db, [lot])
    db.refresh(lot)
    return lot


@router.post(
    "/",
    response_model=LotResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_lot(
    data: LotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.AUCTIONEER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Somente leiloeiros podem criar lotes.",
        )

    now = datetime.now(timezone.utc)

    lot = Lot(
        auctioneer_id=current_user.id,
        title=data.title.strip(),
        description=data.description,
        image_url=str(data.image_url) if data.image_url else None,
        initial_bid=data.initial_bid,
        minimum_increment=data.minimum_increment,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        status=(
            LotStatus.CLOSED if data.ends_at <= now
            else LotStatus.LIVE if data.starts_at <= now < data.ends_at
            else LotStatus.SCHEDULED
        ),
    )

    db.add(lot)
    db.flush()
    record_event(
        db,
        event_type=AuditEventType.LOT_CREATED,
        actor_user_id=current_user.id,
        entity_type="lot",
        entity_id=lot.id,
        description="Lote criado pelo leiloeiro.",
        event_data={
            "title": lot.title,
            "initial_bid": format(lot.initial_bid, "f"),
            "minimum_increment": format(lot.minimum_increment, "f"),
            "starts_at": lot.starts_at.isoformat(),
            "ends_at": lot.ends_at.isoformat(),
        },
        commit=False,
    )
    db.commit()
    db.refresh(lot)

    return lot


@router.post(
    "/{lot_id}/settle",
    status_code=status.HTTP_200_OK,
)
def settle_lot(
    lot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.AUCTIONEER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Somente leiloeiros podem liquidar leilões.",
        )

    return settle_auction(
        db,
        lot_id=lot_id,
        actor=current_user,
    )