"""Tests for BlueskyScraper."""

from __future__ import annotations

import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from openorbit.db import close_db, get_db, init_db
from openorbit.scrapers.bluesky import BlueskyScraper, _make_slug

# ---------------------------------------------------------------------------
# Fixtures / sample payloads
# ---------------------------------------------------------------------------

SAMPLE_POST_1: dict = {
    "uri": "at://did:plc:abc123/app.bsky.feed.post/1",
    "record": {
        "text": "SpaceX Falcon 9 rocket launch successful! #spacex #launch",
        "createdAt": "2024-01-15T18:30:00.000Z",
    },
    "author": {"handle": "spacenerd.bsky.social"},
    "indexedAt": "2024-01-15T18:31:00.000Z",
}

SAMPLE_POST_2: dict = {
    "uri": "at://did:plc:def456/app.bsky.feed.post/2",
    "record": {
        "text": "Watching the rocket liftoff from the cape! Amazing 🚀",
        "createdAt": "2024-01-16T12:00:00.000Z",
    },
    "author": {"handle": "rocketfan.bsky.social"},
    "indexedAt": "2024-01-16T12:01:00.000Z",
}

SAMPLE_POST_IRRELEVANT: dict = {
    "uri": "at://did:plc:ghi789/app.bsky.feed.post/3",
    "record": {
        "text": "Just had a great lunch today!",
        "createdAt": "2024-01-16T13:00:00.000Z",
    },
    "author": {"handle": "foodblogger.bsky.social"},
    "indexedAt": "2024-01-16T13:01:00.000Z",
}

SAMPLE_SEARCH_RESPONSE: dict = {
    "posts": [SAMPLE_POST_1, SAMPLE_POST_2],
}

SAMPLE_FEED_RESPONSE: dict = {
    "feed": [
        {"post": SAMPLE_POST_1},
        {"post": SAMPLE_POST_2},
    ]
}

SCRAPER = BlueskyScraper()


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
        assert BlueskyScraper.source_tier == 3

    def test_evidence_type_is_media(self) -> None:
        assert BlueskyScraper.evidence_type == "media"

    def test_source_name(self) -> None:
        assert BlueskyScraper.source_name == "bluesky"

    def test_source_url(self) -> None:
        assert "bsky.app" in BlueskyScraper.source_url

    def test_search_terms_non_empty(self) -> None:
        assert len(BlueskyScraper.SEARCH_TERMS) > 0

    def test_tracked_accounts_non_empty(self) -> None:
        assert len(BlueskyScraper.TRACKED_ACCOUNTS) > 0

    def test_rate_limit_seconds(self) -> None:
        assert BlueskyScraper.RATE_LIMIT_SECONDS == 3.0


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

    def test_matches_satellite(self) -> None:
        assert SCRAPER._is_launch_relevant("New satellite deployed") is True

    def test_matches_spacecraft(self) -> None:
        assert SCRAPER._is_launch_relevant("Spacecraft reached orbit") is True

    def test_case_insensitive(self) -> None:
        assert SCRAPER._is_launch_relevant("ROCKET LAUNCH") is True

    def test_no_match(self) -> None:
        assert SCRAPER._is_launch_relevant("Just had a great lunch today!") is False

    def test_empty_string(self) -> None:
        assert SCRAPER._is_launch_relevant("") is False


# ---------------------------------------------------------------------------
# parse() unit tests
# ---------------------------------------------------------------------------


class TestParseSearchResponse:
    """parse() handles search endpoint format {"posts": [...]}."""

    @pytest.mark.asyncio
    async def test_returns_correct_count(self) -> None:
        events = await SCRAPER.parse(json.dumps(SAMPLE_SEARCH_RESPONSE))
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_slug_format(self) -> None:
        events = await SCRAPER.parse(json.dumps(SAMPLE_SEARCH_RESPONSE))
        assert events[0].slug is not None
        assert events[0].slug.startswith("bluesky-")

    @pytest.mark.asyncio
    async def test_claim_lifecycle_is_rumor(self) -> None:
        events = await SCRAPER.parse(json.dumps(SAMPLE_SEARCH_RESPONSE))
        for event in events:
            assert event.claim_lifecycle == "rumor"

    @pytest.mark.asyncio
    async def test_event_kind_is_inferred(self) -> None:
        events = await SCRAPER.parse(json.dumps(SAMPLE_SEARCH_RESPONSE))
        for event in events:
            assert event.event_kind == "inferred"

    @pytest.mark.asyncio
    async def test_provider_is_author_handle(self) -> None:
        events = await SCRAPER.parse(json.dumps(SAMPLE_SEARCH_RESPONSE))
        assert events[0].provider == "spacenerd.bsky.social"

    @pytest.mark.asyncio
    async def test_name_is_post_text(self) -> None:
        events = await SCRAPER.parse(json.dumps(SAMPLE_SEARCH_RESPONSE))
        assert "rocket" in events[0].name.lower()

    @pytest.mark.asyncio
    async def test_launch_date_parsed(self) -> None:
        events = await SCRAPER.parse(json.dumps(SAMPLE_SEARCH_RESPONSE))
        assert isinstance(events[0].launch_date, datetime)
        assert events[0].launch_date.year == 2024

    @pytest.mark.asyncio
    async def test_precision_is_day(self) -> None:
        events = await SCRAPER.parse(json.dumps(SAMPLE_SEARCH_RESPONSE))
        for event in events:
            assert event.launch_date_precision == "day"

    @pytest.mark.asyncio
    async def test_status_is_scheduled(self) -> None:
        events = await SCRAPER.parse(json.dumps(SAMPLE_SEARCH_RESPONSE))
        for event in events:
            assert event.status == "scheduled"

    @pytest.mark.asyncio
    async def test_launch_type_is_unknown(self) -> None:
        events = await SCRAPER.parse(json.dumps(SAMPLE_SEARCH_RESPONSE))
        for event in events:
            assert event.launch_type == "unknown"


