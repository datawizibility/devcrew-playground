from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://smartap:smartap@localhost:5432/smartap"
    database_url_test: str = "postgresql+asyncpg://smartap:smartap@localhost:5432/smartap_test"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    environment: str = "dev"


settings = Settings()