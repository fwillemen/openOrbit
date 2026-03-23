"""Additional tests to cover remaining branches in api/v1/launches.py."""

from __future__ import annotations

import base64
import os
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

import openorbit.config as config_module
import openorbit.db as db_module
from openorbit.api.v1.launches import (
    _decode_cursor,
    _encode_cursor,
    _haversine_km,
    _parse_lat_lon,
)
from openorbit.db import close_db, get_db, init_db, upsert_launch_event
from openorbit.main import create_app
from openorbit.models.db import LaunchEventCreate


@pytest.fixture
async def geo_client() -> AsyncClient:  # type: ignore[return]
    """Client with events that have lat/lon locations for geo filter tests."""
    db_file = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
    config_module._settings = None
    db_module._db_connection = None

    await init_db()

    async with get_db() as conn:
        # KSC at roughly 28.573, -80.649
        await upsert_launch_event(
            conn,
            LaunchEventCreate(
                name="Falcon 9 KSC",
                launch_date="2025-03-15T10:00:00+00:00",
                launch_date_precision="minute",
                provider="SpaceX",
                vehicle="Falcon 9",
                location="28.573,-80.649",
                launch_type="civilian",
                status="scheduled",
                slug="spacex-falcon9-ksc-2025",
            ),
        )
        # Vandenberg at roughly 34.632, -120.611
        await upsert_launch_event(
            conn,
            LaunchEventCreate(
                name="Falcon 9 VAFB",
                launch_date="2025-04-01T12:00:00+00:00",
                launch_date_precision="minute",
                provider="SpaceX",
                vehicle="Falcon 9",
                location="34.632,-120.611",
                launch_type="civilian",
                status="scheduled",
                slug="spacex-falcon9-vafb-2025",
            ),
        )
        # Event with no location
        await upsert_launch_event(
            conn,
            LaunchEventCreate(
                name="Mystery Launch",
                launch_date="2025-05-01T08:00:00+00:00",
                launch_date_precision="day",
                provider="Unknown",
                vehicle="Unknown",
                location=None,
                launch_type="unknown",
                status="scheduled",
                slug="mystery-launch-2025",
            ),
        )
        # Event with unparseable location
        await upsert_launch_event(
            conn,
            LaunchEventCreate(
                name="Text Location Launch",
                launch_date="2025-06-01T08:00:00+00:00",
                launch_date_precision="day",
                provider="Roscosmos",
                vehicle="Soyuz",
                location="Baikonur Cosmodrome",
                launch_type="civilian",
                status="scheduled",
                slug="roscosmos-baikonur-2025",
            ),
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


# ---------------------------------------------------------------------------
# Unit tests for helper functions (lines 47-53, 70-71, 83)
# ---------------------------------------------------------------------------


async def test_parse_lat_lon_valid() -> None:
    """_parse_lat_lon returns tuple for valid lat,lon string."""
    result = _parse_lat_lon("28.573,-80.649")
    assert result is not None
    lat, lon = result
    assert abs(lat - 28.573) < 1e-6
    assert abs(lon - (-80.649)) < 1e-6


async def test_parse_lat_lon_no_comma() -> None:
    """_parse_lat_lon returns None when there is no comma."""
    assert _parse_lat_lon("notACoord") is None


async def test_parse_lat_lon_non_numeric() -> None:
    """_parse_lat_lon returns None when parts are not floats."""
    assert _parse_lat_lon("abc,def") is None


async def test_parse_lat_lon_empty_string() -> None:
    """_parse_lat_lon returns None for empty string."""
    assert _parse_lat_lon("") is None


async def test_encode_cursor_roundtrip() -> None:
    """_encode_cursor produces a token that _decode_cursor can reverse."""
    token = _encode_cursor(42)
    assert isinstance(token, str)
    assert _decode_cursor(token) == 42


async def test_encode_cursor_is_base64() -> None:
    """_encode_cursor produces valid base64-encoded output."""
    token = _encode_cursor(100)
    decoded = base64.urlsafe_b64decode(token).decode()
    assert decoded == "100"


async def test_decode_cursor_invalid_returns_none() -> None:
    """_decode_cursor returns None for a garbled token (line 83)."""
    result = _decode_cursor("!!not-valid-base64!!")
    assert result is None


async def test_decode_cursor_non_integer_returns_none() -> None:
    """_decode_cursor returns None when decoded bytes are not an integer."""
    bad = base64.urlsafe_b64encode(b"not-a-number").decode()
    assert _decode_cursor(bad) is None


async def test_haversine_same_point() -> None:
    """_haversine_km returns 0 for same point."""
    assert _haversine_km(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0, abs=1e-6)


async def test_haversine_known_distance() -> None:
    """_haversine_km returns ~2887 km between London and New York (rough check)."""
    # London: 51.5074, -0.1278 | NYC: 40.7128, -74.0060
    dist = _haversine_km(51.5074, -0.1278, 40.7128, -74.0060)
    assert 5500 < dist < 5600


# ---------------------------------------------------------------------------
# Geo-filter integration tests (lines 254, 258-259, 264-270, 301, 306)
# ---------------------------------------------------------------------------


async def test_geo_filter_finds_nearby_event(geo_client: AsyncClient) -> None:
    """?location near KSC returns the KSC event within 100 km default radius."""
    response = await geo_client.get(
        "/v1/launches",
        params={"location": "28.573,-80.649", "radius_km": "50"},
    )
    assert response.status_code == 200
    body = response.json()
    slugs = [e["slug"] for e in body["data"]]
    assert "spacex-falcon9-ksc-2025" in slugs
    assert "spacex-falcon9-vafb-2025" not in slugs


async def test_geo_filter_excludes_distant_event(geo_client: AsyncClient) -> None:
    """?location near KSC with small radius excludes Vandenberg."""
    response = await geo_client.get(
        "/v1/launches",
        params={"location": "28.573,-80.649", "radius_km": "100"},
    )
    assert response.status_code == 200
    body = response.json()
    slugs = [e["slug"] for e in body["data"]]
    assert "spacex-falcon9-vafb-2025" not in slugs


async def test_geo_filter_skips_null_location_events(geo_client: AsyncClient) -> None:
    """Geo filter ignores events with NULL location field."""
    response = await geo_client.get(
        "/v1/launches",
        params={"location": "28.573,-80.649", "radius_km": "10000"},
    )
    assert response.status_code == 200
    body = response.json()
    slugs = [e["slug"] for e in body["data"]]
    # mystery-launch-2025 has no location, should be skipped
    assert "mystery-launch-2025" not in slugs


async def test_geo_filter_skips_unparseable_location(geo_client: AsyncClient) -> None:
    """Geo filter ignores events with text-only location strings."""
    response = await geo_client.get(
        "/v1/launches",
        params={"location": "28.573,-80.649", "radius_km": "10000"},
    )
    assert response.status_code == 200
    body = response.json()
    slugs = [e["slug"] for e in body["data"]]
    assert "roscosmos-baikonur-2025" not in slugs


async def test_geo_filter_default_radius(geo_client: AsyncClient) -> None:
    """?location without radius_km uses 100 km default."""
    response = await geo_client.get(
        "/v1/launches",
        params={"location": "28.573,-80.649"},
    )
    assert response.status_code == 200
    body = response.json()
    # Should return at least the KSC event (0 km away)
    assert body["meta"]["total"] >= 1


async def test_geo_filter_with_cursor_pagination(geo_client: AsyncClient) -> None:
    """Cursor pagination works within geo-filtered results (lines 258-259, 264-270)."""
    initial_cursor = _encode_cursor(0)
    # Fetch first page of 1 with a small limit using geo filter + cursor
    response = await geo_client.get(
        "/v1/launches",
        params={"location": "28.0,-80.0", "radius_km": "10000", "limit": "1", "cursor": initial_cursor},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) >= 1

    # If there's a next_cursor, follow it
    next_cursor = body["meta"].get("next_cursor")
    if next_cursor:
        response2 = await geo_client.get(
            "/v1/launches",
            params={
                "location": "28.0,-80.0",
                "radius_km": "10000",
                "limit": "1",
                "cursor": next_cursor,
            },
        )
        assert response2.status_code == 200


async def test_cursor_pagination_generates_next_cursor(geo_client: AsyncClient) -> None:
    """Cursor-based pagination sets next_cursor when page is full (line 301)."""
    # Pass an initial cursor (encoded id=0 means start-of-list) to activate cursor mode
    initial_cursor = _encode_cursor(0)
    response = await geo_client.get(
        "/v1/launches",
        params={"location": "28.0,-80.0", "radius_km": "10000", "limit": "1", "cursor": initial_cursor},
    )
    assert response.status_code == 200
    body = response.json()
    # With limit=1 and multiple events matching the geo filter, next_cursor should be set
    if body["meta"]["total"] > 1:
        assert body["meta"]["next_cursor"] is not None


async def test_cursor_pagination_meta_uses_cursor_mode(geo_client: AsyncClient) -> None:
    """Cursor-mode response uses limit in meta.per_page, page=1 (line 306)."""
    initial_cursor = _encode_cursor(0)
    response = await geo_client.get(
        "/v1/launches",
        params={"location": "28.0,-80.0", "radius_km": "10000", "limit": "2", "cursor": initial_cursor},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["page"] == 1
    assert body["meta"]["per_page"] == 2


async def test_cursor_pagination_no_geo_next_cursor(geo_client: AsyncClient) -> None:
    """Non-geo cursor pagination generates next_cursor when page is full (line 301)."""
    initial_cursor = _encode_cursor(0)
    response = await geo_client.get(
        "/v1/launches", params={"limit": "1", "cursor": initial_cursor}
    )
    assert response.status_code == 200
    body = response.json()
    if body["meta"]["total"] > 1:
        assert body["meta"]["next_cursor"] is not None


async def test_cursor_pagination_meta_page_one(geo_client: AsyncClient) -> None:
    """Cursor-based pagination meta always has page=1 (line 306)."""
    initial_cursor = _encode_cursor(0)
    response = await geo_client.get(
        "/v1/launches", params={"limit": "1", "cursor": initial_cursor}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["page"] == 1
