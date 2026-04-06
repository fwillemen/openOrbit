"""Tests for NotamScraper — all HTTP calls are mocked via respx."""

from __future__ import annotations

import json
import os

import httpx
import pytest
import respx

from openorbit.db import close_db, get_db, init_db
from openorbit.scrapers.notams import NotamScraper


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


def _make_faa_response(items: list[dict]) -> dict:
    """Build a minimal FAA NOTAM API envelope around a list of items."""
    return {"pageSize": len(items), "pageNum": 1, "totalCount": len(items), "items": items}


def _launch_notam(
    notam_id: str = "1/1234",
    e_text: str = "ROCKET LAUNCH CORRIDOR ACTIVE 5NM RADIUS",
    start: str = "2306151200",
    end: str = "2306151800",
) -> dict:
    return {
        "notamNumber": notam_id,
        "traditionalMessageFrom4thLine": e_text,
        "qLine": "Q) KZJX/QRTCA/IV/BO/AE/000/999/2845S04512W010",
        "startValidity": start,
        "endValidity": end,
        "location": "KZJX",
    }


FAA_URL = "https://external-api.faa.gov/notamapi/v1/notams"


class TestNotamScraperParse:
    """Unit tests for NotamScraper.parse() — no HTTP, no DB."""

    def test_parse_returns_launch_events(self) -> None:
        """parse() returns LaunchEventCreate list for matching NOTAMs."""
        scraper = NotamScraper()
        payload = _make_faa_response([_launch_notam()])
        events = scraper.parse(json.dumps(payload))
        assert len(events) == 1
        assert events[0].provider == "FAA"
        assert events[0].launch_type == "civilian"

    def test_parse_empty_items(self) -> None:
        """parse() returns empty list when items is empty."""
        scraper = NotamScraper()
        events = scraper.parse(json.dumps(_make_faa_response([])))
        assert events == []

    def test_parse_filters_non_launch(self) -> None:
        """parse() skips NOTAMs without launch keywords."""
        scraper = NotamScraper()
        non_launch = {
            "notamNumber": "9/9999",
            "traditionalMessageFrom4thLine": "VOR LIMA OUT OF SERVICE",
            "qLine": "",
            "startValidity": "2306151200",
            "endValidity": "2306151800",
            "location": "KZJX",
        }
        events = scraper.parse(json.dumps(_make_faa_response([non_launch])))
        assert events == []

    def test_parse_invalid_json_raises(self) -> None:
        """parse() raises ValueError on invalid JSON."""
        scraper = NotamScraper()
        with pytest.raises(ValueError, match="Invalid JSON"):
            scraper.parse("not valid json {{{")

    def test_parse_multiple_events(self) -> None:
        """parse() returns one event per matching NOTAM."""
        scraper = NotamScraper()
        items = [
            _launch_notam("1/0001", "ROCKET LAUNCH"),
            _launch_notam("1/0002", "SPACE LAUNCH VEHICLE"),
            {"notamNumber": "1/0003", "traditionalMessageFrom4thLine": "AIRSHOW",
             "qLine": "", "startValidity": "2306151200", "endValidity": "2306151800",
             "location": "KZJX"},
        ]
        events = scraper.parse(json.dumps(_make_faa_response(items)))
        assert len(events) == 2

    def test_parse_missile_launch_type_military(self) -> None:
        """MISSILE keyword → launch_type='military'."""
        scraper = NotamScraper()
        payload = _make_faa_response([_launch_notam(e_text="MISSILE EXERCISE ACTIVE")])
        events = scraper.parse(json.dumps(payload))
        assert len(events) == 1
        assert events[0].launch_type == "military"


class TestNotamScraperFetch:
    """Tests for _fetch_with_retry() — all HTTP mocked with respx."""

    @respx.mock
    async def test_fetch_success(self, db_connection) -> None:
        """Successful 200 response returns (json_str, 200)."""
        scraper = NotamScraper()
        respx.get(FAA_URL).mock(
            return_value=httpx.Response(200, json=_make_faa_response([]))
        )
        raw_json, status = await scraper._fetch_with_retry(FAA_URL)
        assert status == 200
        assert raw_json is not None
        assert json.loads(raw_json)["totalCount"] == 0

    @respx.mock
    async def test_fetch_server_error_retries(self, db_connection) -> None:
        """500 error retries; second attempt succeeds."""
        scraper = NotamScraper()
        scraper.settings.SCRAPER_MAX_RETRIES = 2
        respx.get(FAA_URL).mock(
            side_effect=[
                httpx.Response(500, text="Internal Server Error"),
                httpx.Response(200, json=_make_faa_response([])),
            ]
        )
        raw_json, status = await scraper._fetch_with_retry(FAA_URL)
        assert status == 200
        assert raw_json is not None

    @respx.mock
    async def test_fetch_401_no_retry(self, db_connection) -> None:
        """401 returns (None, 401) immediately without retrying."""
        scraper = NotamScraper()
        mock = respx.get(FAA_URL).mock(return_value=httpx.Response(401, text="Unauthorized"))
        raw_json, status = await scraper._fetch_with_retry(FAA_URL)
        assert status == 401
        assert raw_json is None
        assert mock.called
        assert mock.call_count == 1  # No retry

    @respx.mock
    async def test_fetch_403_no_retry(self, db_connection) -> None:
        """403 returns (None, 403) immediately without retrying."""
        scraper = NotamScraper()
        mock = respx.get(FAA_URL).mock(return_value=httpx.Response(403, text="Forbidden"))
        raw_json, status = await scraper._fetch_with_retry(FAA_URL)
        assert status == 403
        assert raw_json is None
        assert mock.call_count == 1

    @respx.mock
    async def test_fetch_connection_error_graceful(self, db_connection) -> None:
        """Network/connection errors are caught; exhausted retries return (None, None)."""
        scraper = NotamScraper()
        scraper.settings.SCRAPER_MAX_RETRIES = 1
        respx.get(FAA_URL).mock(side_effect=httpx.RequestError("Connection refused"))
        raw_json, status = await scraper._fetch_with_retry(FAA_URL)
        assert raw_json is None
        assert status is None

    @respx.mock
    async def test_fetch_timeout_graceful(self, db_connection) -> None:
        """Timeout errors are caught; exhausted retries return (None, None)."""
        scraper = NotamScraper()
        scraper.settings.SCRAPER_MAX_RETRIES = 1
        respx.get(FAA_URL).mock(side_effect=httpx.TimeoutException("Timed out"))
        raw_json, status = await scraper._fetch_with_retry(FAA_URL)
        assert raw_json is None
        assert status is None


