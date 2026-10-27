
import argparse
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.services.audit_checkpoint import (
    CHECKPOINT_PATH,
    create_audit_checkpoint,
)
from app.services.audit_service import verify_audit_chain


def main():
    parser = argparse.ArgumentParser(
        description="Gerencia manualmente o checkpoint de auditoria."
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Autoriza substituir um checkpoint existente.",
    )
    parser.add_argument(
        "--confirm-reviewed",
        action="store_true",
        help=(
            "Confirma que as alterações desde o checkpoint anterior "
            "foram revisadas manualmente."
        ),
    )
    args = parser.parse_args()

    if args.confirm_reviewed and not args.update:
        parser.error("--confirm-reviewed exige --update.")

    if args.update and not args.confirm_reviewed:
        parser.error(
            "A atualização exige --update --confirm-reviewed."
        )

    if CHECKPOINT_PATH.exists() and not args.update:
        raise RuntimeError(
            "O checkpoint já existe. Revise as alterações e use "
            "--update --confirm-reviewed somente após a revisão."
        )

    database_url = os.getenv("TEST_DATABASE_URL")

    if not database_url:
        raise RuntimeError("TEST_DATABASE_URL não está definida.")

    url = make_url(database_url)

    authorized = (
        url.drivername == "postgresql+psycopg"
        and url.host in {"localhost", "127.0.0.1"}
        and url.port == 5433
        and url.database == "verzel_test"
        and url.username == "verzel_test"
    )

    if not authorized:
        raise RuntimeError(
            "Banco não autorizado. Esperado PostgreSQL local "
            "na porta 5433, banco verzel_test e usuário verzel_test."
        )

    engine = create_engine(database_url, pool_pre_ping=True)

    try:
        with Session(engine) as db:
            integrity = verify_audit_chain(db)

            if not integrity["valid"]:
                raise RuntimeError(
                    f"Cadeia de auditoria inválida: {integrity}"
                )

            checkpoint = create_audit_checkpoint(
                db,
                allow_update=args.update,
            )

            print("Checkpoint registrado com sucesso.")
            print(checkpoint)

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
