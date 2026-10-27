
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent, AuditEventType
from app.models.bid import Bid
from app.models.lot import Lot, LotStatus
from app.models.user import User, UserRole
from app.models.wallet import Wallet
from app.models.wallet_transaction import (
    TransactionType,
    WalletTransaction,
)
from app.services import auction_settlement
from tests.conftest import test_engine


def create_user(db_session, name, email, role):
    user = User(
        name=name,
        email=email,
        password_hash="hash-ficticio-apenas-para-teste",
        role=role,
    )
    db_session.add(user)
    db_session.flush()
    return user


def create_wallet(db_session, user, balance, committed_balance="0.00"):
    wallet = Wallet(
        user_id=user.id,
        balance=Decimal(balance),
        committed_balance=Decimal(committed_balance),
    )
    db_session.add(wallet)
    db_session.flush()
    return wallet


def create_lot(
    db_session,
    auctioneer,
    *,
    ends_at=None,
    lot_status=LotStatus.LIVE,
    title="Lote de teste",
):
    now = datetime.now(timezone.utc)

    lot = Lot(
        auctioneer_id=auctioneer.id,
        title=title,
        description="Lote fictício para teste automatizado",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(hours=2),
        ends_at=ends_at or now - timedelta(minutes=1),
        status=lot_status,
    )
    db_session.add(lot)
    db_session.flush()
    return lot


def create_bid(db_session, lot, bidder, amount):
    bid = Bid(
        lot_id=lot.id,
        bidder_id=bidder.id,
        amount=Decimal(amount),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(bid)
    db_session.flush()
    return bid


def test_settlement_transfers_payment_and_preserves_other_reservations(
    db_session,
):
    auctioneer = create_user(
        db_session,
        "Leiloeiro Liquidação",
        "leiloeiro.liquidacao@example.test",
        UserRole.AUCTIONEER,
    )
    winner = create_user(
        db_session,
        "Vencedor Liquidação",
        "vencedor.liquidacao@example.test",
        UserRole.BIDDER,
    )

    seller_wallet = create_wallet(db_session, auctioneer, "100.00")
    winner_wallet = create_wallet(
        db_session,
        winner,
        "1000.00",
        "225.00",
    )

    lot = create_lot(db_session, auctioneer)
    other_lot = create_lot(
        db_session,
        auctioneer,
        ends_at=datetime.now(timezone.utc) + timedelta(hours=1),
        title="Outro lote",
    )

    winning_bid = create_bid(db_session, lot, winner, "150.00")
    create_bid(db_session, other_lot, winner, "75.00")

    result = auction_settlement.settle_auction(
        db_session,
        lot_id=lot.id,
        actor=auctioneer,
    )

    db_session.refresh(lot)
    db_session.refresh(winner_wallet)
    db_session.refresh(seller_wallet)

    assert result["lot_id"] == lot.id
    assert result["status"] == LotStatus.CLOSED.value
    assert result["winner_id"] == winner.id
    assert result["winning_amount"] == Decimal("150.00")

    assert lot.status == LotStatus.CLOSED
    assert winner_wallet.balance == Decimal("850.00")
    assert winner_wallet.committed_balance == Decimal("75.00")
    assert seller_wallet.balance == Decimal("250.00")

    transactions = db_session.scalars(
        select(WalletTransaction).where(
            WalletTransaction.lot_id == lot.id,
            WalletTransaction.transaction_type
            == TransactionType.AUCTION_PAYMENT,
        )
    ).all()

    assert len(transactions) == 2

    winner_transactions = [
        transaction
        for transaction in transactions
        if transaction.wallet_id == winner_wallet.id
    ]
    seller_transactions = [
        transaction
        for transaction in transactions
        if transaction.wallet_id == seller_wallet.id
    ]

    assert len(winner_transactions) == 1
    assert len(seller_transactions) == 1
    assert winner_transactions[0].amount == Decimal("150.00")
    assert seller_transactions[0].amount == Decimal("150.00")

    events = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_type == "lot",
            AuditEvent.entity_id == lot.id,
        )
    ).all()

    assert any(
        event.event_type == AuditEventType.AUCTION_SETTLED
        for event in events
    )
    assert any(
        event.event_type == AuditEventType.LOT_STATUS_CHANGED
        for event in events
    )
    assert winning_bid.id is not None


