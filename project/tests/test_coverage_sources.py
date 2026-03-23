"""Tests for GET /v1/sources endpoint coverage."""

from __future__ import annotations

import os
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

import openorbit.config as config_module
import openorbit.db as db_module
from openorbit.db import close_db, get_db, init_db, register_osint_source
from openorbit.main import create_app


@pytest.fixture
async def sources_client() -> AsyncClient:  # type: ignore[return]
    """Async client with a clean database for sources tests."""
    db_file = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
    config_module._settings = None
    db_module._db_connection = None

    await init_db()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    await close_db()
    if os.path.exists(db_file):
        os.unlink(db_file)
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
    config_module._settings = None


@pytest.fixture
async def sources_client_with_source() -> AsyncClient:  # type: ignore[return]
    """Async client with one OSINT source pre-seeded."""
    db_file = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
    config_module._settings = None
    db_module._db_connection = None

    await init_db()

    async with get_db() as conn:
        await register_osint_source(
            conn,
            name="Test Source",
            url="https://example.com/launches",
            scraper_class="openorbit.scrapers.commercial.CommercialScraper",
            enabled=True,
        )

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    await close_db()
    if os.path.exists(db_file):
        os.unlink(db_file)
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
    config_module._settings = None


async def test_list_sources_empty_returns_200(sources_client: AsyncClient) -> None:
    """GET /v1/sources returns 200 with empty data list when no sources exist."""
    response = await sources_client.get("/v1/sources")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert body["data"] == []


async def test_list_sources_with_source_returns_data(
    sources_client_with_source: AsyncClient,
) -> None:
    """GET /v1/sources returns source record with all expected fields."""
    response = await sources_client_with_source.get("/v1/sources")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert len(body["data"]) == 1
    source = body["data"][0]
    assert source["name"] == "Test Source"
    assert source["url"] == "https://example.com/launches"
    assert source["enabled"] is True
    assert "id" in source
    assert "event_count" in source
    assert source["event_count"] == 0
    assert "last_scraped_at" in source
    assert source["last_scraped_at"] is None
    assert "last_error" in source


async def test_list_sources_response_structure(
    sources_client_with_source: AsyncClient,
) -> None:
    """GET /v1/sources response has all required fields in each source record."""
    response = await sources_client_with_source.get("/v1/sources")
    assert response.status_code == 200
    body = response.json()
    source = body["data"][0]
    required_fields = {
        "id",
        "name",
        "url",
        "enabled",
        "refresh_interval_hours",
        "last_scraped_at",
        "event_count",
        "last_error",
    }
    assert required_fields.issubset(source.keys())
