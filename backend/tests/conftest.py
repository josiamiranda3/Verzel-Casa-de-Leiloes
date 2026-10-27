
import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from app.api.deps import get_db
from app.core.database import Base
from app.main import app as fastapi_app
import app.models


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

if not TEST_DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL não está definida. "
        "Configure a URL do PostgreSQL de testes antes de executar os testes."
    )

test_url = make_url(TEST_DATABASE_URL)

if not (
    test_url.drivername == "postgresql+psycopg"
    and test_url.host in {"localhost", "127.0.0.1"}
    and test_url.port == 5433
    and test_url.database == "verzel_test"
    and test_url.username == "verzel_test"
):
    raise RuntimeError(
        "Banco de testes não autorizado. "
        "Esperado: PostgreSQL local, porta 5433, "
        "banco verzel_test e usuário verzel_test."
    )

test_engine = create_engine(
    TEST_DATABASE_URL,
    pool_pre_ping=True,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    connection = test_engine.connect()
    transaction = connection.begin()

    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )

    try:
        yield session
    finally:
        session.close()

        if transaction.is_active:
            transaction.rollback()

        connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(fastapi_app) as test_client:
          yield test_client
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)

@pytest.fixture
def isolated_client() -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        with Session(
            bind=test_engine,
            autoflush=False,
            expire_on_commit=False,
        ) as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(fastapi_app) as test_client:
            yield test_client
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def independent_engine():
    return test_engine