def test_settlement_closes_lot_without_bids_and_without_payment(db_session):
    auctioneer = create_user(
        db_session,
        "Leiloeiro Sem Lances",
        "leiloeiro.sem.lances@example.test",
        UserRole.AUCTIONEER,
    )
    seller_wallet = create_wallet(db_session, auctioneer, "200.00")
    lot = create_lot(db_session, auctioneer)

    result = auction_settlement.settle_auction(
        db_session,
        lot_id=lot.id,
        actor=auctioneer,
    )

    db_session.refresh(lot)
    db_session.refresh(seller_wallet)

    assert result["status"] == LotStatus.CLOSED.value
    assert result["winner_id"] is None
    assert result["winning_amount"] is None
    assert lot.status == LotStatus.CLOSED
    assert seller_wallet.balance == Decimal("200.00")

    transaction_count = db_session.scalar(
        select(func.count())
        .select_from(WalletTransaction)
        .where(WalletTransaction.lot_id == lot.id)
    )
    assert transaction_count == 0

    settled_event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.event_type == AuditEventType.AUCTION_SETTLED,
            AuditEvent.entity_id == lot.id,
        )
    )
    assert settled_event is not None


def test_settlement_rejects_user_who_does_not_own_lot(db_session):
    auctioneer = create_user(
        db_session,
        "Leiloeiro Responsável",
        "responsavel.lote@example.test",
        UserRole.AUCTIONEER,
    )
    another_auctioneer = create_user(
        db_session,
        "Outro Leiloeiro",
        "outro.leiloeiro@example.test",
        UserRole.AUCTIONEER,
    )
    lot = create_lot(db_session, auctioneer)

    with pytest.raises(HTTPException) as exc_info:
        auction_settlement.settle_auction(
            db_session,
            lot_id=lot.id,
            actor=another_auctioneer,
        )

    assert exc_info.value.status_code == 403
    assert lot.status == LotStatus.LIVE


