
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import delete

from app.models.audit_event import AuditEventType
from app.models.bid import Bid
from app.models.lot import Lot, LotStatus
from app.models.user import User, UserRole
from app.services.audit_service import record_event


def create_lot_with_bids(db_session):
    now = datetime.now(timezone.utc)

    auctioneer = User(
        name="Leiloeiro Privado",
        email="auctioneer-audit@example.com",
        password_hash="test-hash",
        role=UserRole.AUCTIONEER,
    )
    bidder_one = User(
        name="Participante Privado A",
        email="bidder-audit-a@example.com",
        password_hash="test-hash",
        role=UserRole.BIDDER,
    )
    bidder_two = User(
        name="Participante Privado B",
        email="bidder-audit-b@example.com",
        password_hash="test-hash",
        role=UserRole.BIDDER,
    )

    db_session.add_all([auctioneer, bidder_one, bidder_two])
    db_session.flush()

    lot = Lot(
        auctioneer_id=auctioneer.id,
        title="Lote de auditoria",
        description="Lote usado em teste automatizado",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(minutes=10),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.LIVE,
    )
    db_session.add(lot)
    db_session.flush()

    first_bid = Bid(
        lot_id=lot.id,
        bidder_id=bidder_one.id,
        amount=Decimal("100.00"),
        created_at=now - timedelta(minutes=2),
    )
    second_bid = Bid(
        lot_id=lot.id,
        bidder_id=bidder_two.id,
        amount=Decimal("110.00"),
        created_at=now - timedelta(minutes=1),
    )

    db_session.add_all([first_bid, second_bid])
    db_session.flush()

    record_event(
        db_session,
        event_type=AuditEventType.BID_PLACED,
        entity_type="bid",
        entity_id=first_bid.id,
        description=f"Lance registrado no lote {lot.id}.",
        event_data={
            "lot_id": lot.id,
            "bidder_id": bidder_one.id,
            "amount": format(first_bid.amount, "f"),
            "reserved_amount": format(first_bid.amount, "f"),
        },
        commit=False,
    )

    record_event(
        db_session,
        event_type=AuditEventType.BID_PLACED,
        entity_type="bid",
        entity_id=second_bid.id,
        description=f"Lance registrado no lote {lot.id}.",
        event_data={
            "lot_id": lot.id,
            "bidder_id": bidder_two.id,
            "amount": format(second_bid.amount, "f"),
            "reserved_amount": format(second_bid.amount, "f"),
        },
        commit=False,
    )

    db_session.flush()

    return lot, bidder_one, bidder_two


def mock_valid_integrity():
    return {
        "valid": True,
        "event_id": None,
        "reason": "Todos os eventos verificados estão íntegros.",
        "checked_events": 2,
    }


def mock_valid_checkpoint():
    return {
        "valid": True,
        "reason": "A cadeia corresponde ao checkpoint registrado.",
    }


def test_public_audit_returns_bid_history_without_login(
    client,
    db_session,
):
    lot, _, _ = create_lot_with_bids(db_session)

    with (
        patch(
            "app.api.routes.audit.verify_audit_chain",
            return_value=mock_valid_integrity(),
        ),
        patch(
            "app.api.routes.audit.verify_audit_checkpoint",
            return_value=mock_valid_checkpoint(),
        ),
    ):
        response = client.get(f"/audit/lots/{lot.id}")

    assert response.status_code == 200

    data = response.json()

    assert data["lot_id"] == lot.id
    assert data["integrity"]["valid"] is True
    assert data["integrity"]["checked_events"] == 2
    assert len(data["bids"]) == 2

    assert [
        Decimal(item["amount"]) for item in data["bids"]
    ] == [
        Decimal("100.00"),
        Decimal("110.00"),
    ]

    assert data["bids"][0]["bidder_label"] == "Licitante 1"
    assert data["bids"][1]["bidder_label"] == "Licitante 2"


