from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import httpx

from app.api.deps import get_current_user
from app.models.audit_event import AuditEvent, AuditEventType
from app.models.bid import Bid
from app.models.lot import Lot, LotStatus
from app.models.user import User, UserRole


def test_external_api_failure_does_not_break_local_lot_features(
    client, db_session
):
    now = datetime.now(timezone.utc)

    auctioneer = User(
        name="Leiloeiro temporário",
        email="auctioneer-external-temp@example.com",
        password_hash="test-hash",
        role=UserRole.AUCTIONEER,
    )
    bidder = User(
        name="Arrematante temporário",
        email="bidder-external-temp@example.com",
        password_hash="test-hash",
        role=UserRole.BIDDER,
    )
    db_session.add_all([auctioneer, bidder])
    db_session.flush()

    live_lot = Lot(
        auctioneer_id=auctioneer.id,
        title="Lote ativo temporário",
        description="Teste integrado",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(minutes=10),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.LIVE,
    )
    closed_lot = Lot(
        auctioneer_id=auctioneer.id,
        title="Lote encerrado temporário",
        description="Teste integrado de comprovante",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(hours=2),
        ends_at=now - timedelta(hours=1),
        status=LotStatus.CLOSED,
    )
    db_session.add_all([live_lot, closed_lot])
    db_session.flush()

    db_session.add_all([
        Bid(
            lot_id=live_lot.id,
            bidder_id=bidder.id,
            amount=Decimal("100.00"),
            created_at=now - timedelta(minutes=2),
        ),
        Bid(
            lot_id=closed_lot.id,
            bidder_id=bidder.id,
            amount=Decimal("150.00"),
            created_at=now - timedelta(hours=1, minutes=30),
        ),
        AuditEvent(
            event_type=AuditEventType.AUCTION_SETTLED,
            actor_user_id=auctioneer.id,
            entity_type="lot",
            entity_id=closed_lot.id,
            description="Liquidação simulada para teste integrado.",
            event_data={},
            event_hash="f" * 64,
        ),
    ])
    db_session.flush()

    app = client.app
    app.dependency_overrides[get_current_user] = lambda: auctioneer

    try:
        with (
            patch(
                "app.api.routes.lots.httpx.get",
                side_effect=httpx.ConnectError("Falha externa simulada"),
            ),
            patch(
                "app.api.routes.audit.verify_audit_chain",
                return_value={
                    "valid": True,
                    "event_id": None,
                    "reason": "Teste integrado",
                    "checked_events": 1,
                },
            ),
            patch(
                "app.api.routes.audit.verify_audit_checkpoint",
                return_value={
                    "valid": True,
                    "reason": "Teste integrado",
                },
            ),
        ):
            external = client.get(
                "/lots/external/search",
                params={"q": "dom casmurro"},
            )
            vitrine = client.get("/lots/")
            sala = client.get(f"/bids/lot/{live_lot.id}")
            auditoria = client.get(f"/audit/lots/{live_lot.id}")
            comprovante = client.get(
                f"/lots/{closed_lot.id}/receipt"
            )

        assert external.status_code == 503, external.text
        assert vitrine.status_code == 200, vitrine.text
        assert any(
            item["id"] == live_lot.id for item in vitrine.json()
        )
        assert sala.status_code == 200, sala.text
        assert len(sala.json()) == 1
        assert auditoria.status_code == 200, auditoria.text
        assert auditoria.json()["integrity"]["valid"] is True
        assert comprovante.status_code == 200, comprovante.text
        assert comprovante.json()["status"] == "closed"

    finally:
        app.dependency_overrides.pop(get_current_user, None)
