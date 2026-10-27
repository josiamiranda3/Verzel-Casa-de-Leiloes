
from decimal import Decimal

from sqlalchemy import select

from app.core.security import create_access_token
from app.models.audit_event import AuditEvent, AuditEventType
from app.models.user import User, UserRole
from app.models.wallet import Wallet
from app.models.wallet_transaction import (
    TransactionType,
    WalletTransaction,
)


def test_deposit_persists_balance_transaction_and_audit(
    client,
    db_session,
):
    bidder = User(
        name="Arrematante Depósito",
        email="deposito.integracao@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.BIDDER,
    )
    db_session.add(bidder)
    db_session.flush()

    wallet = Wallet(
        user_id=bidder.id,
        balance=Decimal("100.00"),
        committed_balance=Decimal("20.00"),
    )
    db_session.add(wallet)
    db_session.flush()

    token = create_access_token(subject=str(bidder.id))

    response = client.post(
        "/wallet/deposit",
        json={"amount": "50.00"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201, response.text
    response_data = response.json()

    assert response_data["message"] == "Depósito simulado registrado."
    assert Decimal(response_data["amount"]) == Decimal("50.00")
    assert Decimal(response_data["balance"]) == Decimal("150.00")
    assert Decimal(response_data["committed_balance"]) == Decimal("20.00")
    assert Decimal(response_data["available_balance"]) == Decimal("130.00")

    db_session.refresh(wallet)
    assert wallet.balance == Decimal("150.00")
    assert wallet.committed_balance == Decimal("20.00")

    transaction = db_session.scalar(
        select(WalletTransaction).where(
            WalletTransaction.id == response_data["transaction_id"]
        )
    )
    assert transaction is not None
    assert transaction.wallet_id == wallet.id
    assert transaction.transaction_type == TransactionType.DEPOSIT
    assert transaction.amount == Decimal("50.00")

    event = db_session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.event_type == AuditEventType.WALLET_TRANSACTION,
            AuditEvent.actor_user_id == bidder.id,
            AuditEvent.entity_type == "wallet",
            AuditEvent.entity_id == wallet.id,
        )
        .order_by(AuditEvent.id.desc())
    )
    assert event is not None
    assert event.event_data["transaction_type"] == "deposit"
    assert event.event_data["amount"] == "50.00"
    assert event.event_data["simulated"] is True


import pytest


@pytest.mark.parametrize(
    "amount",
    ["0", "-1.00", "0.00"],
)
def test_deposit_rejects_non_positive_amount(client, db_session, amount):
    bidder = User(
        name="Arrematante Valor Inválido",
        email=f"valor.invalido.{amount.replace('.', '_').replace('-', 'neg')}@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.BIDDER,
    )
    db_session.add(bidder)
    db_session.flush()

    token = create_access_token(subject=str(bidder.id))

    response = client.post(
        "/wallet/deposit",
        json={"amount": amount},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_auctioneer_cannot_deposit_to_wallet(client, db_session):
    auctioneer = User(
        name="Leiloeiro Sem Permissão",
        email="leiloeiro.carteira@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.AUCTIONEER,
    )
    db_session.add(auctioneer)
    db_session.flush()

    token = create_access_token(subject=str(auctioneer.id))

    response = client.post(
        "/wallet/deposit",
        json={"amount": "50.00"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
 

def test_wallet_transactions_show_only_authenticated_users_transactions(
    client,
    db_session,
):
    first_bidder = User(
        name="Arrematante Histórico Um",
        email="historico.um@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.BIDDER,
    )
    second_bidder = User(
        name="Arrematante Histórico Dois",
        email="historico.dois@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.BIDDER,
    )
    db_session.add_all([first_bidder, second_bidder])
    db_session.flush()

    first_wallet = Wallet(user_id=first_bidder.id)
    second_wallet = Wallet(user_id=second_bidder.id)
    db_session.add_all([first_wallet, second_wallet])
    db_session.flush()

    older_transaction = WalletTransaction(
        wallet_id=first_wallet.id,
        transaction_type=TransactionType.DEPOSIT,
        amount=Decimal("20.00"),
        description="Depósito antigo",
    )
    newer_transaction = WalletTransaction(
        wallet_id=first_wallet.id,
        transaction_type=TransactionType.DEPOSIT,
        amount=Decimal("30.00"),
        description="Depósito recente",
    )
    other_user_transaction = WalletTransaction(
        wallet_id=second_wallet.id,
        transaction_type=TransactionType.DEPOSIT,
        amount=Decimal("999.00"),
        description="Movimentação de outro usuário",
    )
    db_session.add_all(
        [
            older_transaction,
            newer_transaction,
            other_user_transaction,
        ]
    )
    db_session.flush()

    # Estabelece uma ordem temporal inequívoca para o teste.
    from datetime import datetime, timedelta, timezone

    older_transaction.created_at = datetime(
        2026, 1, 1, tzinfo=timezone.utc
    )
    newer_transaction.created_at = datetime(
        2026, 1, 2, tzinfo=timezone.utc
    )
    other_user_transaction.created_at = datetime(
        2026, 1, 3, tzinfo=timezone.utc
    )
    db_session.flush()

    token = create_access_token(subject=str(first_bidder.id))

    response = client.get(
        "/wallet/me/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    transactions = response.json()

    assert len(transactions) == 2
    assert [item["description"] for item in transactions] == [
        "Depósito recente",
        "Depósito antigo",
    ]
    assert all(
        item["wallet_id"] == first_wallet.id
        for item in transactions
    )
    assert Decimal(transactions[0]["amount"]) == Decimal("30.00")
    assert Decimal(transactions[1]["amount"]) == Decimal("20.00")



def test_read_my_wallet_returns_correct_balances(client, db_session):
    bidder = User(
        name="Arrematante Consulta",
        email="consulta.carteira@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.BIDDER,
    )
    db_session.add(bidder)
    db_session.flush()

    wallet = Wallet(
        user_id=bidder.id,
        balance=Decimal("250.00"),
        committed_balance=Decimal("75.00"),
    )
    db_session.add(wallet)
    db_session.flush()

    token = create_access_token(subject=str(bidder.id))

    response = client.get(
        "/wallet/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text

    data = response.json()
    assert data["id"] == wallet.id
    assert data["user_id"] == bidder.id
    assert Decimal(data["balance"]) == Decimal("250.00")
    assert Decimal(data["committed_balance"]) == Decimal("75.00")
    assert Decimal(data["available_balance"]) == Decimal("175.00")


def test_auctioneer_cannot_read_wallet(client, db_session):
    auctioneer = User(
        name="Leiloeiro Consulta",
        email="consulta.leiloeiro@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.AUCTIONEER,
    )
    db_session.add(auctioneer)
    db_session.flush()

    token = create_access_token(subject=str(auctioneer.id))

    response = client.get(
        "/wallet/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_auctioneer_cannot_read_wallet_transactions(client, db_session):
    auctioneer = User(
        name="Leiloeiro Histórico",
        email="historico.leiloeiro@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.AUCTIONEER,
    )
    db_session.add(auctioneer)
    db_session.flush()

    token = create_access_token(subject=str(auctioneer.id))

    response = client.get(
        "/wallet/me/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_deposit_rejects_amount_with_more_than_two_decimal_places(
    client,
    db_session,
):
    bidder = User(
        name="Arrematante Precisão",
        email="precisao.carteira@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.BIDDER,
    )
    db_session.add(bidder)
    db_session.flush()

    token = create_access_token(subject=str(bidder.id))

    response = client.post(
        "/wallet/deposit",
        json={"amount": "10.999"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422

