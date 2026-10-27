
from sqlalchemy import create_engine, text
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def main():
    settings = Settings()
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )

    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("SELECT current_database(), current_user")
            )
            database, user = result.one()
            print("Conexão estabelecida com sucesso!")
            print(f"Banco: {database}")
            print(f"Usuário: {user}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
