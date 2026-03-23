"""Tests for main.py — configure_logging() and lifespan coverage."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

import openorbit.config as config_module


@pytest.fixture(autouse=True)
def reset_settings() -> None:  # type: ignore[return]
    """Reset cached settings between tests."""
    original = config_module._settings
    yield
    config_module._settings = original


async def test_configure_logging_dev_mode() -> None:
    """configure_logging() with LOG_LEVEL=DEBUG sets dev (console) processors."""
    config_module._settings = None
    os.environ["LOG_LEVEL"] = "DEBUG"
    try:
        from openorbit.main import configure_logging

        configure_logging()  # should not raise
    finally:
        os.environ.pop("LOG_LEVEL", None)
        config_module._settings = None


async def test_configure_logging_info_mode() -> None:
    """configure_logging() with LOG_LEVEL=INFO uses dev (console) processors."""
    config_module._settings = None
    os.environ["LOG_LEVEL"] = "INFO"
    try:
        from openorbit.main import configure_logging

        configure_logging()
    finally:
        os.environ.pop("LOG_LEVEL", None)
        config_module._settings = None


async def test_configure_logging_production_mode() -> None:
    """configure_logging() with LOG_LEVEL=WARNING uses JSON processors."""
    config_module._settings = None
    os.environ["LOG_LEVEL"] = "WARNING"
    try:
        from openorbit.main import configure_logging

        configure_logging()
    finally:
        os.environ.pop("LOG_LEVEL", None)
        config_module._settings = None


async def test_configure_logging_error_mode() -> None:
    """configure_logging() with LOG_LEVEL=ERROR uses JSON processors."""
    config_module._settings = None
    os.environ["LOG_LEVEL"] = "ERROR"
    try:
        from openorbit.main import configure_logging

        configure_logging()
    finally:
        os.environ.pop("LOG_LEVEL", None)
        config_module._settings = None


async def test_lifespan_startup_and_shutdown() -> None:
    """lifespan() calls init_db, start_scheduler on enter and stop_scheduler, close_db on exit."""
    mock_init = AsyncMock()
    mock_close = AsyncMock()
    mock_start = AsyncMock()
    mock_stop = AsyncMock()

    with (
        patch("openorbit.main.init_db", mock_init),
        patch("openorbit.main.close_db", mock_close),
        patch("openorbit.main.start_scheduler", mock_start),
        patch("openorbit.main.stop_scheduler", mock_stop),
    ):
        from openorbit.main import create_app, lifespan

        app = create_app()
        async with lifespan(app):
            mock_init.assert_called_once()
            mock_start.assert_called_once()
            mock_close.assert_not_called()
            mock_stop.assert_not_called()

        mock_stop.assert_called_once()
        mock_close.assert_called_once()


async def test_lifespan_shutdown_order() -> None:
    """lifespan() calls stop_scheduler before close_db on shutdown."""
    call_order: list[str] = []

    async def fake_init() -> None:
        call_order.append("init_db")

    async def fake_close() -> None:
        call_order.append("close_db")

    async def fake_start() -> None:
        call_order.append("start_scheduler")

    async def fake_stop() -> None:
        call_order.append("stop_scheduler")

    with (
        patch("openorbit.main.init_db", fake_init),
        patch("openorbit.main.close_db", fake_close),
        patch("openorbit.main.start_scheduler", fake_start),
        patch("openorbit.main.stop_scheduler", fake_stop),
    ):
        from openorbit.main import create_app, lifespan

        app = create_app()
        async with lifespan(app):
            pass

    assert call_order == ["init_db", "start_scheduler", "stop_scheduler", "close_db"]
