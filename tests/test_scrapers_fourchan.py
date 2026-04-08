"""Tests for FourChanScraper."""

from __future__ import annotations

import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from openorbit.db import close_db, get_db, init_db
from openorbit.scrapers.fourchan import (
    FourChanScraper,
    _build_image_url,
    _make_slug,
    _strip_html,
)

# ---------------------------------------------------------------------------
# Fixtures / sample payloads
# ---------------------------------------------------------------------------

SAMPLE_THREAD_1: dict = {
    "no": 12345678,
    "sub": "SpaceX Falcon 9 Launch Thread",
    "com": '<a href="#p12345677" class="quotelink">&gt;&gt;12345677</a><br>Launch is GO for tonight! Rocket is on the pad. <br><span class="quote">&gt;mfw liftoff</span>',
    "time": 1705340400,
    "tim": 1705340399000,
    "ext": ".jpg",
    "_board": "sci",
}

SAMPLE_THREAD_2: dict = {
    "no": 12345679,
    "sub": "NASA Artemis mission orbit update",
    "com": "Latest update on the Artemis spacecraft mission to lunar orbit.",
    "time": 1705426800,
    "_board": "sci",
}

SAMPLE_THREAD_IRRELEVANT: dict = {
    "no": 12345680,
    "sub": "Chemistry homework thread",
    "com": "Help me with organic chemistry please",
    "time": 1705513200,
    "_board": "sci",
}

SAMPLE_CATALOG_RESPONSE: list = [
    {
        "page": 1,
        "threads": [SAMPLE_THREAD_1, SAMPLE_THREAD_2],
    },
]

SCRAPER = FourChanScraper()


@pytest.fixture
async def db_connection():
    """Provide a fresh in-memory database for each test."""
    from openorbit import config

    config._settings = None
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    await init_db()
    async with get_db() as conn:
        yield conn

    await close_db()
    config._settings = None


# ---------------------------------------------------------------------------
# Class-variable tests
# ---------------------------------------------------------------------------


class TestClassVars:
    def test_source_tier_is_3(self) -> None:
        assert FourChanScraper.source_tier == 3

    def test_evidence_type_is_media(self) -> None:
        assert FourChanScraper.evidence_type == "media"

    def test_source_name(self) -> None:
        assert FourChanScraper.source_name == "4chan"

    def test_source_url(self) -> None:
        assert "4cdn.org" in FourChanScraper.source_url

    def test_boards_non_empty(self) -> None:
        assert len(FourChanScraper.BOARDS) > 0

    def test_boards_contain_sci(self) -> None:
        assert "sci" in FourChanScraper.BOARDS

    def test_refresh_interval(self) -> None:
        assert FourChanScraper.refresh_interval_hours == 2


# ---------------------------------------------------------------------------
# _is_launch_relevant tests
# ---------------------------------------------------------------------------


class TestIsLaunchRelevant:
    def test_matches_launch(self) -> None:
        assert SCRAPER._is_launch_relevant("rocket launch today") is True

    def test_matches_liftoff(self) -> None:
        assert SCRAPER._is_launch_relevant("beautiful liftoff") is True

    def test_matches_rocket(self) -> None:
        assert SCRAPER._is_launch_relevant("Watching the rocket") is True

    def test_matches_spacex(self) -> None:
        assert SCRAPER._is_launch_relevant("SpaceX launch update") is True

    def test_matches_nasa(self) -> None:
        assert SCRAPER._is_launch_relevant("NASA mission update") is True

    def test_matches_starship(self) -> None:
        assert SCRAPER._is_launch_relevant("Starship test flight") is True

    def test_case_insensitive(self) -> None:
        assert SCRAPER._is_launch_relevant("ROCKET LAUNCH") is True

    def test_no_match(self) -> None:
        assert SCRAPER._is_launch_relevant("chemistry homework help") is False

    def test_empty_string(self) -> None:
        assert SCRAPER._is_launch_relevant("") is False


# ---------------------------------------------------------------------------
# _strip_html tests
# ---------------------------------------------------------------------------


