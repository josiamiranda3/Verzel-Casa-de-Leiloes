import pytest

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.bid import Bid
from app.models.lot import Lot, LotStatus
from app.models.user import User, UserRole
from app.models.wallet_transaction import (
    TransactionType,
    WalletTransaction,
)


def make_user(user_id: int, role: UserRole) -> User:
    return User(
        id=user_id,
        name=f"Usuário {user_id}",
        email=f"usuario{user_id}@example.com",
        password_hash="hash-de-teste",
        role=role,
    )


def test_auctioneer_cannot_place_bid():
    auctioneer = make_user(3, UserRole.AUCTIONEER)
    fake_db = Mock()

    app.dependency_overrides[get_current_user] = lambda: auctioneer
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        with TestClient(app) as client:
            response = client.post(
                "/bids/",
                json={"lot_id": 1, "amount": "100.00"},
            )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Somente arrematantes podem ofertar lances."
        )
        fake_db.scalar.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_bidder_with_missing_lot_is_rejected():
    bidder = make_user(1, UserRole.BIDDER)
    fake_db = Mock()
    fake_db.scalar.return_value = None

    app.dependency_overrides[get_current_user] = lambda: bidder
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        with TestClient(app) as client:
            response = client.post(
                "/bids/",
                json={"lot_id": 999999, "amount": "100.00"},
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Lote não encontrado."
        fake_db.scalar.assert_called_once()
    finally:
        app.dependency_overrides.clear()


def test_bid_below_minimum_is_rejected():
    bidder = make_user(1, UserRole.BIDDER)
    fake_db = Mock()
    now = datetime.now(timezone.utc)

    lot = Lot(
        id=1,
        auctioneer_id=3,
        title="Lote de teste",
        description="Lote simulado para testes automatizados",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(minutes=5),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.LIVE,
    )

    fake_db.scalar.side_effect = [lot, None]

    app.dependency_overrides[get_current_user] = lambda: bidder
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        with TestClient(app) as client:
            response = client.post(
                "/bids/",
                json={"lot_id": 1, "amount": "90.00"},
            )

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "O lance mínimo permitido é 100.00."
        )
        assert fake_db.scalar.call_count == 2
    finally:
        app.dependency_overrides.clear()


def test_bid_with_insufficient_balance_is_rejected():
    bidder = make_user(1, UserRole.BIDDER)
    fake_db = Mock()
    now = datetime.now(timezone.utc)

    lot = Lot(
        id=1,
        auctioneer_id=3,
        title="Lote de teste",
        description="Lote simulado",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(minutes=5),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.LIVE,
    )

    wallet = Mock()
    wallet.user_id = bidder.id
    wallet.id = 10
    wallet.balance = Decimal("50.00")
    wallet.committed_balance = Decimal("0.00")

    fake_db.scalar.side_effect = [lot, None]
    fake_db.scalars.return_value.all.return_value = [wallet]

    app.dependency_overrides[get_current_user] = lambda: bidder
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        with TestClient(app) as client:
            response = client.post(
                "/bids/",
                json={"lot_id": 1, "amount": "100.00"},
            )

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "Saldo disponível insuficiente para cobrir o lance."
        )
        fake_db.add.assert_not_called()
        fake_db.commit.assert_not_called()
    finally:
        app.dependency_overrides.clear()


@patch("app.api.routes.bids.record_event")
def test_valid_bid_is_created_and_balance_reserved(mock_record_event):
    bidder = make_user(1, UserRole.BIDDER)
    fake_db = Mock()
    now = datetime.now(timezone.utc)

    lot = Lot(
        id=1,
        auctioneer_id=3,
        title="Lote de teste",
        description="Lote simulado",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(minutes=5),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.LIVE,
    )

    wallet = Mock()
    wallet.id = 10
    wallet.user_id = bidder.id
    wallet.balance = Decimal("200.00")
    wallet.committed_balance = Decimal("0.00")

    fake_db.scalar.side_effect = [lot, None]
    fake_db.scalars.return_value.all.return_value = [wallet]

    def fake_refresh(obj):
        if isinstance(obj, Bid):
            obj.id = 123
            obj.created_at = now

    fake_db.refresh.side_effect = fake_refresh

    app.dependency_overrides[get_current_user] = lambda: bidder
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        with TestClient(app) as client:
            response = client.post(
                "/bids/",
                json={"lot_id": 1, "amount": "100.00"},
            )

        assert response.status_code == 201
        assert response.json()["id"] == 123
        assert response.json()["lot_id"] == 1
        assert response.json()["bidder_id"] == bidder.id
        assert Decimal(response.json()["amount"]) == Decimal("100.00")

        assert wallet.committed_balance == Decimal("100.00")
        fake_db.add.assert_called()
        fake_db.commit.assert_called_once()
        fake_db.refresh.assert_called_once()
        assert mock_record_event.call_count == 2
    finally:
        app.dependency_overrides.clear()