def test_public_audit_does_not_expose_private_fields(
    client,
    db_session,
):
    lot, bidder_one, bidder_two = create_lot_with_bids(db_session)

    with (
        patch(
            "app.api.routes.audit.verify_audit_chain",
            return_value=mock_valid_integrity(),
        ),
        patch(
            "app.api.routes.audit.verify_audit_checkpoint",
            return_value=mock_valid_checkpoint(),
        ),
    ):
        response = client.get(f"/audit/lots/{lot.id}")

    assert response.status_code == 200

    data = response.json()

    assert "bidder_id" not in data
    assert "actor_user_id" not in data
    assert "event_data" not in data
    assert "event_hash" not in data

    for item in data["bids"]:
        assert set(item.keys()) == {
            "bidder_label",
            "amount",
            "created_at",
        }

        assert "bidder_id" not in item
        assert "name" not in item
        assert "email" not in item

    response_text = response.text

    assert bidder_one.email not in response_text
    assert bidder_two.email not in response_text
    assert bidder_one.name not in response_text
    assert bidder_two.name not in response_text


def test_public_audit_returns_404_for_missing_lot(client):
    response = client.get("/audit/lots/999999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Lote não encontrado."


def test_public_audit_reports_invalid_chain(
    client,
    db_session,
):
    invalid_chain = {
        "valid": False,
        "event_id": 42,
        "reason": "O hash do evento não corresponde aos seus dados.",
        "checked_events": 3,
    }

    lot, _, _ = create_lot_with_bids(db_session)

    with (
        patch(
            "app.api.routes.audit.verify_audit_chain",
            return_value=invalid_chain,
        ),
        patch(
            "app.api.routes.audit.verify_audit_checkpoint",
            return_value=mock_valid_checkpoint(),
        ),
    ):
        response = client.get(f"/audit/lots/{lot.id}")

    assert response.status_code == 200

    integrity = response.json()["integrity"]

    assert integrity["valid"] is False
    assert integrity["message"] == (
        "Adulteração ou inconsistência detectada "
        "na cadeia de auditoria."
    )
    assert integrity["checked_events"] == 3
    assert "event_id" not in integrity
    assert "reason" not in integrity


def test_public_audit_reports_invalid_checkpoint(
    client,
    db_session,
):
    lot, _, _ = create_lot_with_bids(db_session)

    with (
        patch(
            "app.api.routes.audit.verify_audit_chain",
            return_value=mock_valid_integrity(),
        ),
        patch(
            "app.api.routes.audit.verify_audit_checkpoint",
            return_value={
                "valid": False,
                "reason": "Checkpoint de auditoria não encontrado.",
            },
        ),
    ):
        response = client.get(f"/audit/lots/{lot.id}")

    assert response.status_code == 200

    integrity = response.json()["integrity"]

    assert integrity["valid"] is False
    assert integrity["message"] == (
        "Integridade não confirmada: "
        "checkpoint ausente, inválido ou divergente."
    )
    assert integrity["checked_events"] == 2
    assert "reason" not in integrity


def test_public_audit_keeps_bid_after_bid_record_is_deleted(
    client,
    db_session,
):
    lot, _, bidder_two = create_lot_with_bids(db_session)

    # Exclui o lance da tabela Bid, mantendo os eventos de auditoria.
    db_session.execute(
        delete(Bid).where(
            Bid.lot_id == lot.id,
            Bid.bidder_id == bidder_two.id,
        )
    )
    db_session.flush()

    with (
        patch(
            "app.api.routes.audit.verify_audit_chain",
            return_value=mock_valid_integrity(),
        ),
        patch(
            "app.api.routes.audit.verify_audit_checkpoint",
            return_value=mock_valid_checkpoint(),
        ),
    ):
        response = client.get(f"/audit/lots/{lot.id}")

    assert response.status_code == 200

    data = response.json()

    assert len(data["bids"]) == 2
    assert [
        Decimal(item["amount"]) for item in data["bids"]
    ] == [
        Decimal("100.00"),
        Decimal("110.00"),
    ]

def test_public_audit_reports_invalid_bid_event_data(
    client,
    db_session,
):
    lot, _, _ = create_lot_with_bids(db_session)

    record_event(
        db_session,
        event_type=AuditEventType.BID_PLACED,
        entity_type="bid",
        entity_id=999999,
        description="Evento de lance incompleto",
        event_data={"lot_id": lot.id},
        commit=False,
    )
    db_session.flush()

    with (
        patch(
            "app.api.routes.audit.verify_audit_chain",
            return_value=mock_valid_integrity(),
        ),
        patch(
            "app.api.routes.audit.verify_audit_checkpoint",
            return_value=mock_valid_checkpoint(),
        ),
    ):
        response = client.get(f"/audit/lots/{lot.id}")

    assert response.status_code == 200
    assert response.json()["integrity"]["valid"] is False