class TestStripHtml:
    def test_strips_br_tags(self) -> None:
        result = _strip_html("line one<br>line two")
        assert "<br>" not in result
        assert "line one" in result

    def test_strips_anchor_tags(self) -> None:
        result = _strip_html('<a href="#p123">&gt;&gt;123</a> text')
        assert "<a" not in result
        assert "text" in result

    def test_decodes_entities(self) -> None:
        result = _strip_html("A &amp; B &lt; C &gt; D")
        assert result == "A & B < C > D"

    def test_strips_span_tags(self) -> None:
        result = _strip_html('<span class="quote">&gt;greentext</span>')
        assert "<span" not in result

    def test_empty_string(self) -> None:
        assert _strip_html("") == ""


# ---------------------------------------------------------------------------
# _build_image_url tests
# ---------------------------------------------------------------------------


class TestBuildImageUrl:
    def test_correct_format(self) -> None:
        url = _build_image_url("sci", 1705340399000, ".jpg")
        assert url == "https://i.4cdn.org/sci/1705340399000.jpg"

    def test_png_extension(self) -> None:
        url = _build_image_url("sci", 12345, ".png")
        assert url.endswith(".png")
        assert "sci" in url


# ---------------------------------------------------------------------------
# _make_slug tests
# ---------------------------------------------------------------------------


class TestMakeSlug:
    def test_deterministic(self) -> None:
        slug1 = _make_slug("sci", 12345)
        slug2 = _make_slug("sci", 12345)
        assert slug1 == slug2

    def test_starts_with_4chan(self) -> None:
        slug = _make_slug("sci", 12345)
        assert slug.startswith("4chan-")

    def test_different_threads(self) -> None:
        slug1 = _make_slug("sci", 12345)
        slug2 = _make_slug("sci", 67890)
        assert slug1 != slug2

    def test_different_boards(self) -> None:
        slug1 = _make_slug("sci", 12345)
        slug2 = _make_slug("pol", 12345)
        assert slug1 != slug2


# ---------------------------------------------------------------------------
# parse() unit tests
# ---------------------------------------------------------------------------


class TestParse:
    @pytest.mark.asyncio
    async def test_returns_correct_count(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_THREAD_1, SAMPLE_THREAD_2]))
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_slug_format(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_THREAD_1]))
        assert events[0].slug is not None
        assert events[0].slug.startswith("4chan-")

    @pytest.mark.asyncio
    async def test_claim_lifecycle_is_rumor(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_THREAD_1, SAMPLE_THREAD_2]))
        for event in events:
            assert event.claim_lifecycle == "rumor"

    @pytest.mark.asyncio
    async def test_event_kind_is_inferred(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_THREAD_1, SAMPLE_THREAD_2]))
        for event in events:
            assert event.event_kind == "inferred"

    @pytest.mark.asyncio
    async def test_provider_includes_board(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_THREAD_1]))
        assert "sci" in events[0].provider

    @pytest.mark.asyncio
    async def test_name_from_subject(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_THREAD_1]))
        assert "Falcon 9" in events[0].name

    @pytest.mark.asyncio
    async def test_launch_date_parsed(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_THREAD_1]))
        assert isinstance(events[0].launch_date, datetime)

    @pytest.mark.asyncio
    async def test_precision_is_day(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_THREAD_1]))
        assert events[0].launch_date_precision == "day"

    @pytest.mark.asyncio
    async def test_status_is_scheduled(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_THREAD_1]))
        assert events[0].status == "scheduled"

    @pytest.mark.asyncio
    async def test_image_url_captured(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_THREAD_1]))
        assert len(events[0].image_urls) == 1
        assert "4cdn.org" in events[0].image_urls[0]
        assert ".jpg" in events[0].image_urls[0]

    @pytest.mark.asyncio
    async def test_no_image_when_missing(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_THREAD_2]))
        assert events[0].image_urls == []

    @pytest.mark.asyncio
    async def test_invalid_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid JSON"):
            await SCRAPER.parse("not-json")

    @pytest.mark.asyncio
    async def test_missing_thread_no_skipped(self) -> None:
        bad = {"sub": "test thread", "com": "rocket launch", "time": 0, "_board": "sci"}
        events = await SCRAPER.parse(json.dumps([bad]))
        assert events == []

    @pytest.mark.asyncio
    async def test_fallback_to_comment_when_no_subject(self) -> None:
        thread = {
            "no": 99999,
            "com": "Watching the rocket launch live!",
            "time": 1705340400,
            "_board": "sci",
        }
        events = await SCRAPER.parse(json.dumps([thread]))
        assert len(events) == 1
        assert "rocket launch" in events[0].name.lower()


