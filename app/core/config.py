from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    bot_token: SecretStr = SecretStr("")
    database_url: str = "postgresql+asyncpg://goofish:goofish@localhost:5432/goofish"
    redis_url: str = "redis://localhost:6379/0"
    goofish_provider: Literal["mock", "browser", "api"] = "mock"
    goofish_api_url: str | None = None
    goofish_browser_headless: bool = True
    goofish_browser_channel: str = "chrome"
    goofish_browser_profile: str = ".run/goofish-profile"
    goofish_timeout_seconds: int = Field(30, ge=5, le=120)
    goofish_min_interval_seconds: float = Field(3, ge=1, le=60)
    ai_provider: str = "disabled"
    ai_api_key: SecretStr | None = None
    admin_token: SecretStr | None = None
    log_level: str = "INFO"
    poll_fast_seconds: int = Field(300, ge=60)
    poll_standard_seconds: int = Field(900, ge=60)
    poll_economy_seconds: int = Field(3600, ge=60)


@lru_cache
def get_settings() -> Settings:
    return Settings()
