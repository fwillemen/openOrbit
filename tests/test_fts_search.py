"""Tests for FTS5 full-text search — fts_search(), count_fts_search(), and ?q= endpoint."""

from __future__ import annotations

import os
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

import openorbit.config
import openorbit.db as db_module
from openorbit.db import (
    close_db,
    count_fts_search,
    fts_search,
    get_db,
    init_db,
    upsert_launch_event,
)
from openorbit.main import create_app
from openorbit.models.db import LaunchEventCreate


@pytest.fixture
async def db_conn():  # type: ignore[return]
    """Provide a fresh in-memory DB connection for low-level tests."""
    db_file = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
    openorbit.config._settings = None
    db_module._db_connection = None

    await init_db()

    async with get_db() as conn:
        yield conn

    await close_db()
    if os.path.exists(db_file):
        os.unlink(db_file)
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
    openorbit.config._settings = None


@pytest.fixture
async def app_client():  # type: ignore[return]
    """Provide a fresh HTTP test client with a seeded DB."""
    db_file = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
    openorbit.config._settings = None
    db_module._db_connection = None

    await init_db()

    async with get_db() as conn:
        await upsert_launch_event(
            conn,
            LaunchEventCreate(
                name="Falcon 9 Starlink Mission",
                launch_date="2025-03-15T10:00:00+00:00",
                launch_date_precision="minute",
                provider="SpaceX",
                vehicle="Falcon 9",
                location="Cape Canaveral",
                launch_type="civilian",
                status="scheduled",
                slug="spacex-starlink-fts-test",
            ),
        )
        await upsert_launch_event(
            conn,
            LaunchEventCreate(
                name="Soyuz MS-26",
                launch_date="2025-06-01T08:00:00+00:00",
                launch_date_precision="hour",
                provider="Roscosmos",
                vehicle="Soyuz",
                location="Baikonur Cosmodrome",
                launch_type="civilian",
                status="scheduled",
                slug="roscosmos-soyuz-fts-test",
            ),
        )

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

    await close_db()
    if os.path.exists(db_file):
        os.unlink(db_file)
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
    openorbit.config._settings = None


async def test_fts_search_returns_matching_events(app_client: AsyncClient) -> None:
    """FTS search on ?q=Falcon returns the Falcon 9 event."""
    resp = await app_client.get("/v1/launches?q=Falcon")
    assert resp.status_code == 200
    body = resp.json()
    slugs = [e["slug"] for e in body["data"]]
    assert "spacex-starlink-fts-test" in slugs
    assert body["meta"]["total"] >= 1


async def test_fts_search_by_provider(app_client: AsyncClient) -> None:
    """FTS search on ?q=SpaceX matches provider field."""
    resp = await app_client.get("/v1/launches?q=SpaceX")
    assert resp.status_code == 200
    body = resp.json()
    assert any(e["provider"] == "SpaceX" for e in body["data"])


async def test_fts_search_by_vehicle(app_client: AsyncClient) -> None:
    """FTS search on ?q=Soyuz matches vehicle field and returns Roscosmos event."""
    resp = await app_client.get("/v1/launches?q=Soyuz")
    assert resp.status_code == 200
    body = resp.json()
    slugs = [e["slug"] for e in body["data"]]
    assert "roscosmos-soyuz-fts-test" in slugs


async def test_fts_search_by_location(app_client: AsyncClient) -> None:
    """FTS search on ?q=Baikonur matches location field."""
    resp = await app_client.get("/v1/launches?q=Baikonur")
    assert resp.status_code == 200
    body = resp.json()
    assert any("Baikonur" in (e.get("location") or "") for e in body["data"])


async def test_fts_search_no_match_returns_empty(app_client: AsyncClient) -> None:
    """FTS search with no matching term returns empty data and total=0."""
    resp = await app_client.get("/v1/launches?q=zzznomatch99999")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["meta"]["total"] == 0


async def test_fts_search_cursor_not_supported(app_client: AsyncClient) -> None:
    """Combining ?q= with ?cursor= returns 400."""
    resp = await app_client.get("/v1/launches?q=Falcon&cursor=abc")
    assert resp.status_code == 400
    assert "cursor" in resp.json()["detail"]["message"].lower()


async def test_fts_search_helper_returns_events(db_conn) -> None:  # type: ignore[no-untyped-def]
    """fts_search() returns matching LaunchEvent objects."""
    await upsert_launch_event(
        db_conn,
        LaunchEventCreate(
            name="Vulcan Centaur debut",
            launch_date="2025-04-10T12:00:00+00:00",
            launch_date_precision="hour",
            provider="ULA",
            vehicle="Vulcan Centaur",
            location="SLC-41",
            launch_type="civilian",
            status="scheduled",
            slug="ula-vulcan-fts-test",
        ),
    )
    results = await fts_search(db_conn, "Vulcan")
    assert len(results) >= 1
    assert any(e.slug == "ula-vulcan-fts-test" for e in results)


async def test_count_fts_search_helper(db_conn) -> None:  # type: ignore[no-untyped-def]
    """count_fts_search() returns correct count."""
    await upsert_launch_event(
        db_conn,
        LaunchEventCreate(
            name="Ariane 6 Launch",
            launch_date="2025-05-20T14:00:00+00:00",
            launch_date_precision="hour",
            provider="Arianespace",
            vehicle="Ariane 6",
            location="Kourou",
            launch_type="civilian",
            status="scheduled",
            slug="arianespace-ariane6-fts-test",
        ),
    )
    count = await count_fts_search(db_conn, "Ariane")
    assert count >= 1
    count_none = await count_fts_search(db_conn, "zzznomatch99999")
    assert count_none == 0


async def test_fts_search_empty_query_returns_empty(db_conn) -> None:  # type: ignore[no-untyped-def]
    """fts_search() and count_fts_search() return empty for blank/empty query."""
    assert await fts_search(db_conn, "") == []
    assert await fts_search(db_conn, "   ") == []
    assert await count_fts_search(db_conn, "") == 0


async def test_fts_search_survives_remigration(db_conn) -> None:  # type: ignore[no-untyped-def]
    """FTS table still works after a simulated rebuild (INSERT ... rebuild)."""
    await upsert_launch_event(
        db_conn,
        LaunchEventCreate(
            name="New Shepard suborbital",
            launch_date="2025-07-01T09:00:00+00:00",
            launch_date_precision="hour",
            provider="Blue Origin",
            vehicle="New Shepard",
            location="Van Horn",
            launch_type="civilian",
            status="scheduled",
            slug="blueorigin-newshepard-fts-test",
        ),
    )
    # Simulate a content-table rebuild
    await db_conn.execute(
        "INSERT INTO launch_events_fts(launch_events_fts) VALUES('rebuild')"
    )
    await db_conn.commit()

    results = await fts_search(db_conn, "Shepard")
    assert any(e.slug == "blueorigin-newshepard-fts-test" for e in results)
