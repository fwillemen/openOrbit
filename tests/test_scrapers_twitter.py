"""Tests for TwitterScraper."""

from __future__ import annotations

import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from openorbit.db import close_db, get_db, init_db
from openorbit.scrapers.twitter import (
    TwitterScraper,
    _make_slug,
    _strip_urls,
)

# ---------------------------------------------------------------------------
# Fixtures / sample payloads — synthetic Russia & China launch tweets
# ---------------------------------------------------------------------------

SAMPLE_TWEET_RUSSIA: dict = {
    "id": "1800000000000000001",
    "text": "Roscosmos Soyuz-2.1b rocket launch from Vostochny cosmodrome carrying Glonass-K2 satellite to orbit! 🚀 https://t.co/abc123",
    "created_at": "2026-04-07T10:30:00.000Z",
    "author_id": "111111",
    "_username": "RoscosmosNews",
    "attachments": {"media_keys": ["media_001"]},
    "_image_urls": ["https://pbs.twimg.com/media/soyuz_launch.jpg"],
}

SAMPLE_TWEET_CHINA: dict = {
    "id": "1800000000000000002",
    "text": "CASC Long March 5B rocket launch from Wenchang — carrying Tiangong space station module to orbit successfully! #ChinaSpace https://t.co/def456",
    "created_at": "2026-04-06T14:00:00.000Z",
    "author_id": "222222",
    "_username": "CNSAWatcher",
    "attachments": {"media_keys": ["media_002"]},
    "_image_urls": ["https://pbs.twimg.com/media/longmarch5b.jpg"],
}

SAMPLE_TWEET_CHINA_2: dict = {
    "id": "1800000000000000003",
    "text": "Breaking: China's Kuaizhou-1A rocket liftoff from Jiuquan Satellite Launch Center — deploying remote sensing satellite constellation",
    "created_at": "2026-04-05T08:15:00.000Z",
    "author_id": "333333",
    "_username": "SpaceTracker",
    "_image_urls": [],
}

SAMPLE_TWEET_RUSSIA_2: dict = {
    "id": "1800000000000000004",
    "text": "Angara-A5 heavy-lift rocket mission from Plesetsk cosmodrome — Russia's newest orbital launch vehicle reaches orbit",
    "created_at": "2026-04-04T06:45:00.000Z",
    "author_id": "444444",
    "_username": "RussianSpaceWeb",
    "_image_urls": ["https://pbs.twimg.com/media/angara_a5.jpg"],
}

SAMPLE_TWEET_IRRELEVANT: dict = {
    "id": "1800000000000000099",
    "text": "Had a great breakfast this morning. Coffee and pancakes!",
    "created_at": "2026-04-07T07:00:00.000Z",
    "author_id": "999999",
    "_username": "foodie42",
    "_image_urls": [],
}

# Twitter API v2 search response format with Russia/China data
SAMPLE_SEARCH_RESPONSE: dict = {
    "data": [SAMPLE_TWEET_RUSSIA, SAMPLE_TWEET_CHINA],
    "includes": {
        "users": [
            {"id": "111111", "username": "RoscosmosNews"},
            {"id": "222222", "username": "CNSAWatcher"},
        ],
        "media": [
            {
                "media_key": "media_001",
                "type": "photo",
                "url": "https://pbs.twimg.com/media/soyuz_launch.jpg",
            },
            {
                "media_key": "media_002",
                "type": "photo",
                "url": "https://pbs.twimg.com/media/longmarch5b.jpg",
            },
        ],
    },
    "meta": {
        "newest_id": "1800000000000000002",
        "oldest_id": "1800000000000000001",
        "result_count": 2,
    },
}

