"""Tests for CelesTrakScraper — all HTTP calls mocked via respx."""

from __future__ import annotations

import json
import os

import httpx
import pytest
import respx

from openorbit.db import close_db, get_db, init_db
from openorbit.scrapers.celestrak import CelesTrakScraper


@pytest.fixture
async def db_connection():
    """Initialize in-memory database for scraper tests."""
    from openorbit import config

    config._settings = None
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    await init_db()
    async with get_db() as conn:
        yield conn

    await close_db()
    config._settings = None


CELESTRAK_URL = (
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=json"
)


def _celestrak_item(
    object_id: str,
    object_name: str,
    launch_date: str,
    owner: str = "US",
    site: str = "AFETR",
) -> dict:
    return {
        "OBJECT_ID": object_id,
        "OBJECT_NAME": object_name,
        "LAUNCH_DATE": launch_date,
        "OWNER": owner,
        "SITE": site,
    }


class TestCelesTrakScraperParse:
    """Unit tests for parse()."""

    def test_parse_aggregates_multiple_payloads_per_launch(self) -> None:
        """Multiple payload objects under same launch key collapse to one event."""
        scraper = CelesTrakScraper()
        payload = [
            _celestrak_item("2026-001A", "PAYLOAD-1", "2026-01-15"),
            _celestrak_item("2026-001B", "PAYLOAD-2", "2026-01-15"),
            _celestrak_item("2026-002A", "PAYLOAD-3", "2026-01-20"),
        ]

        events = scraper.parse(json.dumps(payload))
        assert len(events) == 2
        assert any(event.slug == "celestrak-2026-001" for event in events)
        assert any(event.slug == "celestrak-2026-002" for event in events)
        first = next(event for event in events if event.slug == "celestrak-2026-001")
        assert "2 payloads" in first.name

    def test_parse_invalid_json_raises(self) -> None:
        """Invalid JSON should raise ValueError."""
        scraper = CelesTrakScraper()
        with pytest.raises(ValueError, match="Invalid JSON"):
            scraper.parse("not valid json {{{")

    def test_parse_skips_items_without_launch_date(self) -> None:
        """Rows missing LAUNCH_DATE are ignored."""
        scraper = CelesTrakScraper()
        payload = [
            _celestrak_item("2026-005A", "VALID", "2026-01-25"),
            {
                "OBJECT_ID": "2026-005B",
                "OBJECT_NAME": "INVALID",
                "OWNER": "US",
                "SITE": "AFETR",
            },
        ]
        events = scraper.parse(json.dumps(payload))
        assert len(events) == 1
        assert events[0].slug == "celestrak-2026-005"

    def test_parse_uses_epoch_when_launch_date_missing(self) -> None:
        """Parser falls back to EPOCH when LAUNCH_DATE is not present."""
        scraper = CelesTrakScraper()
        payload = [
            {
                "OBJECT_ID": "2026-020A",
                "OBJECT_NAME": "EPOCH-ONLY",
                "EPOCH": "2026-03-22T14:44:56.613696",
            }
        ]
        events = scraper.parse(json.dumps(payload))
        assert len(events) == 1
        assert events[0].slug == "celestrak-2026-020"


class TestCelesTrakScraperFetch:
    """Tests for _fetch_with_retry()."""

    @respx.mock
    async def test_fetch_success(self, db_connection) -> None:
        """200 response returns JSON string and status."""
        scraper = CelesTrakScraper()
        respx.get(CELESTRAK_URL).mock(return_value=httpx.Response(200, json=[]))

        raw_json, status = await scraper._fetch_with_retry(CELESTRAK_URL)
        assert status == 200
        assert raw_json is not None
        assert json.loads(raw_json) == []

    @respx.mock
    async def test_fetch_server_error_then_success(self, db_connection) -> None:
        """500 retries and succeeds on next response."""
        scraper = CelesTrakScraper()
        scraper.settings.SCRAPER_MAX_RETRIES = 2
        respx.get(CELESTRAK_URL).mock(
            side_effect=[
                httpx.Response(500, text="server error"),
                httpx.Response(200, json=[]),
            ]
        )

        raw_json, status = await scraper._fetch_with_retry(CELESTRAK_URL)
        assert status == 200
        assert raw_json is not None


class TestCelesTrakScraperScrape:
    """Integration tests for scrape() with in-memory DB."""

    @respx.mock
    async def test_scrape_creates_events(self, db_connection) -> None:
        """First scrape inserts new launch events."""
        scraper = CelesTrakScraper()
        payload = [
            _celestrak_item("2026-010A", "OBJ-A", "2026-02-10"),
            _celestrak_item("2026-010B", "OBJ-B", "2026-02-10"),
            _celestrak_item("2026-011A", "OBJ-C", "2026-02-11"),
        ]
        respx.get(CELESTRAK_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await scraper.scrape()
        assert result["total_fetched"] == 2
        assert result["new_events"] == 2
        assert result["updated_events"] == 0

    @respx.mock
    async def test_scrape_idempotent(self, db_connection) -> None:
        """Repeated scrape updates existing events without duplicates."""
        scraper = CelesTrakScraper()
        payload = [_celestrak_item("2026-015A", "OBJ-STABLE", "2026-02-15")]
        respx.get(CELESTRAK_URL).mock(return_value=httpx.Response(200, json=payload))

        first = await scraper.scrape()
        assert first["new_events"] == 1

        respx.get(CELESTRAK_URL).mock(return_value=httpx.Response(200, json=payload))
        second = await scraper.scrape()
        assert second["new_events"] == 0
        assert second["updated_events"] == 1

        async with get_db() as conn, conn.execute(
            "SELECT COUNT(*) as count FROM launch_events WHERE slug = ?",
            ("celestrak-2026-015",),
        ) as cursor:
            row = await cursor.fetchone()
            assert row["count"] == 1
