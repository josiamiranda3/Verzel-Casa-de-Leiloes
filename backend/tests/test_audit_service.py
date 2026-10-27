
import pytest

from app.models.audit_event import AuditEvent, AuditEventType
from app.services.audit_service import (
    GENESIS_HASH,
    record_event,
    verify_audit_chain,
)


def _create_event(db_session, *, description="Evento de teste", event_data=None):
    return record_event(
        db_session,
        event_type=AuditEventType.LOT_CREATED,
        entity_type="lot",
        entity_id=1,
        description=description,
        event_data=event_data or {"source": "test"},
        commit=False,
    )


def test_audit_chain_is_valid_when_events_are_unchanged(db_session):
    first = _create_event(db_session, description="Primeiro evento")
    db_session.flush()

    second = _create_event(db_session, description="Segundo evento")
    db_session.flush()

    assert first.previous_hash == GENESIS_HASH
    assert second.previous_hash == first.event_hash

    result = verify_audit_chain(db_session)

    assert result["valid"] is True
    assert result["checked_events"] == 2


def test_audit_chain_detects_event_data_tampering(db_session):
    event = _create_event(db_session)
    db_session.flush()

    event.event_data = {"source": "modified"}
    db_session.flush()

    result = verify_audit_chain(db_session)

    assert result["valid"] is False
    assert result["event_id"] == event.id
    assert result["reason"] == (
        "O hash do evento não corresponde aos seus dados."
    )


def test_audit_chain_detects_previous_hash_tampering(db_session):
    first = _create_event(db_session, description="Primeiro evento")
    db_session.flush()

    second = _create_event(db_session, description="Segundo evento")
    db_session.flush()

    second.previous_hash = "f" * 64
    db_session.flush()

    result = verify_audit_chain(db_session)

    assert result["valid"] is False
    assert result["event_id"] == second.id
    assert result["reason"] == "O hash anterior não corresponde à cadeia."


def test_audit_chain_detects_deleted_middle_event(db_session):
    _create_event(
        db_session,
        description="Primeiro evento",
    )
    db_session.flush()

    second = _create_event(
        db_session,
        description="Evento que será excluído",
    )
    db_session.flush()

    third = _create_event(
        db_session,
        description="Terceiro evento",
    )
    db_session.flush()

    # Simula a exclusão de um evento intermediário.
    db_session.delete(second)
    db_session.flush()

    result = verify_audit_chain(db_session)

    assert result["valid"] is False
    assert result["event_id"] == third.id
    assert result["reason"] == (
        "O hash anterior não corresponde à cadeia."
    )


def test_audit_chain_alone_cannot_detect_deleted_last_event(db_session):
    _create_event(
        db_session,
        description="Primeiro evento",
    )
    db_session.flush()

    last = _create_event(
        db_session,
        description="Último evento",
    )
    db_session.flush()

    # Simula a exclusão do último evento da cadeia.
    db_session.delete(last)
    db_session.flush()

    result = verify_audit_chain(db_session)

    # Sem um checkpoint externo, a cadeia restante pode parecer íntegra.
    assert result["valid"] is True
