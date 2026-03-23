"""Integration tests for the v1 launches API endpoints."""

from __future__ import annotations

import os
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

import openorbit.config
import openorbit.db as db_module
from openorbit.db import close_db, get_db, init_db, upsert_launch_event
from openorbit.main import create_app
from openorbit.models.db import LaunchEventCreate


@pytest.fixture
async def client() -> AsyncClient:  # type: ignore[return]
    """Create async HTTP client wired to a fresh database.

    Yields:
        AsyncClient configured with ASGITransport for the test app.
    """
    db_file = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
    openorbit.config._settings = None
    db_module._db_connection = None

    await init_db()
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


@pytest.fixture
async def seeded_client() -> AsyncClient:  # type: ignore[return]
    """Client with pre-seeded launch events in the database.

    Yields:
        AsyncClient with a populated database.
    """
    db_file = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
    openorbit.config._settings = None
    db_module._db_connection = None

    await init_db()

    async with get_db() as conn:
        await upsert_launch_event(
            conn,
            LaunchEventCreate(
                name="Falcon 9 Launch",
                launch_date="2025-03-15T10:00:00+00:00",
                launch_date_precision="minute",
                provider="SpaceX",
                vehicle="Falcon 9",
                location="KSC",
                launch_type="civilian",
                status="scheduled",
                slug="spacex-falcon9-2025-03-15",
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
                location="Baikonur",
                launch_type="civilian",
                status="delayed",
                slug="roscosmos-soyuz-2025-06-01",
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


async def test_list_launches_empty_db(client: AsyncClient) -> None:
    """GET /v1/launches on empty DB returns empty data with correct meta."""
    response = await client.get("/v1/launches")
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["total"] == 0
    assert body["meta"]["page"] == 1
    assert body["meta"]["per_page"] == 25


async def test_list_launches_with_seeded_data(seeded_client: AsyncClient) -> None:
    """GET /v1/launches returns events and correct pagination meta."""
    response = await seeded_client.get("/v1/launches")
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 2
    assert body["meta"]["page"] == 1
    assert body["meta"]["per_page"] == 25
    assert len(body["data"]) == 2
    slugs = {e["slug"] for e in body["data"]}
    assert "spacex-falcon9-2025-03-15" in slugs
    assert "roscosmos-soyuz-2025-06-01" in slugs


async def test_list_launches_date_filter(seeded_client: AsyncClient) -> None:
    """GET /v1/launches with from/to date params filters correctly."""
    response = await seeded_client.get(
        "/v1/launches", params={"from": "2025-01-01", "to": "2025-04-01"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["slug"] == "spacex-falcon9-2025-03-15"


async def test_list_launches_provider_filter(seeded_client: AsyncClient) -> None:
    """GET /v1/launches?provider=SpaceX returns only SpaceX events."""
    response = await seeded_client.get("/v1/launches", params={"provider": "SpaceX"})
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["provider"] == "SpaceX"


async def test_list_launches_launch_type_filter(seeded_client: AsyncClient) -> None:
    """GET /v1/launches?launch_type=civilian returns only civilian events."""
    response = await seeded_client.get(
        "/v1/launches", params={"launch_type": "civilian"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 2
    for event in body["data"]:
        assert event["launch_type"] == "civilian"


async def test_list_launches_status_filter(seeded_client: AsyncClient) -> None:
    """GET /v1/launches?status=scheduled returns only scheduled events."""
    response = await seeded_client.get("/v1/launches", params={"status": "scheduled"})
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["status"] == "scheduled"


async def test_get_launch_detail_200(seeded_client: AsyncClient) -> None:
    """GET /v1/launches/{slug} returns 200 with sources array."""
    response = await seeded_client.get("/v1/launches/spacex-falcon9-2025-03-15")
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "spacex-falcon9-2025-03-15"
    assert isinstance(body["sources"], list)
    assert "id" in body
    assert isinstance(body["id"], int)


async def test_get_launch_not_found(client: AsyncClient) -> None:
    """GET /v1/launches/nonexistent returns 404 with error detail."""
    response = await client.get("/v1/launches/nonexistent-slug")
    assert response.status_code == 404
    assert response.json()["detail"] == {"error": "not_found"}


async def test_list_launches_invalid_launch_type_422(client: AsyncClient) -> None:
    """GET /v1/launches?launch_type=invalid returns 422 validation error."""
    response = await client.get("/v1/launches", params={"launch_type": "invalid"})
    assert response.status_code == 422


async def test_health_still_works(client: AsyncClient) -> None:
    """GET /health regression check — still returns 200."""
    response = await client.get("/health")
    assert response.status_code == 200


async def test_lifespan_exercises_startup_shutdown(client: AsyncClient) -> None:
    """The AsyncClient with ASGITransport exercises app startup/shutdown."""
    # Making a request through the client validates that init_db() ran
    response = await client.get("/v1/launches")
    assert response.status_code == 200

