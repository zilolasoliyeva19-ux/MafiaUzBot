from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: SecretStr
    admin_ids: list[int] = Field(default_factory=list)
    database_url: str
    redis_url: str | None = None
    log_level: str = "INFO"
    default_language: str = "uz"
    min_players: int = Field(default=5, ge=4, le=30)
    max_players: int = Field(default=15, ge=5, le=50)

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [int(item) for item in value]
        raise ValueError("ADMIN_IDS must be a comma-separated list of Telegram IDs")

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        value = value.strip()
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL noto‘g‘ri")
        return normalized

    @field_validator("max_players")
    @classmethod
    def max_must_cover_min(cls, value: int, info) -> int:
        minimum = info.data.get("min_players", 5)
        if value < minimum:
            raise ValueError("MAX_PLAYERS MIN_PLAYERS dan kichik bo‘lishi mumkin emas")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
