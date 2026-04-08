"""Application configuration management.

Loads all settings from environment variables with sensible defaults.
Follows 12-factor app principles for Docker-compatibility and security.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All configuration is sourced from the environment to support
    deployment across dev/staging/prod without code changes.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    VERSION: str = "0.1.0"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./openorbit.db"

    # Scraper settings
    SCRAPER_DELAY_SECONDS: int = 2
    SCRAPER_TIMEOUT_SECONDS: int = 30
    SCRAPER_MAX_RETRIES: int = 3
    SCRAPER_SSL_VERIFY: bool = True

    # Authentication
    OPENORBIT_ADMIN_KEY: str | None = None

    # Twitter/X API
    TWITTER_BEARER_TOKEN: str | None = None

    # CORS — comma-separated allowed origins, or "*" for public/development.
    # In production, set to your frontend domain, e.g. "https://app.example.com"
    CORS_ORIGINS: str = "*"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Application settings singleton.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