def test_settlement_rejects_lot_before_end_time(db_session):
    auctioneer = create_user(
        db_session,
        "Leiloeiro Prazo",
        "leiloeiro.prazo@example.test",
        UserRole.AUCTIONEER,
    )
    lot = create_lot(
        db_session,
        auctioneer,
        ends_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    with pytest.raises(HTTPException) as exc_info:
        auction_settlement.settle_auction(
            db_session,
            lot_id=lot.id,
            actor=auctioneer,
        )

    assert exc_info.value.status_code == 409
    assert lot.status == LotStatus.LIVE


def test_settlement_rejects_cancelled_lot(db_session):
    auctioneer = create_user(
        db_session,
        "Leiloeiro Cancelado",
        "leiloeiro.cancelado@example.test",
        UserRole.AUCTIONEER,
    )
    lot = create_lot(
        db_session,
        auctioneer,
        lot_status=LotStatus.CANCELLED,
    )

    with pytest.raises(HTTPException) as exc_info:
        auction_settlement.settle_auction(
            db_session,
            lot_id=lot.id,
            actor=auctioneer,
        )

    assert exc_info.value.status_code == 409
    assert lot.status == LotStatus.CANCELLED


def test_settlement_rejects_duplicate_payment(db_session):
    auctioneer = create_user(
        db_session,
        "Leiloeiro Duplicidade",
        "leiloeiro.duplicidade@example.test",
        UserRole.AUCTIONEER,
    )
    winner = create_user(
        db_session,
        "Vencedor Duplicidade",
        "vencedor.duplicidade@example.test",
        UserRole.BIDDER,
    )

    seller_wallet = create_wallet(db_session, auctioneer, "0.00")
    winner_wallet = create_wallet(
        db_session,
        winner,
        "500.00",
        "100.00",
    )
    lot = create_lot(db_session, auctioneer)
    create_bid(db_session, lot, winner, "100.00")

    auction_settlement.settle_auction(
        db_session,
        lot_id=lot.id,
        actor=auctioneer,
    )

    with pytest.raises(HTTPException) as exc_info:
        auction_settlement.settle_auction(
            db_session,
            lot_id=lot.id,
            actor=auctioneer,
        )

    assert exc_info.value.status_code == 409

    db_session.refresh(winner_wallet)
    db_session.refresh(seller_wallet)

    assert winner_wallet.balance == Decimal("400.00")
    assert winner_wallet.committed_balance == Decimal("0.00")
    assert seller_wallet.balance == Decimal("100.00")

    payment_count = db_session.scalar(
        select(func.count())
        .select_from(WalletTransaction)
        .where(
            WalletTransaction.lot_id == lot.id,
            WalletTransaction.transaction_type
            == TransactionType.AUCTION_PAYMENT,
        )
    )
    assert payment_count == 2


def test_settlement_rolls_back_if_audit_recording_fails(monkeypatch):
    """
    Confirma que uma falha de auditoria não deixa a liquidação
    parcialmente persistida no banco de dados.
    """
    auctioneer_email = "leiloeiro.rollback@example.test"
    winner_email = "vencedor.rollback@example.test"

    auctioneer_id = None
    winner_id = None
    lot_id = None
    winner_wallet_id = None
    seller_wallet_id = None

    # Cria e confirma os dados em uma sessão independente.
    # Assim, o rollback da liquidação não pode ser confundido com
    # o rollback automático da fixture db_session.
    with Session(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    ) as setup_session:
        try:
            auctioneer = create_user(
                setup_session,
                "Leiloeiro Rollback",
                auctioneer_email,
                UserRole.AUCTIONEER,
            )
            winner = create_user(
                setup_session,
                "Vencedor Rollback",
                winner_email,
                UserRole.BIDDER,
            )

            seller_wallet = create_wallet(
                setup_session,
                auctioneer,
                "50.00",
            )
            winner_wallet = create_wallet(
                setup_session,
                winner,
                "500.00",
                "100.00",
            )
            lot = create_lot(setup_session, auctioneer)
            create_bid(setup_session, lot, winner, "100.00")

            setup_session.flush()

            auctioneer_id = auctioneer.id
            winner_id = winner.id
            lot_id = lot.id
            winner_wallet_id = winner_wallet.id
            seller_wallet_id = seller_wallet.id

            setup_session.commit()
        except Exception:
            setup_session.rollback()
            raise

    # Simula a falha no terceiro evento de auditoria.
    # Os dois primeiros eventos de carteira já terão sido solicitados
    # depois das alterações financeiras, tornando o teste mais rigoroso.
    original_record_event = auction_settlement.record_event
    audit_calls = 0

    def fail_on_third_audit_event(*args, **kwargs):
        nonlocal audit_calls
        audit_calls += 1

        if audit_calls == 3:
            raise RuntimeError("Falha de auditoria simulada")

        return original_record_event(*args, **kwargs)

    monkeypatch.setattr(
        auction_settlement,
        "record_event",
        fail_on_third_audit_event,
    )

    try:
        with Session(
            bind=test_engine,
            autoflush=False,
            expire_on_commit=False,
        ) as settlement_session:
            actor = settlement_session.get(User, auctioneer_id)
            assert actor is not None

            with pytest.raises(
                RuntimeError,
                match="Falha de auditoria simulada",
            ):
                auction_settlement.settle_auction(
                    settlement_session,
                    lot_id=lot_id,
                    actor=actor,
                )

        # Verifica o estado persistido usando uma terceira sessão.
        with Session(
            bind=test_engine,
            autoflush=False,
            expire_on_commit=False,
        ) as verification_session:
            saved_lot = verification_session.get(Lot, lot_id)
            saved_winner_wallet = verification_session.get(
                Wallet,
                winner_wallet_id,
            )
            saved_seller_wallet = verification_session.get(
                Wallet,
                seller_wallet_id,
            )

            assert saved_lot is not None
            assert saved_winner_wallet is not None
            assert saved_seller_wallet is not None

            assert saved_lot.status == LotStatus.LIVE

            assert saved_winner_wallet.balance == Decimal("500.00")
            assert (
                saved_winner_wallet.committed_balance
                == Decimal("100.00")
            )

            assert saved_seller_wallet.balance == Decimal("50.00")

            payment_count = verification_session.scalar(
                select(func.count())
                .select_from(WalletTransaction)
                .where(
                    WalletTransaction.lot_id == lot_id,
                    WalletTransaction.transaction_type
                    == TransactionType.AUCTION_PAYMENT,
                )
            )
            assert payment_count == 0

            audit_count = verification_session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.entity_type == "lot",
                    AuditEvent.entity_id == lot_id,
                )
            )
            assert audit_count == 0

        assert audit_calls == 3

    finally:
        # Remove apenas os dados criados por este teste.
        # A ordem respeita as dependências entre os registros.
        monkeypatch.setattr(
            auction_settlement,
            "record_event",
            original_record_event,
        )

        with Session(
            bind=test_engine,
            autoflush=False,
            expire_on_commit=False,
        ) as cleanup_session:
            try:
                if lot_id is not None:
                    cleanup_session.execute(
                        delete(WalletTransaction).where(
                            WalletTransaction.lot_id == lot_id,
                        )
                    )
                    cleanup_session.execute(
                        delete(AuditEvent).where(
                            AuditEvent.entity_type == "lot",
                            AuditEvent.entity_id == lot_id,
                        )
                    )
                    cleanup_session.execute(
                        delete(Bid).where(Bid.lot_id == lot_id)
                    )
                    cleanup_session.execute(
                        delete(Lot).where(Lot.id == lot_id)
                    )

                if winner_wallet_id is not None:
                    cleanup_session.execute(
                        delete(Wallet).where(
                            Wallet.id == winner_wallet_id
                        )
                    )

                if seller_wallet_id is not None:
                    cleanup_session.execute(
                        delete(Wallet).where(
                            Wallet.id == seller_wallet_id
                        )
                    )

                if winner_id is not None:
                    cleanup_session.execute(
                        delete(User).where(User.id == winner_id)
                    )

                if auctioneer_id is not None:
                    cleanup_session.execute(
                        delete(User).where(User.id == auctioneer_id)
                    )

                cleanup_session.commit()
            except Exception:
                cleanup_session.rollback()
                raise



def test_settlement_creates_missing_auctioneer_wallet(db_session):
    auctioneer = create_user(
        db_session,
        "Leiloeiro sem carteira",
        "leiloeiro.sem.carteira@example.test",
        UserRole.AUCTIONEER,
    )
    winner = create_user(
        db_session,
        "Vencedor com carteira",
        "vencedor.com.carteira@example.test",
        UserRole.BIDDER,
    )
    winner_wallet = create_wallet(
        db_session,
        winner,
        "500.00",
        "100.00",
    )
    lot = create_lot(db_session, auctioneer)
    create_bid(db_session, lot, winner, "100.00")

    result = auction_settlement.settle_auction(
        db_session,
        lot_id=lot.id,
        actor=auctioneer,
    )

    db_session.refresh(lot)
    db_session.refresh(winner_wallet)
    seller_wallet = db_session.scalar(
        select(Wallet).where(Wallet.user_id == auctioneer.id)
    )

    assert result["status"] == LotStatus.CLOSED.value
    assert seller_wallet is not None
    assert seller_wallet.balance == Decimal("100.00")
    assert winner_wallet.balance == Decimal("400.00")
    assert winner_wallet.committed_balance == Decimal("0.00")
