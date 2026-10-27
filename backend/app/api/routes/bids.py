
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.audit_event import AuditEventType
from app.models.bid import Bid
from app.models.lot import Lot, LotStatus
from app.models.user import User, UserRole
from app.models.wallet import Wallet
from app.models.wallet_transaction import (
    TransactionType,
    WalletTransaction,
)
from app.schemas.bids import (
    BidCreate,
    BidResponse,
    PublicBidResponse,
)
from app.services.audit_service import record_event


router = APIRouter(prefix="/bids", tags=["Lances"])


@router.post(
    "/",
    response_model=BidResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_bid(
    data: BidCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.BIDDER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Somente arrematantes podem ofertar lances.",
        )

    # Bloqueia o lote para serializar os lances concorrentes.
    lot = db.scalar(
        select(Lot)
        .where(Lot.id == data.lot_id)
        .with_for_update()
    )

    if lot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lote não encontrado.",
        )

    # Captura o horário somente depois de adquirir o bloqueio.
    # Assim, o prazo é validado com base no horário atual,
    # mesmo quando a requisição precisou esperar outra transação.
    now = datetime.now(timezone.utc)

    if lot.auctioneer_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não pode dar lances no próprio lote.",
        )

    if lot.status in (LotStatus.CLOSED, LotStatus.CANCELLED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este lote não está aceitando lances.",
        )

    if now < lot.starts_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O leilão ainda não começou.",
        )

    if now >= lot.ends_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O prazo para lances deste lote terminou.",
        )

    highest_bid = db.scalar(
        select(Bid)
        .where(Bid.lot_id == lot.id)
        .order_by(
            Bid.amount.desc(),
            Bid.created_at.desc(),
            Bid.id.desc(),
        )
        .limit(1)
    )

    minimum_allowed = (
        lot.initial_bid
        if highest_bid is None
        else highest_bid.amount + lot.minimum_increment
    )

    if data.amount < minimum_allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"O lance mínimo permitido é {minimum_allowed:.2f}.",
        )

    # Bloqueia as carteiras em ordem de usuário para reduzir
    # o risco de deadlocks em lances concorrentes.
    user_ids = {current_user.id}

    if highest_bid is not None:
        user_ids.add(highest_bid.bidder_id)

    wallets = db.scalars(
        select(Wallet)
        .where(Wallet.user_id.in_(sorted(user_ids)))
        .order_by(Wallet.user_id)
        .with_for_update()
    ).all()

    wallets_by_user = {
        wallet.user_id: wallet for wallet in wallets
    }

    bidder_wallet = wallets_by_user.get(current_user.id)

    if bidder_wallet is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Carteira do arrematante não encontrada.",
        )

    previous_leader_wallet = None

    if highest_bid is not None:
        previous_leader_wallet = wallets_by_user.get(
            highest_bid.bidder_id
        )

        if previous_leader_wallet is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Carteira do líder atual não encontrada.",
            )

    # O edital do desafio proíbe que o líder cubra o próprio lance.
    same_leader = (
        highest_bid is not None
        and highest_bid.bidder_id == current_user.id
    )
    if same_leader:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Você já está liderando este leilão e não pode cobrir o próprio lance.",
        )

    reserve_amount = (
        data.amount - highest_bid.amount
        if same_leader
        else data.amount
    )

    available_balance = (
        bidder_wallet.balance
        - bidder_wallet.committed_balance
    )

    if available_balance < reserve_amount:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Saldo disponível insuficiente para cobrir o lance.",
        )

    # Confere a consistência da reserva do líder anterior.
    if (
        highest_bid is not None
        and not same_leader
        and previous_leader_wallet.committed_balance
        < highest_bid.amount
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A reserva da carteira do líder está inconsistente. "
                "O lance não foi registrado."
            ),
        )

    # Todas as alterações financeiras, criação do lance,
    # auditoria e commit ficam protegidos pelo mesmo bloco.
    try:
        # Atualiza o status de um lote agendado que já começou.
        status_changed = lot.status == LotStatus.SCHEDULED

        if status_changed:
            lot.status = LotStatus.LIVE

        # Libera a reserva do líder que foi superado.
        if highest_bid is not None and not same_leader:
            previous_leader_wallet.committed_balance -= (
                highest_bid.amount
            )

            db.add(
                WalletTransaction(
                    wallet_id=previous_leader_wallet.id,
                    lot_id=lot.id,
                    transaction_type=TransactionType.BID_RELEASE,
                    amount=highest_bid.amount,
                    description=(
                        f"Reserva liberada após ser superado "
                        f"no lote {lot.id}."
                    ),
                )
            )

            record_event(
                db,
                event_type=AuditEventType.WALLET_TRANSACTION,
                actor_user_id=current_user.id,
                entity_type="wallet",
                entity_id=previous_leader_wallet.id,
                description=(
                    "Reserva liberada após o arrematante ser superado."
                ),
                event_data={
                    "lot_id": lot.id,
                    "previous_bidder_id": highest_bid.bidder_id,
                    "transaction_type": TransactionType.BID_RELEASE.value,
                    "amount": format(highest_bid.amount, "f"),
                },
                commit=False,
            )

        # Reserva o valor do novo lance ou somente sua diferença.
        bidder_wallet.committed_balance += reserve_amount

        db.add(
            WalletTransaction(
                wallet_id=bidder_wallet.id,
                lot_id=lot.id,
                transaction_type=TransactionType.BID_RESERVE,
                amount=reserve_amount,
                description=f"Reserva para lance no lote {lot.id}.",
            )
        )

        bid = Bid(
            lot_id=lot.id,
            bidder_id=current_user.id,
            amount=data.amount,
        )

        db.add(bid)
        db.flush()

        if status_changed:
            record_event(
                db,
                event_type=AuditEventType.LOT_STATUS_CHANGED,
                actor_user_id=current_user.id,
                entity_type="lot",
                entity_id=lot.id,
                description="Lote passou de agendado para em andamento.",
                event_data={
                    "old_status": LotStatus.SCHEDULED.value,
                    "new_status": LotStatus.LIVE.value,
                },
                commit=False,
            )

        record_event(
            db,
            event_type=AuditEventType.BID_PLACED,
            actor_user_id=current_user.id,
            entity_type="bid",
            entity_id=bid.id,
            description=f"Lance registrado no lote {lot.id}.",
            event_data={
                "lot_id": lot.id,
                "bidder_id": current_user.id,
                "amount": format(data.amount, "f"),
                "reserved_amount": format(reserve_amount, "f"),
            },
            commit=False,
        )

        record_event(
            db,
            event_type=AuditEventType.WALLET_TRANSACTION,
            actor_user_id=current_user.id,
            entity_type="wallet",
            entity_id=bidder_wallet.id,
            description="Saldo reservado para um lance.",
            event_data={
                "lot_id": lot.id,
                "transaction_type": TransactionType.BID_RESERVE.value,
                "amount": format(reserve_amount, "f"),
            },
            commit=False,
        )

        # Anti-sniping: um lance nos dois minutos finais prorroga o
        # encerramento em dois minutos. O lote está bloqueado nesta transação.
        remaining_seconds = (lot.ends_at - now).total_seconds()
        if 0 < remaining_seconds <= 120:
            previous_end = lot.ends_at
            lot.ends_at = previous_end + timedelta(minutes=2)
            record_event(
                db,
                event_type=AuditEventType.LOT_STATUS_CHANGED,
                actor_user_id=current_user.id,
                entity_type="lot",
                entity_id=lot.id,
                description="Encerramento prorrogado por anti-sniping.",
                event_data={
                    "reason": "bid_in_final_two_minutes",
                    "previous_ends_at": previous_end.isoformat(),
                    "new_ends_at": lot.ends_at.isoformat(),
                    "bid_id": bid.id,
                },
                commit=False,
            )

        db.commit()
        db.refresh(bid)

        return bid

    except Exception:
        db.rollback()
        raise


