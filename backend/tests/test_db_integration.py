
from sqlalchemy import inspect, select, text

from app.core.database import Base
from app.models.user import User, UserRole
import app.models  # Registra todos os modelos


def test_postgres_test_database_has_expected_tables(db_session):
    inspector = inspect(db_session.get_bind())
    tables = set(inspector.get_table_names())

    expected_tables = {
        "users",
        "lots",
        "bids",
        "wallets",
        "wallet_transactions",
        "audit_events",
        "alembic_version",
    }

    assert expected_tables.issubset(tables)


def test_postgres_test_database_connection(db_session):
    result = db_session.execute(text("SELECT 1")).scalar_one()

    assert result == 1


def test_sqlalchemy_metadata_contains_all_application_tables():
    expected_tables = {
        "users",
        "lots",
        "bids",
        "wallets",
        "wallet_transactions",
        "audit_events",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_postgres_can_insert_and_query_user(db_session):
    user = User(
        name="Usuário de Integração",
        email="integracao.rollback@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.BIDDER,
    )

    db_session.add(user)
    db_session.flush()

    user_id = user.id

    assert user_id is not None

    saved_user = db_session.scalar(
        select(User).where(User.id == user_id)
    )

    assert saved_user is not None
    assert saved_user.name == "Usuário de Integração"
    assert saved_user.email == "integracao.rollback@example.test"
    assert saved_user.role == UserRole.BIDDER
