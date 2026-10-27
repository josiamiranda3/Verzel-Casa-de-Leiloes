import pytest
from sqlalchemy import select

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password
from app.models.user import User, UserRole


def test_register_rejects_public_auctioneer(client):
    response = client.post(
        "/auth/register",
        json={
            "name": "Leiloeiro Teste",
            "email": "leiloeiro@example.com",
            "password": "SenhaSegura123",
            "role": "auctioneer",
        },
    )

    assert response.status_code == 403
    assert "somente para arrematantes" in response.json()["detail"]


def test_register_creates_bidder_and_wallet(client, db_session):
    response = client.post(
        "/auth/register",
        json={
            "name": "Arrematante Teste",
            "email": "arrematante@example.com",
            "password": "SenhaSegura123",
            "role": "bidder",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "arrematante@example.com"
    assert response.json()["role"] == "bidder"
    assert "password_hash" not in response.json()

    user = db_session.scalar(
        select(User).where(User.email == "arrematante@example.com")
    )

    assert user is not None


def test_login_rejects_wrong_password(client, db_session):
    user = User(
        name="Login Teste",
        email="login@example.com",
        password_hash=hash_password("SenhaCorreta123"),
        role=UserRole.BIDDER,
    )
    db_session.add(user)
    db_session.flush()

    response = client.post(
        "/auth/login",
        json={
            "email": "login@example.com",
            "password": "SenhaErrada123",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "E-mail ou senha incorretos."


def test_protected_route_rejects_missing_token(client):
    response = client.post(
        "/bids/",
        json={"lot_id": 1, "amount": "100.00"},
    )

    assert response.status_code == 401


def test_protected_route_rejects_invalid_token(client):
    response = client.post(
        "/bids/",
        json={"lot_id": 1, "amount": "100.00"},
        headers={"Authorization": "Bearer token-invalido"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Credenciais inválidas ou token expirado."
    )


def test_protected_route_rejects_token_for_nonexistent_user(
    client,
    db_session,
):
    token = create_access_token(subject="999999999")

    response = client.post(
        "/bids/",
        json={"lot_id": 1, "amount": "100.00"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
