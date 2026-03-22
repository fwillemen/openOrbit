"""Tests for configuration management."""

from __future__ import annotations

import pytest

from openorbit.config import Settings, get_settings


def test_settings_load_defaults() -> None:
    """Test that settings load with sensible defaults."""
    settings = Settings()

    assert settings.VERSION == "0.1.0"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./openorbit.db"


def test_settings_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that settings can be overridden via environment variables."""
    monkeypatch.setenv("VERSION", "1.2.3")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

    settings = Settings()

    assert settings.VERSION == "1.2.3"
    assert settings.LOG_LEVEL == "DEBUG"
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./test.db"


def test_get_settings_returns_singleton() -> None:
    """Test that get_settings returns cached instance."""
    # Clear the global cache first
    import openorbit.config

    openorbit.config._settings = None

    settings1 = get_settings()
    settings2 = get_settings()

    assert settings1 is settings2
