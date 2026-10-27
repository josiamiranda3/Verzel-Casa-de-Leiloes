import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent, AuditEventType


GENESIS_HASH = "0" * 64
AUDIT_LOCK_ID = 824_731_905


def _normalize(value: Any) -> Any:
    """Converte valores Python para uma representação JSON determinística."""
    if isinstance(value, Enum):
        return value.value

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Decimal):
        return format(value, "f")

    if isinstance(value, dict):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items())
        }

    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    raise TypeError(
        f"Tipo não suportado para auditoria: {type(value).__name__}"
    )


def _calculate_hash(
    *,
    event_type: str,
    actor_user_id: int | None,
    entity_type: str,
    entity_id: int | None,
    description: str,
    event_data: dict,
    created_at: datetime,
    previous_hash: str,
) -> str:
    """Calcula o SHA-256 dos dados do evento e do hash anterior."""
    payload = {
        "event_type": event_type,
        "actor_user_id": actor_user_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "description": description,
        "event_data": _normalize(event_data),
        "created_at": created_at.isoformat(),
        "previous_hash": previous_hash,
    }

    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )

    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _acquire_audit_lock(db: Session) -> None:
    """Serializa gravações da auditoria na transação atual."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": AUDIT_LOCK_ID},
    )


def record_event(
    db: Session,
    *,
    event_type: AuditEventType,
    entity_type: str,
    description: str,
    actor_user_id: int | None = None,
    entity_id: int | None = None,
    event_data: dict | None = None,
    commit: bool = True,
) -> AuditEvent:
    """
    Registra um evento encadeado.

    Por padrão, faz commit. Use commit=False quando o evento precisar
    fazer parte da mesma transação de negócio do chamador.
    """
    if not db.in_transaction():
        db.begin()

    try:
        _acquire_audit_lock(db)

        previous_event = db.scalar(
            select(AuditEvent)
            .order_by(AuditEvent.id.desc())
            .limit(1)
        )

        previous_hash = (
            previous_event.event_hash
            if previous_event is not None
            else GENESIS_HASH
        )

        created_at = datetime.now(timezone.utc)
        normalized_data = _normalize(event_data or {})

        event_hash = _calculate_hash(
            event_type=event_type.value,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            event_data=normalized_data,
            created_at=created_at,
            previous_hash=previous_hash,
        )

        event = AuditEvent(
            event_type=event_type,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            event_data=normalized_data,
            previous_hash=previous_hash,
            event_hash=event_hash,
            created_at=created_at,
        )

        db.add(event)
        db.flush()

        if commit:
            db.commit()
            db.refresh(event)

        return event

    except Exception:
        db.rollback()
        raise


def verify_audit_chain(db: Session) -> dict:
    """Verifica os hashes e a ligação entre os eventos."""
    events = db.scalars(
        select(AuditEvent).order_by(AuditEvent.id.asc())
    ).all()

    expected_previous_hash = GENESIS_HASH

    for index, event in enumerate(events):
        if event.previous_hash != expected_previous_hash:
            return {
                "valid": False,
                "event_id": event.id,
                "reason": "O hash anterior não corresponde à cadeia.",
                "checked_events": index,
            }

        try:
            calculated_hash = _calculate_hash(
                event_type=event.event_type.value,
                actor_user_id=event.actor_user_id,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                description=event.description,
                event_data=event.event_data or {},
                created_at=event.created_at,
                previous_hash=event.previous_hash,
            )
        except (TypeError, ValueError, AttributeError) as exc:
            return {
                "valid": False,
                "event_id": event.id,
                "reason": f"Não foi possível calcular o hash: {exc}",
                "checked_events": index,
            }

        if calculated_hash != event.event_hash:
            return {
                "valid": False,
                "event_id": event.id,
                "reason": "O hash do evento não corresponde aos seus dados.",
                "checked_events": index,
            }

        expected_previous_hash = event.event_hash

    return {
        "valid": True,
        "event_id": None,
        "reason": "Todos os eventos verificados estão íntegros.",
        "checked_events": len(events),
    }