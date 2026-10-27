from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    frontend_origin: str = "http://localhost:5173"

    # Origens adicionais permitidas, separadas por vírgulas
    cors_origins: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_origins(self) -> list[str]:
        origins = [
            "http://localhost:5173",
            self.frontend_origin,
        ]

        if self.cors_origins.strip():
            origins.extend(
                origin.strip()
                for origin in self.cors_origins.split(",")
                if origin.strip()
            )

        return list(dict.fromkeys(origins))


settings = Settings()