SCRAPER = TwitterScraper()


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
        assert TwitterScraper.source_tier == 3

    def test_evidence_type_is_media(self) -> None:
        assert TwitterScraper.evidence_type == "media"

    def test_source_name(self) -> None:
        assert TwitterScraper.source_name == "twitter"

    def test_source_url(self) -> None:
        assert "api.twitter.com" in TwitterScraper.source_url

    def test_search_terms_non_empty(self) -> None:
        assert len(TwitterScraper.SEARCH_TERMS) > 0

    def test_tracked_accounts_non_empty(self) -> None:
        assert len(TwitterScraper.TRACKED_ACCOUNTS) > 0

    def test_tracked_accounts_contain_space_accounts(self) -> None:
        accounts = set(TwitterScraper.TRACKED_ACCOUNTS)
        assert "NASA" in accounts
        assert "SpaceX" in accounts

    def test_refresh_interval(self) -> None:
        assert TwitterScraper.refresh_interval_hours == 2

    def test_rate_limit_seconds_set(self) -> None:
        assert TwitterScraper.RATE_LIMIT_SECONDS >= 1.0

    def test_max_results_per_query(self) -> None:
        assert TwitterScraper.MAX_RESULTS_PER_QUERY == 10


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

    def test_matches_mission(self) -> None:
        assert SCRAPER._is_launch_relevant("Mars mission update") is True

    def test_matches_orbit(self) -> None:
        assert SCRAPER._is_launch_relevant("Entered low Earth orbit") is True

    def test_case_insensitive(self) -> None:
        assert SCRAPER._is_launch_relevant("ROCKET LAUNCH") is True

    def test_no_match(self) -> None:
        assert SCRAPER._is_launch_relevant("Just a chemistry paper") is False

    def test_empty_string(self) -> None:
        assert SCRAPER._is_launch_relevant("") is False

    def test_russia_soyuz_launch(self) -> None:
        assert (
            SCRAPER._is_launch_relevant(
                "Soyuz-2.1b rocket launch from Vostochny cosmodrome"
            )
            is True
        )

    def test_china_long_march(self) -> None:
        assert (
            SCRAPER._is_launch_relevant("Long March 5B rocket launch from Wenchang")
            is True
        )


# ---------------------------------------------------------------------------
# _strip_urls tests
# ---------------------------------------------------------------------------


class TestStripUrls:
    def test_strips_tco_links(self) -> None:
        result = _strip_urls("Big launch today! https://t.co/abc123")
        assert "https://t.co" not in result
        assert "Big launch today!" in result

    def test_strips_multiple_links(self) -> None:
        result = _strip_urls("A https://t.co/x B https://t.co/y C")
        assert "https://t.co" not in result
        assert "A" in result
        assert "C" in result

    def test_no_links_unchanged(self) -> None:
        assert _strip_urls("No links here") == "No links here"

    def test_empty_string(self) -> None:
        assert _strip_urls("") == ""


# ---------------------------------------------------------------------------
# _make_slug tests
# ---------------------------------------------------------------------------


class TestMakeSlug:
    def test_deterministic(self) -> None:
        slug1 = _make_slug("1800000000000000001")
        slug2 = _make_slug("1800000000000000001")
        assert slug1 == slug2

    def test_different_ids(self) -> None:
        slug1 = _make_slug("1800000000000000001")
        slug2 = _make_slug("1800000000000000002")
        assert slug1 != slug2

    def test_prefix(self) -> None:
        slug = _make_slug("1800000000000000001")
        assert slug.startswith("twitter-")

    def test_length(self) -> None:
        slug = _make_slug("1800000000000000001")
        # "twitter-" (8) + 12 hex chars = 20
        assert len(slug) == 20


# ---------------------------------------------------------------------------
# parse() unit tests — Russia & China launch data
# ---------------------------------------------------------------------------