class TestNotamScraperScrape:
    """Integration tests for scrape() — HTTP mocked, real in-memory DB."""

    @respx.mock
    async def test_scrape_creates_events(self, db_connection) -> None:
        """scrape() with 2 matching NOTAMs creates 2 new events."""
        scraper = NotamScraper()
        items = [
            _launch_notam("1/0001", "ROCKET LAUNCH AREA"),
            _launch_notam("1/0002", "SPACE LAUNCH VEHICLE DEPARTURE"),
        ]
        respx.get(FAA_URL).mock(
            return_value=httpx.Response(200, json=_make_faa_response(items))
        )
        result = await scraper.scrape()
        assert result["total_fetched"] == 2
        assert result["new_events"] == 2
        assert result["updated_events"] == 0

    @respx.mock
    async def test_scrape_empty_response(self, db_connection) -> None:
        """scrape() with empty items list returns zeros without error."""
        scraper = NotamScraper()
        respx.get(FAA_URL).mock(
            return_value=httpx.Response(200, json=_make_faa_response([]))
        )
        result = await scraper.scrape()
        assert result["total_fetched"] == 0
        assert result["new_events"] == 0
        assert result["updated_events"] == 0

    @respx.mock
    async def test_scrape_http_500_returns_zeros(self, db_connection) -> None:
        """scrape() on persistent 500 error logs warning and returns zeros."""
        scraper = NotamScraper()
        scraper.settings.SCRAPER_MAX_RETRIES = 1
        respx.get(FAA_URL).mock(return_value=httpx.Response(500, text="Error"))
        result = await scraper.scrape()
        assert result["total_fetched"] == 0
        assert result["new_events"] == 0

    @respx.mock
    async def test_scrape_connection_error_returns_zeros(self, db_connection) -> None:
        """scrape() on connection error gracefully returns zeros."""
        scraper = NotamScraper()
        scraper.settings.SCRAPER_MAX_RETRIES = 1
        respx.get(FAA_URL).mock(side_effect=httpx.RequestError("Offline"))
        result = await scraper.scrape()
        assert result["total_fetched"] == 0
        assert result["new_events"] == 0
        assert result["updated_events"] == 0

    @respx.mock
    async def test_scrape_idempotent(self, db_connection) -> None:
        """Running scrape() twice on same data updates rather than duplicates."""
        scraper = NotamScraper()
        items = [_launch_notam("1/1111", "ROCKET LAUNCH")]
        respx.get(FAA_URL).mock(
            return_value=httpx.Response(200, json=_make_faa_response(items))
        )
        result1 = await scraper.scrape()
        assert result1["new_events"] == 1

        respx.get(FAA_URL).mock(
            return_value=httpx.Response(200, json=_make_faa_response(items))
        )
        result2 = await scraper.scrape()
        assert result2["updated_events"] == 1
        assert result2["new_events"] == 0

        # Still only 1 event in DB (no duplicates)
        async with (
            get_db() as conn,
            conn.execute("SELECT COUNT(*) as count FROM launch_events") as cursor,
        ):
            row = await cursor.fetchone()
            assert row["count"] == 1

    @respx.mock
    async def test_scrape_registers_source(self, db_connection) -> None:
        """scrape() registers 'FAA NOTAM Database' as an OSINT source."""
        scraper = NotamScraper()
        respx.get(FAA_URL).mock(
            return_value=httpx.Response(200, json=_make_faa_response([]))
        )
        await scraper.scrape()

        async with (
            get_db() as conn,
            conn.execute(
                "SELECT name FROM osint_sources WHERE name = 'FAA NOTAM Database'"
            ) as cursor,
        ):
            row = await cursor.fetchone()
            assert row is not None
            assert row["name"] == "FAA NOTAM Database"
