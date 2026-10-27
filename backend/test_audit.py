
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.audit_event import AuditEvent, AuditEventType
from app.services.audit_service import record_event, verify_audit_chain


def main():
    db = SessionLocal()

    try:
        # Inicia uma transação que será revertida ao final.
        db.begin()

        event = record_event(
            db,
            event_type=AuditEventType.LOT_CREATED,
            entity_type="test",
            entity_id=999999,
            description="Teste temporário da cadeia de auditoria",
            event_data={"test": True},
            commit=False,
        )

        db.flush()

        # Confere o hash do evento criado dentro da transação.
        result = verify_audit_chain(db)
        print("Verificação:", result)

        if not result["valid"]:
            raise RuntimeError("A verificação da cadeia falhou.")

        print("Hash gerado:", event.event_hash)
        print("Hash anterior:", event.previous_hash)

    finally:
        db.rollback()
        db.close()

    print("Teste encerrado; transação revertida.")


if __name__ == "__main__":
    main()