class TestParse:
    @pytest.mark.asyncio
    async def test_returns_correct_count(self) -> None:
        events = await SCRAPER.parse(
            json.dumps([SAMPLE_TWEET_RUSSIA, SAMPLE_TWEET_CHINA])
        )
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_slug_format(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_TWEET_RUSSIA]))
        assert events[0].slug is not None
        assert events[0].slug.startswith("twitter-")

    @pytest.mark.asyncio
    async def test_claim_lifecycle_is_rumor(self) -> None:
        events = await SCRAPER.parse(
            json.dumps([SAMPLE_TWEET_RUSSIA, SAMPLE_TWEET_CHINA])
        )
        for event in events:
            assert event.claim_lifecycle == "rumor"

    @pytest.mark.asyncio
    async def test_event_kind_is_inferred(self) -> None:
        events = await SCRAPER.parse(
            json.dumps([SAMPLE_TWEET_RUSSIA, SAMPLE_TWEET_CHINA])
        )
        for event in events:
            assert event.event_kind == "inferred"

    @pytest.mark.asyncio
    async def test_provider_includes_username(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_TWEET_RUSSIA]))
        assert "@RoscosmosNews" in events[0].provider

    @pytest.mark.asyncio
    async def test_china_provider(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_TWEET_CHINA]))
        assert "@CNSAWatcher" in events[0].provider

    @pytest.mark.asyncio
    async def test_name_from_text_stripped(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_TWEET_RUSSIA]))
        # t.co links should be stripped from display name
        assert "https://t.co" not in events[0].name
        assert "Roscosmos" in events[0].name

    @pytest.mark.asyncio
    async def test_china_name_content(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_TWEET_CHINA]))
        assert "Long March" in events[0].name

    @pytest.mark.asyncio
    async def test_launch_date_parsed(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_TWEET_RUSSIA]))
        assert isinstance(events[0].launch_date, datetime)

    @pytest.mark.asyncio
    async def test_precision_is_day(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_TWEET_RUSSIA]))
        assert events[0].launch_date_precision == "day"

    @pytest.mark.asyncio
    async def test_status_is_scheduled(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_TWEET_RUSSIA]))
        assert events[0].status == "scheduled"

    @pytest.mark.asyncio
    async def test_image_urls_captured(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_TWEET_RUSSIA]))
        assert len(events[0].image_urls) >= 1
        assert "soyuz_launch.jpg" in events[0].image_urls[0]

    @pytest.mark.asyncio
    async def test_china_image_urls_captured(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_TWEET_CHINA]))
        assert len(events[0].image_urls) >= 1
        assert "longmarch5b.jpg" in events[0].image_urls[0]

    @pytest.mark.asyncio
    async def test_no_images_empty_list(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_TWEET_CHINA_2]))
        assert events[0].image_urls == []

    @pytest.mark.asyncio
    async def test_invalid_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid JSON"):
            await SCRAPER.parse("not-json")

    @pytest.mark.asyncio
    async def test_missing_id_skipped(self) -> None:
        bad = {"text": "launch today", "_username": "x"}
        events = await SCRAPER.parse(json.dumps([bad]))
        assert events == []

    @pytest.mark.asyncio
    async def test_missing_text_skipped(self) -> None:
        bad = {"id": "123", "_username": "x"}
        events = await SCRAPER.parse(json.dumps([bad]))
        assert events == []

    @pytest.mark.asyncio
    async def test_data_wrapper_accepted(self) -> None:
        """parse() accepts the {"data": [...]} wrapper format."""
        wrapped = {"data": [SAMPLE_TWEET_RUSSIA]}
        events = await SCRAPER.parse(json.dumps(wrapped))
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_all_four_synthetic_tweets(self) -> None:
        """All four Russia/China tweets parse correctly."""
        all_tweets = [
            SAMPLE_TWEET_RUSSIA,
            SAMPLE_TWEET_CHINA,
            SAMPLE_TWEET_CHINA_2,
            SAMPLE_TWEET_RUSSIA_2,
        ]
        events = await SCRAPER.parse(json.dumps(all_tweets))
        assert len(events) == 4
        providers = [e.provider for e in events]
        assert "@RoscosmosNews" in providers
        assert "@CNSAWatcher" in providers
        assert "@SpaceTracker" in providers
        assert "@RussianSpaceWeb" in providers


# ---------------------------------------------------------------------------
# Bearer token / disabled-mode tests
# ---------------------------------------------------------------------------


class TestBearerTokenGating:
    async def test_scrape_returns_empty_without_token(self) -> None:
        """scrape() returns zeros when TWITTER_BEARER_TOKEN is not set."""
        env = os.environ.copy()
        env.pop("TWITTER_BEARER_TOKEN", None)
        with patch.dict(os.environ, env, clear=True):
            scraper = TwitterScraper()
            result = await scraper.scrape()

        assert result["total_fetched"] == 0
        assert result["new_events"] == 0
        assert result["updated_events"] == 0

    def test_get_bearer_token_returns_none_without_env(self) -> None:
        env = os.environ.copy()
        env.pop("TWITTER_BEARER_TOKEN", None)
        with patch.dict(os.environ, env, clear=True):
            assert SCRAPER._get_bearer_token() is None

    def test_get_bearer_token_returns_token(self) -> None:
        with patch.dict(os.environ, {"TWITTER_BEARER_TOKEN": "test-token-123"}):
            assert SCRAPER._get_bearer_token() == "test-token-123"


