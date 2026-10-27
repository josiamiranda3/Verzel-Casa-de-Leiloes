from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent, AuditEventType
from app.models.bid import Bid
from app.models.lot import Lot, LotStatus
from app.models.user import User
from app.models.wallet import Wallet
from app.models.wallet_transaction import (
    TransactionType,
    WalletTransaction,
)
from app.services.audit_service import record_event


def settle_auction(
    db: Session,
    *,
    lot_id: int,
    actor: User,
) -> dict:
    """
    Liquida um leilão encerrado, transferindo o valor do arremate
    da carteira do vencedor para a carteira do leiloeiro responsável.

    Todas as alterações financeiras, transações e eventos de auditoria
    são persistidos na mesma transação do banco de dados.
    """

    # Bloqueia o lote para impedir duas liquidações simultâneas.
    lot = db.scalar(
        select(Lot)
        .where(Lot.id == lot_id)
        .with_for_update()
    )

    if lot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lote não encontrado.",
        )

    # Somente o leiloeiro responsável pode liquidar o próprio lote.
    if lot.auctioneer_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Somente o leiloeiro responsável pode liquidar este lote.",
        )

    # Encerramento do prazo e liquidação financeira são etapas distintas.
    # Um lote fechado ainda pode ser liquidado se houver lances e se a
    # liquidação ainda não tiver sido registrada.
    settled_event = db.scalar(
        select(AuditEvent.id)
        .where(
            AuditEvent.entity_type == "lot",
            AuditEvent.entity_id == lot.id,
            AuditEvent.event_type == AuditEventType.AUCTION_SETTLED,
        )
        .limit(1)
    )
    if settled_event is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este lote já foi liquidado.",
        )

    # Lotes cancelados não podem ser liquidados.
    if lot.status == LotStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Não é possível liquidar um lote cancelado.",
        )

    # Trata datas com e sem informação de fuso horário.
    now = datetime.now(timezone.utc)
    ends_at = lot.ends_at

    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=timezone.utc)

    # O prazo do leilão precisa ter terminado.
    if now < ends_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O prazo do leilão ainda não terminou.",
        )

    try:
        # Seleciona o maior lance usando os mesmos critérios de desempate
        # empregados na consulta dos lances.
        winning_bid = db.scalar(
            select(Bid)
            .where(Bid.lot_id == lot.id)
            .order_by(
                Bid.amount.desc(),
                Bid.created_at.desc(),
                Bid.id.desc(),
            )
            .limit(1)
        )

        old_status = lot.status

        # Caso não existam lances, encerra o lote sem movimentar carteiras.
        if winning_bid is None:
            lot.status = LotStatus.CLOSED

            record_event(
                db,
                event_type=AuditEventType.LOT_STATUS_CHANGED,
                actor_user_id=actor.id,
                entity_type="lot",
                entity_id=lot.id,
                description="Lote encerrado sem lances.",
                event_data={
                    "old_status": old_status.value,
                    "new_status": LotStatus.CLOSED.value,
                },
                commit=False,
            )

            record_event(
                db,
                event_type=AuditEventType.AUCTION_SETTLED,
                actor_user_id=actor.id,
                entity_type="lot",
                entity_id=lot.id,
                description="Leilão encerrado sem vencedor.",
                event_data={
                    "lot_id": lot.id,
                    "winner_id": None,
                    "bid_id": None,
                    "amount": None,
                    "commission": "0.00",
                },
                commit=False,
            )

            db.commit()

            return {
                "lot_id": lot.id,
                "status": lot.status.value,
                "winner_id": None,
                "winning_amount": None,
            }

        amount = winning_bid.amount

        # Bloqueia as carteiras em ordem consistente para reduzir
        # o risco de deadlocks entre operações financeiras.
        user_ids = sorted(
            {
                lot.auctioneer_id,
                winning_bid.bidder_id,
            }
        )

        wallets = db.scalars(
            select(Wallet)
            .where(Wallet.user_id.in_(user_ids))
            .order_by(Wallet.user_id)
            .with_for_update()
        ).all()

        wallets_by_user = {
            wallet.user_id: wallet
            for wallet in wallets
        }

        seller_wallet = wallets_by_user.get(lot.auctioneer_id)
        winner_wallet = wallets_by_user.get(winning_bid.bidder_id)

        # Contas de leiloeiro criadas antes da criação automática de
        # carteiras podem não ter uma linha em wallets. Cria a carteira
        # do responsável dentro da mesma transação, com saldo inicial zero.
        # A carteira do vencedor não é criada automaticamente: ela precisa
        # conter saldo e reserva compatíveis com o lance vencedor.
        if seller_wallet is None:
            seller_wallet = Wallet(user_id=lot.auctioneer_id)
            db.add(seller_wallet)
            db.flush()

        if winner_wallet is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Carteira do arrematante vencedor não encontrada. "
                    "Verifique o cadastro da carteira e tente novamente."
                ),
            )
        # As duas carteiras precisam ser distintas.
        if seller_wallet.id == winner_wallet.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "As carteiras do vencedor e do leiloeiro são inválidas."
                ),
            )

        # Verifica o saldo disponível e a reserva agregada da carteira.
        # A reserva pode ser maior que este lance caso o vencedor também
        # esteja liderando outros leilões.
        if (
            winner_wallet.balance < amount
            or winner_wallet.committed_balance < amount
            or winner_wallet.committed_balance > winner_wallet.balance
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Saldo ou reserva do vencedor inconsistente.",
            )

        # 1. Debita o valor do arremate do saldo do vencedor.
        winner_wallet.balance -= amount

        # 2. Consome a reserva correspondente a este arremate.
        # Outras reservas do mesmo usuário são preservadas.
        winner_wallet.committed_balance -= amount

        # 3. Credita o valor integral ao leiloeiro, sem comissão.
        seller_wallet.balance += amount

        # Registra as duas movimentações financeiras.
        db.add_all(
            [
                WalletTransaction(
                    wallet_id=winner_wallet.id,
                    lot_id=lot.id,
                    transaction_type=TransactionType.AUCTION_PAYMENT,
                    amount=amount,
                    description=(
                        f"Pagamento do arremate do lote {lot.id}."
                    ),
                ),
                WalletTransaction(
                    wallet_id=seller_wallet.id,
                    lot_id=lot.id,
                    transaction_type=TransactionType.AUCTION_PAYMENT,
                    amount=amount,
                    description=(
                        f"Recebimento do arremate do lote {lot.id}."
                    ),
                ),
            ]
        )

        # Marca o lote como encerrado dentro da mesma transação.
        lot.status = LotStatus.CLOSED

        # Auditoria do débito realizado na carteira do vencedor.
        record_event(
            db,
            event_type=AuditEventType.WALLET_TRANSACTION,
            actor_user_id=actor.id,
            entity_type="wallet",
            entity_id=winner_wallet.id,
            description="Pagamento do arremate debitado do vencedor.",
            event_data={
                "lot_id": lot.id,
                "winner_id": winning_bid.bidder_id,
                "bid_id": winning_bid.id,
                "transaction_type": (
                    TransactionType.AUCTION_PAYMENT.value
                ),
                "amount": format(amount, "f"),
                "direction": "debit",
            },
            commit=False,
        )

        # Auditoria do crédito realizado na carteira do leiloeiro.
        record_event(
            db,
            event_type=AuditEventType.WALLET_TRANSACTION,
            actor_user_id=actor.id,
            entity_type="wallet",
            entity_id=seller_wallet.id,
            description="Valor do arremate creditado ao leiloeiro.",
            event_data={
                "lot_id": lot.id,
                "winner_id": winning_bid.bidder_id,
                "bid_id": winning_bid.id,
                "transaction_type": (
                    TransactionType.AUCTION_PAYMENT.value
                ),
                "amount": format(amount, "f"),
                "direction": "credit",
            },
            commit=False,
        )

        # Auditoria da mudança de status do lote.
        record_event(
            db,
            event_type=AuditEventType.LOT_STATUS_CHANGED,
            actor_user_id=actor.id,
            entity_type="lot",
            entity_id=lot.id,
            description="Lote encerrado após a liquidação.",
            event_data={
                "old_status": old_status.value,
                "new_status": LotStatus.CLOSED.value,
            },
            commit=False,
        )

        # Evento final que registra a liquidação do leilão.
        record_event(
            db,
            event_type=AuditEventType.AUCTION_SETTLED,
            actor_user_id=actor.id,
            entity_type="lot",
            entity_id=lot.id,
            description="Leilão liquidado com sucesso.",
            event_data={
                "lot_id": lot.id,
                "winner_id": winning_bid.bidder_id,
                "bid_id": winning_bid.id,
                "amount": format(amount, "f"),
                "commission": "0.00",
            },
            commit=False,
        )

        # Confirma conjuntamente as alterações financeiras,
        # as transações, o status e os eventos de auditoria.
        db.commit()

        return {
            "lot_id": lot.id,
            "status": lot.status.value,
            "winner_id": winning_bid.bidder_id,
            "winning_amount": amount,
        }

    except Exception:
        # Se qualquer etapa falhar, desfaz as alterações pendentes.
        db.rollback()
        raise