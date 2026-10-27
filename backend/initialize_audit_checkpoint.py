"""Inicializa o checkpoint de auditoria do ambiente configurado em .env."""
import argparse

from app.core.database import SessionLocal
from app.services.audit_checkpoint import CHECKPOINT_PATH, create_audit_checkpoint
from app.services.audit_service import verify_audit_chain


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-reviewed", action="store_true",
                        help="Atualiza checkpoint existente somente após revisão manual.")
    args = parser.parse_args()
    if CHECKPOINT_PATH.exists() and not args.update_reviewed:
        parser.error("Checkpoint já existe. Para atualizá-lo, revise a cadeia e use --update-reviewed.")
    with SessionLocal() as db:
        integrity = verify_audit_chain(db)
        if not integrity["valid"]:
            raise RuntimeError(f"Cadeia de auditoria inválida: {integrity}")
        checkpoint = create_audit_checkpoint(db, allow_update=args.update_reviewed)
        print("Checkpoint de auditoria criado/atualizado:", checkpoint)


if __name__ == "__main__":
    main()