@router.get(
    "/lot/{lot_id}",
    response_model=list[PublicBidResponse],
)
def list_lot_bids(
    lot_id: int,
    db: Session = Depends(get_db),
):
    lot = db.get(Lot, lot_id)

    if lot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lote não encontrado.",
        )

    return list(
        db.scalars(
            select(Bid)
            .where(Bid.lot_id == lot_id)
            .order_by(Bid.amount.desc(), Bid.created_at.asc())
        ).all()
    )


@router.get("/lot/{lot_id}/my-position")
def my_lot_position(
    lot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna apenas ao usuário autenticado sua posição, sem expor identidades."""
    lot = db.get(Lot, lot_id)
    if lot is None:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    if current_user.role != UserRole.BIDDER:
        raise HTTPException(status_code=403, detail="Somente arrematantes podem consultar sua posição.")
    highest_bid = db.scalar(
        select(Bid).where(Bid.lot_id == lot_id)
        .order_by(Bid.amount.desc(), Bid.created_at.desc(), Bid.id.desc()).limit(1)
    )
    own_highest = db.scalar(
        select(Bid).where(Bid.lot_id == lot_id, Bid.bidder_id == current_user.id)
        .order_by(Bid.amount.desc(), Bid.created_at.desc(), Bid.id.desc()).limit(1)
    )
    return {
        "lot_id": lot_id,
        "has_bid": own_highest is not None,
        "is_winning": own_highest is not None and highest_bid is not None and own_highest.id == highest_bid.id,
        "own_highest_bid": own_highest.amount if own_highest else None,
        "minimum_next_bid": (highest_bid.amount + lot.minimum_increment) if highest_bid else lot.initial_bid,
    }
