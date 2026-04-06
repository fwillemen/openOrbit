"""Tests for SpaceXOfficialScraper — all HTTP calls are mocked via respx."""

from __future__ import annotations

import json
import os

import httpx
import pytest
import respx

from openorbit.db import close_db, get_db, init_db
from openorbit.scrapers.spacex_official import SpaceXOfficialScraper


@pytest.fixture
async def db_connection():
    """Initialize an in-memory test database with cleanup."""
    from openorbit import config

    config._settings = None
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    await init_db()
    async with get_db() as conn:
        yield conn

    await close_db()
    config._settings = None


SPACEX_QUERY_URL = "https://api.spacexdata.com/v4/launches/query"


def _make_spacex_response(docs: list[dict]) -> dict:
    """Build minimal SpaceX query response envelope."""
    return {
        "docs": docs,
        "totalDocs": len(docs),
        "limit": len(docs),
        "totalPages": 1,
        "page": 1,
        "pagingCounter": 1,
        "hasPrevPage": False,
        "hasNextPage": False,
        "prevPage": None,
        "nextPage": None,
    }


def _launch_doc(
    launch_id: str,
    name: str,
    date_utc: str,
    upcoming: bool,
    success: bool | None,
) -> dict:
    return {
        "id": launch_id,
        "name": name,
        "date_utc": date_utc,
        "upcoming": upcoming,
        "success": success,
        "launchpad": "5e9e4502f5090995de566f86",
        "rocket": "5e9d0d95eda69973a809d1ec",
        "details": "Nominal mission profile",
    }


class TestSpaceXOfficialScraperParse:
    """Unit tests for SpaceXOfficialScraper.parse()."""

    def test_parse_returns_launch_events(self) -> None:
        """parse() returns LaunchEventCreate items for valid docs."""
        scraper = SpaceXOfficialScraper()
        payload = _make_spacex_response(
            [
                _launch_doc(
                    launch_id="abc123",
                    name="Starlink 10-1",
                    date_utc="2026-03-01T12:00:00.000Z",
                    upcoming=True,
                    success=None,
                )
            ]
        )

        events = scraper.parse(json.dumps(payload))
        assert len(events) == 1
        assert events[0].provider == "SpaceX"
        assert events[0].status == "scheduled"
        assert events[0].slug == "spx-abc123"

    def test_parse_invalid_json_raises(self) -> None:
        """parse() raises ValueError for invalid json payloads."""
        scraper = SpaceXOfficialScraper()
        with pytest.raises(ValueError, match="Invalid JSON"):
            scraper.parse("not valid json {{{")

    def test_parse_skips_malformed_docs(self) -> None:
        """parse() skips malformed docs but keeps valid ones."""
        scraper = SpaceXOfficialScraper()
        payload = _make_spacex_response(
            [
                _launch_doc(
                    launch_id="valid1",
                    name="Transporter",
                    date_utc="2026-04-01T12:00:00.000Z",
                    upcoming=True,
                    success=None,
                ),
                {
                    "id": "bad1",
                    "date_utc": "2026-05-01T12:00:00.000Z",
                    "upcoming": True,
                },
            ]
        )
        events = scraper.parse(json.dumps(payload))
        assert len(events) == 1
        assert events[0].slug == "spx-valid1"


class TestSpaceXOfficialScraperFetch:
    """Unit tests for _fetch_with_retry()."""

    @respx.mock
    async def test_fetch_success(self, db_connection) -> None:
        """200 response returns payload and status code."""
        scraper = SpaceXOfficialScraper()
        respx.post(SPACEX_QUERY_URL).mock(
            return_value=httpx.Response(200, json=_make_spacex_response([]))
        )

        raw_json, status = await scraper._fetch_with_retry(SPACEX_QUERY_URL)
        assert status == 200
        assert raw_json is not None
        assert json.loads(raw_json)["totalDocs"] == 0

    @respx.mock
    async def test_fetch_server_error_then_success(self, db_connection) -> None:
        """500 retries and can succeed on next attempt."""
        scraper = SpaceXOfficialScraper()
        scraper.settings.SCRAPER_MAX_RETRIES = 2

        respx.post(SPACEX_QUERY_URL).mock(
            side_effect=[
                httpx.Response(500, text="internal error"),
                httpx.Response(200, json=_make_spacex_response([])),
            ]
        )

        raw_json, status = await scraper._fetch_with_retry(SPACEX_QUERY_URL)
        assert status == 200
        assert raw_json is not None

    @respx.mock
    async def test_fetch_4xx_no_retry(self, db_connection) -> None:
        """4xx response should return immediately with no payload."""
        scraper = SpaceXOfficialScraper()
        mock = respx.post(SPACEX_QUERY_URL).mock(
            return_value=httpx.Response(400, text="bad request")
        )

        raw_json, status = await scraper._fetch_with_retry(SPACEX_QUERY_URL)
        assert raw_json is None
        assert status == 400
        assert mock.call_count == 1


class TestSpaceXOfficialScraperScrape:
    """Integration tests for scrape() with in-memory DB."""

    @respx.mock
    async def test_scrape_creates_events(self, db_connection) -> None:
        """scrape() inserts new events on first run."""
        scraper = SpaceXOfficialScraper()
        docs = [
            _launch_doc(
                launch_id="run1",
                name="Starlink A",
                date_utc="2026-06-01T10:00:00.000Z",
                upcoming=True,
                success=None,
            ),
            _launch_doc(
                launch_id="run2",
                name="Starlink B",
                date_utc="2026-06-02T10:00:00.000Z",
                upcoming=True,
                success=None,
            ),
        ]
        respx.post(SPACEX_QUERY_URL).mock(
            return_value=httpx.Response(200, json=_make_spacex_response(docs))
        )

        result = await scraper.scrape()
        assert result["total_fetched"] == 2
        assert result["new_events"] == 2
        assert result["updated_events"] == 0

    @respx.mock
    async def test_scrape_idempotent_updates_existing(self, db_connection) -> None:
        """Running scrape twice updates existing launch rows, no duplicates."""
        scraper = SpaceXOfficialScraper()
        docs = [
            _launch_doc(
                launch_id="stable1",
                name="Starlink Stable",
                date_utc="2026-07-01T10:00:00.000Z",
                upcoming=True,
                success=None,
            )
        ]
        respx.post(SPACEX_QUERY_URL).mock(
            return_value=httpx.Response(200, json=_make_spacex_response(docs))
        )

        first = await scraper.scrape()
        assert first["new_events"] == 1

        respx.post(SPACEX_QUERY_URL).mock(
            return_value=httpx.Response(200, json=_make_spacex_response(docs))
        )

        second = await scraper.scrape()
        assert second["new_events"] == 0
        assert second["updated_events"] == 1

        async with get_db() as conn, conn.execute(
            "SELECT COUNT(*) as count FROM launch_events WHERE slug = ?",
            ("spx-stable1",),
        ) as cursor:
            row = await cursor.fetchone()
            assert row["count"] == 1
