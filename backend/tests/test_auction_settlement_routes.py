from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.core.security import create_access_token
from app.models.audit_event import AuditEvent, AuditEventType
from app.models.bid import Bid
from app.models.lot import Lot, LotStatus
from app.models.user import User, UserRole
from app.models.wallet import Wallet
from app.models.wallet_transaction import (
    TransactionType,
    WalletTransaction,
)


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


def create_expired_lot(db_session, auctioneer):
    now = datetime.now(timezone.utc)

    lot = Lot(
        auctioneer_id=auctioneer.id,
        title="Lote para teste da API",
        description="Lote fictício para teste automatizado",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(hours=2),
        ends_at=now - timedelta(minutes=1),
        status=LotStatus.LIVE,
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


def auth_headers(user):
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


def test_auctioneer_can_settle_own_lot_through_api(client, db_session):
    auctioneer = create_user(
        db_session,
        "Leiloeiro API",
        "leiloeiro.api.settlement@example.test",
        UserRole.AUCTIONEER,
    )
    bidder = create_user(
        db_session,
        "Arrematante API",
        "arrematante.api.settlement@example.test",
        UserRole.BIDDER,
    )

    seller_wallet = create_wallet(db_session, auctioneer, "0.00")
    bidder_wallet = create_wallet(
        db_session,
        bidder,
        "500.00",
        "120.00",
    )

    lot = create_expired_lot(db_session, auctioneer)
    create_bid(db_session, lot, bidder, "120.00")

    response = client.post(
        f"/lots/{lot.id}/settle",
        headers=auth_headers(auctioneer),
    )

    assert response.status_code == 200, response.text

    data = response.json()
    assert data["lot_id"] == lot.id
    assert data["status"] == LotStatus.CLOSED.value
    assert data["winner_id"] == bidder.id
    assert Decimal(str(data["winning_amount"])) == Decimal("120.00")

    db_session.refresh(lot)
    db_session.refresh(seller_wallet)
    db_session.refresh(bidder_wallet)

    assert lot.status == LotStatus.CLOSED
    assert seller_wallet.balance == Decimal("120.00")
    assert bidder_wallet.balance == Decimal("380.00")
    assert bidder_wallet.committed_balance == Decimal("0.00")

    transactions = db_session.scalars(
        select(WalletTransaction).where(
            WalletTransaction.lot_id == lot.id,
            WalletTransaction.transaction_type
            == TransactionType.AUCTION_PAYMENT,
        )
    ).all()

    assert len(transactions) == 2

    settled_event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.event_type == AuditEventType.AUCTION_SETTLED,
            AuditEvent.entity_id == lot.id,
        )
    )
    assert settled_event is not None


def test_settlement_endpoint_requires_authentication(client, db_session):
    auctioneer = create_user(
        db_session,
        "Leiloeiro Sem Autenticação",
        "leiloeiro.sem.auth.settlement@example.test",
        UserRole.AUCTIONEER,
    )
    lot = create_expired_lot(db_session, auctioneer)

    response = client.post(f"/lots/{lot.id}/settle")

    assert response.status_code == 401


def test_bidder_cannot_settle_lot(client, db_session):
    auctioneer = create_user(
        db_session,
        "Leiloeiro Dono",
        "leiloeiro.dono.settlement@example.test",
        UserRole.AUCTIONEER,
    )
    bidder = create_user(
        db_session,
        "Arrematante Não Autorizado",
        "arrematante.nao.autorizado.settlement@example.test",
        UserRole.BIDDER,
    )
    lot = create_expired_lot(db_session, auctioneer)

    response = client.post(
        f"/lots/{lot.id}/settle",
        headers=auth_headers(bidder),
    )

    assert response.status_code == 403

    db_session.refresh(lot)
    assert lot.status == LotStatus.LIVE


def test_auctioneer_cannot_settle_another_auctioneers_lot(
    client,
    db_session,
):
    owner = create_user(
        db_session,
        "Dono do Lote",
        "dono.lote.settlement@example.test",
        UserRole.AUCTIONEER,
    )
    another_auctioneer = create_user(
        db_session,
        "Outro Leiloeiro",
        "outro.dono.settlement@example.test",
        UserRole.AUCTIONEER,
    )
    lot = create_expired_lot(db_session, owner)

    response = client.post(
        f"/lots/{lot.id}/settle",
        headers=auth_headers(another_auctioneer),
    )

    assert response.status_code == 403

    db_session.refresh(lot)
    assert lot.status == LotStatus.LIVE


def test_settlement_endpoint_returns_404_for_missing_lot(
    client,
    db_session,
):
    auctioneer = create_user(
        db_session,
        "Leiloeiro Lote Ausente",
        "leiloeiro.lote.ausente@example.test",
        UserRole.AUCTIONEER,
    )

    response = client.post(
        "/lots/999999999/settle",
        headers=auth_headers(auctioneer),
    )

    assert response.status_code == 404



def test_expired_scheduled_lot_without_bids_is_closed_on_lot_listing(
    client, db_session
):
    """A consulta não deve deixar um lote vencido preso em scheduled."""
    auctioneer = create_user(
        db_session,
        "Leiloeiro Encerramento Automático",
        "leiloeiro.encerramento.automatico@example.test",
        UserRole.AUCTIONEER,
    )
    lot = create_expired_lot(db_session, auctioneer)
    lot.status = LotStatus.SCHEDULED
    db_session.flush()

    response = client.get("/lots/")

    assert response.status_code == 200, response.text
    db_session.refresh(lot)
    assert lot.status == LotStatus.CLOSED

    settled_event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.event_type == AuditEventType.AUCTION_SETTLED,
            AuditEvent.entity_type == "lot",
            AuditEvent.entity_id == lot.id,
        )
    )
    assert settled_event is not None


def test_scheduled_lot_inside_auction_window_becomes_live_on_listing(
    client, db_session
):
    """A abertura usa as datas existentes e registra a transição de status."""
    auctioneer = create_user(
        db_session,
        "Leiloeiro Abertura Automática",
        "leiloeiro.abertura.automatica@example.test",
        UserRole.AUCTIONEER,
    )
    now = datetime.now(timezone.utc)
    lot = Lot(
        auctioneer_id=auctioneer.id,
        title="Lote agendado para abrir",
        description="Teste de transição de status",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.SCHEDULED,
    )
    db_session.add(lot)
    db_session.flush()

    response = client.get("/lots/")

    assert response.status_code == 200, response.text
    db_session.refresh(lot)
    assert lot.status == LotStatus.LIVE

    changed_event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.event_type == AuditEventType.LOT_STATUS_CHANGED,
            AuditEvent.entity_type == "lot",
            AuditEvent.entity_id == lot.id,
        )
    )
    assert changed_event is not None
