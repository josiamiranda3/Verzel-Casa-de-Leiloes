
import pytest

from app.models.audit_event import AuditEventType
from app.services.audit_checkpoint import (
    create_audit_checkpoint,
    verify_audit_checkpoint,
)
from app.services.audit_service import record_event


def create_test_event(db_session, description="Evento de teste"):
    return record_event(
        db_session,
        event_type=AuditEventType.LOT_CREATED,
        entity_type="lot",
        entity_id=1,
        description=description,
        event_data={"source": "checkpoint_test"},
        commit=False,
    )


def use_temporary_checkpoint(monkeypatch, tmp_path):
    checkpoint_path = tmp_path / "audit_checkpoint.json"

    monkeypatch.setattr(
        "app.services.audit_checkpoint.CHECKPOINT_PATH",
        checkpoint_path,
    )

    return checkpoint_path


def test_checkpoint_is_created_and_verified(
    db_session, monkeypatch, tmp_path
):
    checkpoint_path = use_temporary_checkpoint(monkeypatch, tmp_path)

    create_test_event(db_session)

    checkpoint = create_audit_checkpoint(db_session)
    result = verify_audit_checkpoint(db_session)

    assert checkpoint_path.exists()
    assert checkpoint["event_count"] > 0
    assert result["valid"] is True


def test_checkpoint_detects_deleted_last_event(
    db_session, monkeypatch, tmp_path
):
    checkpoint_path = use_temporary_checkpoint(monkeypatch, tmp_path)

    event = create_test_event(db_session)
    db_session.flush()

    create_audit_checkpoint(db_session)

    db_session.delete(event)
    db_session.flush()

    result = verify_audit_checkpoint(db_session)

    assert result["valid"] is False
    assert result["reason"] == (
        "Eventos registrados no checkpoint foram removidos."
    )


def test_checkpoint_rejects_invalid_chain(
    db_session, monkeypatch, tmp_path
):
    checkpoint_path = use_temporary_checkpoint(monkeypatch, tmp_path)

    event = create_test_event(db_session)
    db_session.flush()

    event.event_data = {"source": "tampered"}
    db_session.flush()

    with pytest.raises(ValueError, match="cadeia de auditoria inválida"):
        create_audit_checkpoint(db_session)

    assert not checkpoint_path.exists()


def test_missing_checkpoint_is_reported(
    db_session, monkeypatch, tmp_path
):
    use_temporary_checkpoint(monkeypatch, tmp_path)

    result = verify_audit_checkpoint(db_session)

    assert result["valid"] is False
    assert result["reason"] == "Checkpoint de auditoria não encontrado."


def test_existing_checkpoint_cannot_be_overwritten_by_default(
    db_session, monkeypatch, tmp_path
):
    checkpoint_path = use_temporary_checkpoint(monkeypatch, tmp_path)

    create_test_event(db_session)
    db_session.flush()

    original_checkpoint = create_audit_checkpoint(db_session)
    original_content = checkpoint_path.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError, match="checkpoint já existe"):
        create_audit_checkpoint(db_session)

    assert checkpoint_path.read_text(encoding="utf-8") == original_content
    assert original_checkpoint["event_count"] > 0


def test_checkpoint_can_be_updated_explicitly_when_chain_is_valid(
    db_session, monkeypatch, tmp_path
):
    checkpoint_path = use_temporary_checkpoint(monkeypatch, tmp_path)

    create_test_event(db_session, description="Evento inicial")
    db_session.flush()

    original_checkpoint = create_audit_checkpoint(db_session)

    create_test_event(db_session, description="Novo evento legítimo")
    db_session.flush()

    with pytest.raises(FileExistsError):
        create_audit_checkpoint(db_session)

    updated_checkpoint = create_audit_checkpoint(
        db_session,
        allow_update=True,
    )

    result = verify_audit_checkpoint(db_session)

    assert updated_checkpoint["event_count"] == (
        original_checkpoint["event_count"] + 1
    )
    assert updated_checkpoint["last_event_id"] != (
        original_checkpoint["last_event_id"]
    )
    assert result["valid"] is True
    assert checkpoint_path.exists()
