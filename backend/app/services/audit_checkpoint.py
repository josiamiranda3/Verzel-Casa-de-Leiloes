
import json
import os
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from app.services.audit_service import verify_audit_chain


CHECKPOINT_PATH = Path(__file__).resolve().parents[2] / "audit_checkpoint.json"


def _current_chain_state(db: Session) -> dict:
    events = db.scalars(
        select(AuditEvent).order_by(AuditEvent.id.asc())
    ).all()

    return {
        "event_count": len(events),
        "last_event_id": events[-1].id if events else None,
        "last_event_hash": events[-1].event_hash if events else None,
    }


def create_audit_checkpoint(
    db: Session,
    *,
    allow_update: bool = False,
) -> dict:
    """Cria um checkpoint ou atualiza um existente mediante autorização explícita."""
    if CHECKPOINT_PATH.exists() and not allow_update:
        raise FileExistsError(
            "O checkpoint já existe. A atualização exige autorização explícita."
        )

    integrity = verify_audit_chain(db)

    if not integrity["valid"]:
        raise ValueError(
            "Não é possível criar checkpoint: cadeia de auditoria inválida."
        )

    checkpoint = _current_chain_state(db)

    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)

    file_descriptor, temporary_path = tempfile.mkstemp(
        prefix="audit_checkpoint_",
        suffix=".tmp",
        dir=CHECKPOINT_PATH.parent,
    )

    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as file:
            json.dump(checkpoint, file, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, CHECKPOINT_PATH)

    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise

    return checkpoint


def verify_audit_checkpoint(db: Session) -> dict:
    """Verifica que a cadeia atual preserve o prefixo registrado no checkpoint.

    Novos eventos legítimos podem ser anexados depois do checkpoint. Alterar,
    remover ou reordenar eventos anteriores ao checkpoint invalida a verificação.
    """
    if not CHECKPOINT_PATH.exists():
        return {
            "valid": False,
            "reason": "Checkpoint de auditoria não encontrado.",
        }

    try:
        with CHECKPOINT_PATH.open("r", encoding="utf-8") as file:
            checkpoint = json.load(file)
        expected_count = int(checkpoint.get("event_count", -1))
        expected_last_id = checkpoint.get("last_event_id")
        expected_last_hash = checkpoint.get("last_event_hash")
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {
            "valid": False,
            "reason": "Checkpoint de auditoria inválido ou ilegível.",
        }

    integrity = verify_audit_chain(db)
    if not integrity["valid"]:
        return {
            "valid": False,
            "reason": "A cadeia de hashes apresenta inconsistências.",
        }

    events = db.scalars(
        select(AuditEvent).order_by(AuditEvent.id.asc())
    ).all()
    current_count = len(events)

    if expected_count < 0 or current_count < expected_count:
        return {
            "valid": False,
            "reason": "Eventos registrados no checkpoint foram removidos.",
        }

    if expected_count == 0:
        if expected_last_id is not None or expected_last_hash is not None:
            return {
                "valid": False,
                "reason": "Checkpoint vazio contém referências inconsistentes.",
            }
        return {
            "valid": True,
            "reason": "Cadeia íntegra; checkpoint inicial preservado.",
        }

    checkpoint_event = next(
        (event for event in events if event.id == expected_last_id),
        None,
    )
    if (
        checkpoint_event is None
        or checkpoint_event.event_hash != expected_last_hash
        or sum(1 for event in events if event.id <= expected_last_id) != expected_count
    ):
        return {
            "valid": False,
            "reason": "A cadeia diverge do prefixo protegido pelo checkpoint.",
        }

    return {
        "valid": True,
        "reason": "Cadeia íntegra e prefixo do checkpoint preservado.",
    }