@patch("app.api.routes.bids.record_event")
def test_new_bid_releases_previous_reservation(mock_record_event):
    bidder = make_user(2, UserRole.BIDDER)
    previous_bidder = make_user(1, UserRole.BIDDER)
    fake_db = Mock()
    now = datetime.now(timezone.utc)

    lot = Lot(
        id=1,
        auctioneer_id=3,
        title="Lote de teste",
        description="Lote simulado",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(minutes=5),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.LIVE,
    )

    previous_bid = Bid(
        id=50,
        lot_id=lot.id,
        bidder_id=previous_bidder.id,
        amount=Decimal("100.00"),
        created_at=now - timedelta(minutes=1),
    )

    previous_wallet = Mock()
    previous_wallet.id = 10
    previous_wallet.user_id = previous_bidder.id
    previous_wallet.balance = Decimal("200.00")
    previous_wallet.committed_balance = Decimal("100.00")

    bidder_wallet = Mock()
    bidder_wallet.id = 20
    bidder_wallet.user_id = bidder.id
    bidder_wallet.balance = Decimal("200.00")
    bidder_wallet.committed_balance = Decimal("0.00")

    fake_db.scalar.side_effect = [lot, previous_bid]
    fake_db.scalars.return_value.all.return_value = [
        previous_wallet,
        bidder_wallet,
    ]

    def fake_refresh(obj):
        if isinstance(obj, Bid):
            obj.id = 123
            obj.created_at = now

    fake_db.refresh.side_effect = fake_refresh

    app.dependency_overrides[get_current_user] = lambda: bidder
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        with TestClient(app) as client:
            response = client.post(
                "/bids/",
                json={"lot_id": 1, "amount": "110.00"},
            )

        assert response.status_code == 201
        assert response.json()["id"] == 123
        assert response.json()["bidder_id"] == bidder.id
        assert Decimal(response.json()["amount"]) == Decimal("110.00")

        assert previous_wallet.committed_balance == Decimal("0.00")
        assert bidder_wallet.committed_balance == Decimal("110.00")

        transactions = [
            call.args[0]
            for call in fake_db.add.call_args_list
            if isinstance(call.args[0], WalletTransaction)
        ]

        assert any(
            transaction.transaction_type == TransactionType.BID_RELEASE
            and transaction.amount == Decimal("100.00")
            for transaction in transactions
        )

        assert any(
            transaction.transaction_type == TransactionType.BID_RESERVE
            and transaction.amount == Decimal("110.00")
            for transaction in transactions
        )

        assert fake_db.commit.call_count == 1
        assert mock_record_event.call_count == 3
    finally:
        app.dependency_overrides.clear()


@patch("app.api.routes.bids.record_event")
def test_audit_failure_rolls_back_bid_and_reservation(
    mock_record_event,
):
    bidder = make_user(1, UserRole.BIDDER)
    fake_db = Mock()
    now = datetime.now(timezone.utc)

    lot = Lot(
        id=1,
        auctioneer_id=3,
        title="Lote de teste",
        description="Lote simulado",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(minutes=5),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.LIVE,
    )

    wallet = Mock()
    wallet.id = 10
    wallet.user_id = bidder.id
    wallet.balance = Decimal("200.00")
    wallet.committed_balance = Decimal("0.00")

    fake_db.scalar.side_effect = [lot, None]
    fake_db.scalars.return_value.all.return_value = [wallet]

    # Simula uma falha ao registrar o evento de auditoria.
    mock_record_event.side_effect = RuntimeError(
        "Falha simulada na auditoria"
    )

    app.dependency_overrides[get_current_user] = lambda: bidder
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        with TestClient(app) as client:
            try:
                client.post(
                    "/bids/",
                    json={"lot_id": 1, "amount": "100.00"},
                )
                assert False, "A falha de auditoria deveria ser propagada."
            except RuntimeError as exc:
                assert str(exc) == "Falha simulada na auditoria"

        # A falha deve impedir o commit da operação.
        fake_db.commit.assert_not_called()

        # O endpoint deve solicitar rollback.
        fake_db.rollback.assert_called()

        # O saldo reservado em memória precisa ser restaurado
        # pelo teste, pois o Mock não simula rollback do banco.
    finally:
        app.dependency_overrides.clear()