class TestParseAuthorFeed:
    """parse() handles bare list format (from author feed flattening)."""

    @pytest.mark.asyncio
    async def test_bare_list_parsed(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_POST_1, SAMPLE_POST_2]))
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_missing_uri_skipped(self) -> None:
        bad = {
            "record": {"text": "launch today", "createdAt": "2024-01-15T10:00:00Z"},
            "author": {"handle": "x"},
        }
        events = await SCRAPER.parse(json.dumps([bad]))
        assert events == []

    @pytest.mark.asyncio
    async def test_missing_text_skipped(self) -> None:
        bad = {
            "uri": "at://x/y/z",
            "record": {"createdAt": "2024-01-15T10:00:00Z"},
            "author": {"handle": "x"},
        }
        events = await SCRAPER.parse(json.dumps([bad]))
        assert events == []

    @pytest.mark.asyncio
    async def test_invalid_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid JSON"):
            await SCRAPER.parse("not-json")


# ---------------------------------------------------------------------------
# Dedup test
# ---------------------------------------------------------------------------


class TestDedupByUri:
    """Same URI must not be processed twice."""

    @pytest.mark.asyncio
    async def test_same_uri_deduped(self) -> None:
        # Two copies of the same post
        posts = [SAMPLE_POST_1, SAMPLE_POST_1]
        events = await SCRAPER.parse(json.dumps(posts))
        # Both produce the same slug; parse doesn't deduplicate — scrape() does
        slugs = [e.slug for e in events]
        assert len(slugs) == 2
        assert slugs[0] == slugs[1]

    def test_make_slug_deterministic(self) -> None:
        slug1 = _make_slug("at://did:plc:abc/post/1")
        slug2 = _make_slug("at://did:plc:abc/post/1")
        assert slug1 == slug2

    def test_make_slug_different_uris(self) -> None:
        slug1 = _make_slug("at://did:plc:abc/post/1")
        slug2 = _make_slug("at://did:plc:abc/post/2")
        assert slug1 != slug2


# ---------------------------------------------------------------------------
# Integration tests — DB insert
# ---------------------------------------------------------------------------


_MOD = "openorbit.scrapers.bluesky"


def _make_db_mock(db_connection):  # type: ignore[no-untyped-def]
    """Return a mock async context manager that yields db_connection."""
    from unittest.mock import MagicMock

    mock_get_db = MagicMock()
    mock_get_db.return_value.__aenter__ = AsyncMock(return_value=db_connection)
    mock_get_db.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_get_db


class TestIntegrationDbInsert:
    """Scrape() inserts events with mocked HTTP and real in-memory DB."""

    @respx.mock
    async def test_scrape_inserts_events(self, db_connection) -> None:
        """scrape() inserts launch-relevant posts from search + feed."""
        relevant_posts = [SAMPLE_POST_1, SAMPLE_POST_2]
        search_response = {"posts": relevant_posts}
        feed_response = {"feed": [{"post": p} for p in relevant_posts]}

        respx.get(BlueskyScraper.SEARCH_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        respx.get(BlueskyScraper.FEED_URL).mock(
            return_value=httpx.Response(200, json=feed_response)
        )

        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(f"{_MOD}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            scraper = BlueskyScraper()
            result = await scraper.scrape()

        assert result["total_fetched"] >= 1
        assert result["new_events"] >= 1

        async with db_connection.execute("SELECT COUNT(*) FROM launch_events") as cur:
            row = await cur.fetchone()
            assert row[0] >= 1

    @respx.mock
    async def test_scrape_dedup_second_run(self, db_connection) -> None:
        """Second scrape() with same posts must not create duplicate events."""
        relevant_posts = [SAMPLE_POST_1]
        search_response = {"posts": relevant_posts}
        feed_response = {"feed": []}

        respx.get(BlueskyScraper.SEARCH_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        respx.get(BlueskyScraper.FEED_URL).mock(
            return_value=httpx.Response(200, json=feed_response)
        )

        mock_get_db = _make_db_mock(db_connection)

        with (
            patch(f"{_MOD}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            scraper = BlueskyScraper()
            result1 = await scraper.scrape()

        # Reset mock for second scrape
        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=db_connection)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(f"{_MOD}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            scraper2 = BlueskyScraper()
            result2 = await scraper2.scrape()

        assert result1["new_events"] >= 1
        assert result2["new_events"] == 0

        async with db_connection.execute("SELECT COUNT(*) FROM launch_events") as cur:
            row = await cur.fetchone()
            assert row[0] == result1["new_events"]

    @respx.mock
    async def test_irrelevant_posts_not_inserted(self, db_connection) -> None:
        """Posts without launch keywords are filtered out."""
        search_response = {"posts": [SAMPLE_POST_IRRELEVANT]}
        feed_response = {"feed": []}

        respx.get(BlueskyScraper.SEARCH_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        respx.get(BlueskyScraper.FEED_URL).mock(
            return_value=httpx.Response(200, json=feed_response)
        )

        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(f"{_MOD}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            scraper = BlueskyScraper()
            result = await scraper.scrape()

        assert result["total_fetched"] == 0
        assert result["new_events"] == 0