# ---------------------------------------------------------------------------
# Integration tests — DB insert with Russia/China launch data
# ---------------------------------------------------------------------------


_MOD = "openorbit.scrapers.twitter"


def _make_db_mock(db_connection):  # type: ignore[no-untyped-def]
    """Return a mock async context manager that yields db_connection."""
    mock_get_db = MagicMock()
    mock_get_db.return_value.__aenter__ = AsyncMock(return_value=db_connection)
    mock_get_db.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_get_db


class TestIntegrationDbInsert:
    """scrape() inserts events with mocked HTTP and real in-memory DB."""

    @respx.mock
    async def test_scrape_inserts_russia_china_tweets(self, db_connection) -> None:
        """scrape() inserts launch-relevant tweets about Russia/China launches."""
        respx.get(TwitterScraper.SEARCH_URL).mock(
            return_value=httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
        )

        mock_get_db = _make_db_mock(db_connection)
        with (
            patch.dict(os.environ, {"TWITTER_BEARER_TOKEN": "test-bearer-token"}),
            patch(f"{_MOD}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            scraper = TwitterScraper()
            result = await scraper.scrape()

        assert result["total_fetched"] >= 1
        assert result["new_events"] >= 1

        async with db_connection.execute("SELECT COUNT(*) FROM launch_events") as cur:
            row = await cur.fetchone()
            assert row[0] >= 1

    @respx.mock
    async def test_scrape_dedup_second_run(self, db_connection) -> None:
        """Second scrape() with same tweets must not create duplicates."""
        respx.get(TwitterScraper.SEARCH_URL).mock(
            return_value=httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
        )

        mock_get_db = _make_db_mock(db_connection)

        with (
            patch.dict(os.environ, {"TWITTER_BEARER_TOKEN": "test-bearer-token"}),
            patch(f"{_MOD}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result1 = await TwitterScraper().scrape()

        # Reset for second run
        respx.mock.reset()
        respx.get(TwitterScraper.SEARCH_URL).mock(
            return_value=httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
        )

        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=db_connection)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.dict(os.environ, {"TWITTER_BEARER_TOKEN": "test-bearer-token"}),
            patch(f"{_MOD}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result2 = await TwitterScraper().scrape()

        assert result1["new_events"] >= 1
        assert result2["new_events"] == 0

    @respx.mock
    async def test_irrelevant_tweets_not_inserted(self, db_connection) -> None:
        """Tweets without launch keywords are filtered out."""
        irrelevant_response = {
            "data": [SAMPLE_TWEET_IRRELEVANT],
            "includes": {
                "users": [{"id": "999999", "username": "foodie42"}],
            },
            "meta": {"result_count": 1},
        }
        respx.get(TwitterScraper.SEARCH_URL).mock(
            return_value=httpx.Response(200, json=irrelevant_response)
        )

        mock_get_db = _make_db_mock(db_connection)
        with (
            patch.dict(os.environ, {"TWITTER_BEARER_TOKEN": "test-bearer-token"}),
            patch(f"{_MOD}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result = await TwitterScraper().scrape()

        assert result["total_fetched"] == 0
        assert result["new_events"] == 0

    @respx.mock
    async def test_scrape_records_image_urls(self, db_connection) -> None:
        """Image URLs from tweets are persisted in the database."""
        respx.get(TwitterScraper.SEARCH_URL).mock(
            return_value=httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
        )

        mock_get_db = _make_db_mock(db_connection)
        with (
            patch.dict(os.environ, {"TWITTER_BEARER_TOKEN": "test-bearer-token"}),
            patch(f"{_MOD}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            await TwitterScraper().scrape()

        async with db_connection.execute("SELECT image_urls FROM launch_events") as cur:
            rows = await cur.fetchall()

        has_images = False
        for row in rows:
            images = json.loads(row["image_urls"] or "[]")
            if images:
                has_images = True
                break

        assert has_images