def test_same_bidder_cannot_cover_own_bid():
    bidder = make_user(1, UserRole.BIDDER)
    fake_db = Mock()
    now = datetime.now(timezone.utc)

    lot = Lot(
        id=1,
        auctioneer_id=3,
        title="Lote de teste",
        description="Lote simulado",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(minutes=5),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.LIVE,
    )

    previous_bid = Bid(
        id=50,
        lot_id=lot.id,
        bidder_id=bidder.id,
        amount=Decimal("100.00"),
        created_at=now - timedelta(minutes=1),
    )

    wallet = Mock()
    wallet.id = 10
    wallet.user_id = bidder.id
    wallet.balance = Decimal("200.00")
    wallet.committed_balance = Decimal("100.00")

    fake_db.scalar.side_effect = [lot, previous_bid]
    fake_db.scalars.return_value.all.return_value = [wallet]

    app.dependency_overrides[get_current_user] = lambda: bidder
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        with TestClient(app) as client:
            response = client.post(
                "/bids/",
                json={"lot_id": 1, "amount": "120.00"},
            )

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "Você já está liderando este leilão e não pode cobrir o próprio lance."
        )

        # A rejeição não deve alterar a reserva financeira.
        assert wallet.committed_balance == Decimal("100.00")

        # Nenhum novo lance, transação, commit ou evento deve ser criado.
        fake_db.add.assert_not_called()
        fake_db.commit.assert_not_called()
        fake_db.refresh.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_bid_after_lot_ends_is_rejected():
    bidder = make_user(1, UserRole.BIDDER)
    fake_db = Mock()
    now = datetime.now(timezone.utc)

    lot = Lot(
        id=1,
        auctioneer_id=3,
        title="Lote encerrado",
        description="Teste de encerramento",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(hours=1),
        ends_at=now - timedelta(seconds=1),
        status=LotStatus.LIVE,
    )

    fake_db.scalar.return_value = lot

    app.dependency_overrides[get_current_user] = lambda: bidder
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        with TestClient(app) as client:
            response = client.post(
                "/bids/",
                json={"lot_id": 1, "amount": "100.00"},
            )

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "O prazo para lances deste lote terminou."
        )

        # A operação não deve modificar nem confirmar dados.
        fake_db.add.assert_not_called()
        fake_db.commit.assert_not_called()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("remaining_seconds", "should_extend"),
    [
        (60, True),
        (120, True),
        (121, False),
    ],
)
@patch("app.api.routes.bids.record_event")
def test_bid_anti_sniping_boundary(
    mock_record_event,
    monkeypatch,
    remaining_seconds,
    should_extend,
):
    from app.api.routes import bids as bids_routes

    bidder = make_user(1, UserRole.BIDDER)
    fake_db = Mock()
    now = datetime(2026, 10, 26, 20, 0, tzinfo=timezone.utc)
    original_end = now + timedelta(seconds=remaining_seconds)

    lot = Lot(
        id=1,
        auctioneer_id=3,
        title="Lote antisniping",
        description="Teste de limite temporal",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(minutes=5),
        ends_at=original_end,
        status=LotStatus.LIVE,
    )

    wallet = Mock()
    wallet.id = 10
    wallet.user_id = bidder.id
    wallet.balance = Decimal("200.00")
    wallet.committed_balance = Decimal("0.00")

    fake_db.scalar.side_effect = [lot, None]
    fake_db.scalars.return_value.all.return_value = [wallet]

    def fake_refresh(obj):
        if isinstance(obj, Bid):
            obj.id = 123
            obj.created_at = now

    fake_db.refresh.side_effect = fake_refresh

    monkeypatch.setattr(
        bids_routes,
        "datetime",
        type("FrozenDateTime", (), {"now": staticmethod(lambda tz=None: now)}),
    )

    app.dependency_overrides[get_current_user] = lambda: bidder
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        with TestClient(app) as client:
            response = client.post(
                "/bids/",
                json={"lot_id": 1, "amount": "100.00"},
            )

        assert response.status_code == 201

        expected_end = (
            original_end + timedelta(minutes=2)
            if should_extend
            else original_end
        )
        assert lot.ends_at == expected_end

        anti_sniping_calls = [
            call.kwargs
            for call in mock_record_event.call_args_list
            if call.kwargs.get("description")
            == "Encerramento prorrogado por anti-sniping."
        ]
        assert len(anti_sniping_calls) == (1 if should_extend else 0)

        if should_extend:
            event_data = anti_sniping_calls[0]["event_data"]
            assert event_data["reason"] == "bid_in_final_two_minutes"
            assert event_data["previous_ends_at"] == original_end.isoformat()
            assert event_data["new_ends_at"] == expected_end.isoformat()

        fake_db.commit.assert_called_once()
    finally:
        app.dependency_overrides.clear()