# ---------------------------------------------------------------------------
# Integration tests — DB insert
# ---------------------------------------------------------------------------


_MOD = "openorbit.scrapers.fourchan"


def _make_db_mock(db_connection):  # type: ignore[no-untyped-def]
    """Return a mock async context manager that yields db_connection."""
    mock_get_db = MagicMock()
    mock_get_db.return_value.__aenter__ = AsyncMock(return_value=db_connection)
    mock_get_db.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_get_db


class TestIntegrationDbInsert:
    """Scrape() inserts events with mocked HTTP and real in-memory DB."""

    @respx.mock
    async def test_scrape_inserts_events(self, db_connection) -> None:
        """scrape() inserts launch-relevant threads from boards."""
        for board in FourChanScraper.BOARDS:
            respx.get(f"https://a.4cdn.org/{board}/catalog.json").mock(
                return_value=httpx.Response(200, json=SAMPLE_CATALOG_RESPONSE)
            )

        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            scraper = FourChanScraper()
            result = await scraper.scrape()

        assert result["total_fetched"] >= 1
        assert result["new_events"] >= 1

        async with db_connection.execute("SELECT COUNT(*) FROM launch_events") as cur:
            row = await cur.fetchone()
            assert row[0] >= 1

    @respx.mock
    async def test_scrape_dedup_second_run(self, db_connection) -> None:
        """Second scrape() with same threads must not create duplicate events."""
        catalog = [{"page": 1, "threads": [SAMPLE_THREAD_1]}]
        for board in FourChanScraper.BOARDS:
            respx.get(f"https://a.4cdn.org/{board}/catalog.json").mock(
                return_value=httpx.Response(200, json=catalog)
            )

        mock_get_db = _make_db_mock(db_connection)

        with (
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result1 = await FourChanScraper().scrape()

        # Reset for second run
        respx.mock.reset()
        for board in FourChanScraper.BOARDS:
            respx.get(f"https://a.4cdn.org/{board}/catalog.json").mock(
                return_value=httpx.Response(200, json=catalog)
            )

        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=db_connection)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result2 = await FourChanScraper().scrape()

        assert result1["new_events"] >= 1
        assert result2["new_events"] == 0

    @respx.mock
    async def test_irrelevant_threads_not_inserted(self, db_connection) -> None:
        """Threads without launch keywords are filtered out."""
        catalog = [{"page": 1, "threads": [SAMPLE_THREAD_IRRELEVANT]}]
        for board in FourChanScraper.BOARDS:
            respx.get(f"https://a.4cdn.org/{board}/catalog.json").mock(
                return_value=httpx.Response(200, json=catalog)
            )

        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result = await FourChanScraper().scrape()

        assert result["total_fetched"] == 0
        assert result["new_events"] == 0

    @respx.mock
    async def test_image_urls_persisted(self, db_connection) -> None:
        """Image URLs from OP should be persisted in the database."""
        catalog = [{"page": 1, "threads": [SAMPLE_THREAD_1]}]
        for board in FourChanScraper.BOARDS:
            respx.get(f"https://a.4cdn.org/{board}/catalog.json").mock(
                return_value=httpx.Response(200, json=catalog)
            )

        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            await FourChanScraper().scrape()

        async with db_connection.execute(
            "SELECT image_urls FROM launch_events LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
            assert row is not None
            image_urls = json.loads(row["image_urls"] or "[]")
            assert len(image_urls) >= 1
            assert "4cdn.org" in image_urls[0]
