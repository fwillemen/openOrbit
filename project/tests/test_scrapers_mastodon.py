"""Tests for MastodonScraper."""

from __future__ import annotations

import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from openorbit.db import close_db, get_db, init_db
from openorbit.scrapers.mastodon import MastodonScraper, _make_slug

# ---------------------------------------------------------------------------
# Sample payloads
# ---------------------------------------------------------------------------

SAMPLE_STATUS_1 = {
    "id": "109876543210",
    "url": "https://mastodon.social/@spaceenthusiast/109876543210",
    "content": "<p>Falcon 9 rocket launch successful! SpaceX confirms orbit injection. #spacex #launch</p>",
    "created_at": "2024-01-15T18:30:00.000Z",
    "account": {"acct": "spaceenthusiast@mastodon.social"},
}
SAMPLE_STATUS_2 = {
    "id": "109876543211",
    "url": "https://mastodon.social/@rocketwatch/109876543211",
    "content": "<p>Watching the satellite liftoff from Kennedy Space Center! #nasa #rocket</p>",
    "created_at": "2024-01-16T12:00:00.000Z",
    "account": {"acct": "rocketwatch@mastodon.social"},
}

SCRAPER = MastodonScraper()


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
# Helper
# ---------------------------------------------------------------------------


def _make_db_mock(db_connection):  # type: ignore[no-untyped-def]
    """Return a mock async context manager that yields *db_connection*."""
    mock_get_db = MagicMock()
    mock_get_db.return_value.__aenter__ = AsyncMock(return_value=db_connection)
    mock_get_db.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_get_db


_MOD = "openorbit.scrapers.mastodon"


# ---------------------------------------------------------------------------
# Class-variable tests
# ---------------------------------------------------------------------------


class TestClassVars:
    def test_source_tier(self) -> None:
        assert MastodonScraper.source_tier == 3

    def test_evidence_type(self) -> None:
        assert MastodonScraper.evidence_type == "media"

    def test_refresh_interval_hours(self) -> None:
        assert MastodonScraper.refresh_interval_hours == 2

    def test_source_name(self) -> None:
        assert MastodonScraper.source_name == "mastodon"


# ---------------------------------------------------------------------------
# HASHTAGS test
# ---------------------------------------------------------------------------


class TestHashtags:
    def test_hashtags_contains_expected(self) -> None:
        expected = {"spacelaunch", "spacex", "nasa", "rocket", "satellite"}
        assert expected == set(MastodonScraper.HASHTAGS)


# ---------------------------------------------------------------------------
# parse() unit tests
# ---------------------------------------------------------------------------


class TestParseStatuses:
    @pytest.mark.asyncio
    async def test_parse_returns_list(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_STATUS_1, SAMPLE_STATUS_2]))
        assert isinstance(events, list)
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_parse_single_status(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_STATUS_1]))
        assert len(events) == 1
        event = events[0]
        assert event.slug is not None
        assert event.slug.startswith("mastodon-")

    @pytest.mark.asyncio
    async def test_provider_is_account_handle(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_STATUS_1]))
        assert events[0].provider == "spaceenthusiast@mastodon.social"

    @pytest.mark.asyncio
    async def test_launch_date_parsed(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_STATUS_1]))
        assert isinstance(events[0].launch_date, datetime)
        assert events[0].launch_date.year == 2024

    @pytest.mark.asyncio
    async def test_precision_is_day(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_STATUS_1, SAMPLE_STATUS_2]))
        for e in events:
            assert e.launch_date_precision == "day"

    @pytest.mark.asyncio
    async def test_status_is_scheduled(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_STATUS_1]))
        assert events[0].status == "scheduled"

    @pytest.mark.asyncio
    async def test_launch_type_civilian(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_STATUS_1]))
        assert events[0].launch_type == "civilian"

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid JSON"):
            await SCRAPER.parse("not-json")

    @pytest.mark.asyncio
    async def test_missing_url_skipped(self) -> None:
        bad = {
            "content": "<p>rocket launch</p>",
            "created_at": "2024-01-15T10:00:00Z",
            "account": {"acct": "x"},
        }
        events = await SCRAPER.parse(json.dumps([bad]))
        assert events == []

    @pytest.mark.asyncio
    async def test_missing_content_skipped(self) -> None:
        bad = {
            "url": "https://mastodon.social/@x/1",
            "created_at": "2024-01-15T10:00:00Z",
            "account": {"acct": "x"},
        }
        events = await SCRAPER.parse(json.dumps([bad]))
        assert events == []


# ---------------------------------------------------------------------------
# claim_lifecycle and event_kind tests
# ---------------------------------------------------------------------------


class TestClaimLifecycleRumor:
    @pytest.mark.asyncio
    async def test_all_events_rumor(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_STATUS_1, SAMPLE_STATUS_2]))
        for e in events:
            assert e.claim_lifecycle == "rumor"


class TestEventKindInferred:
    @pytest.mark.asyncio
    async def test_all_events_inferred(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_STATUS_1, SAMPLE_STATUS_2]))
        for e in events:
            assert e.event_kind == "inferred"


# ---------------------------------------------------------------------------
# HTML stripping test
# ---------------------------------------------------------------------------


class TestHtmlStripped:
    @pytest.mark.asyncio
    async def test_html_tags_removed_from_name(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_STATUS_1]))
        assert "<" not in events[0].name
        assert ">" not in events[0].name
        assert "Falcon 9 rocket launch successful" in events[0].name


# ---------------------------------------------------------------------------
# _parse_link_header tests
# ---------------------------------------------------------------------------


class TestParseLinkHeader:
    def test_found_next_url(self) -> None:
        header = '<https://mastodon.social/api/v1/timelines/tag/spacex?max_id=123>; rel="next", <https://mastodon.social/api/v1/timelines/tag/spacex?min_id=456>; rel="prev"'
        result = SCRAPER._parse_link_header(header)
        assert (
            result == "https://mastodon.social/api/v1/timelines/tag/spacex?max_id=123"
        )

    def test_returns_none_when_no_next(self) -> None:
        header = '<https://mastodon.social/api/v1/timelines/tag/spacex?min_id=456>; rel="prev"'
        result = SCRAPER._parse_link_header(header)
        assert result is None

    def test_returns_none_for_none_input(self) -> None:
        assert SCRAPER._parse_link_header(None) is None

    def test_returns_none_for_empty_string(self) -> None:
        assert SCRAPER._parse_link_header("") is None


# ---------------------------------------------------------------------------
# Deduplication test
# ---------------------------------------------------------------------------


class TestDedupByUrl:
    @pytest.mark.asyncio
    async def test_same_url_not_deduped_in_parse(self) -> None:
        """parse() itself doesn't deduplicate — scrape() does. Confirm same slug produced."""
        events = await SCRAPER.parse(json.dumps([SAMPLE_STATUS_1, SAMPLE_STATUS_1]))
        assert len(events) == 2
        assert events[0].slug == events[1].slug

    def test_make_slug_deterministic(self) -> None:
        url = "https://mastodon.social/@user/123"
        assert _make_slug(url) == _make_slug(url)

    def test_make_slug_different_urls(self) -> None:
        assert _make_slug("https://mastodon.social/@user/1") != _make_slug(
            "https://mastodon.social/@user/2"
        )


# ---------------------------------------------------------------------------
# Instance env override test
# ---------------------------------------------------------------------------


class TestInstanceEnvOverride:
    @pytest.mark.asyncio
    async def test_instance_override_changes_url(self, db_connection) -> None:
        """MASTODON_INSTANCE env var should change the instance URL used."""
        instance = "fosstodon.org"

        respx.mock.get(f"https://{instance}/api/v1/timelines/tag/spacelaunch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_STATUS_1])
        )
        for hashtag in ("spacex", "nasa", "rocket", "satellite"):
            respx.mock.get(f"https://{instance}/api/v1/timelines/tag/{hashtag}").mock(
                return_value=httpx.Response(200, json=[])
            )

        mock_get_db = _make_db_mock(db_connection)
        env_patch = {"MASTODON_INSTANCE": instance}

        with (
            respx.mock,
            patch.dict(os.environ, env_patch),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            scraper = MastodonScraper()
            result = await scraper.scrape()

        assert result["total_fetched"] >= 1


# ---------------------------------------------------------------------------
# Integration tests — DB insert
# ---------------------------------------------------------------------------


class TestIntegrationDbInsert:
    """scrape() with mocked httpx inserts events into an in-memory DB."""

    @respx.mock
    async def test_scrape_inserts_events(self, db_connection) -> None:
        for hashtag in MastodonScraper.HASHTAGS:
            respx.get(f"https://mastodon.social/api/v1/timelines/tag/{hashtag}").mock(
                return_value=httpx.Response(
                    200, json=[SAMPLE_STATUS_1, SAMPLE_STATUS_2]
                )
            )

        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            scraper = MastodonScraper()
            result = await scraper.scrape()

        assert result["total_fetched"] >= 1
        assert result["new_events"] >= 1

        async with db_connection.execute("SELECT COUNT(*) FROM launch_events") as cur:
            row = await cur.fetchone()
            assert row[0] >= 1

    @respx.mock
    async def test_integration_second_run_dedup(self, db_connection) -> None:
        """Second scrape() with same posts must not create duplicate events."""
        for hashtag in MastodonScraper.HASHTAGS:
            respx.get(f"https://mastodon.social/api/v1/timelines/tag/{hashtag}").mock(
                return_value=httpx.Response(200, json=[SAMPLE_STATUS_1])
            )

        mock_get_db = _make_db_mock(db_connection)

        with (
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result1 = await MastodonScraper().scrape()

        # Reset respx routes for second run
        respx.mock.reset()
        for hashtag in MastodonScraper.HASHTAGS:
            respx.get(f"https://mastodon.social/api/v1/timelines/tag/{hashtag}").mock(
                return_value=httpx.Response(200, json=[SAMPLE_STATUS_1])
            )

        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=db_connection)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result2 = await MastodonScraper().scrape()

        assert result1["new_events"] >= 1
        assert result2["new_events"] == 0

        async with db_connection.execute("SELECT COUNT(*) FROM launch_events") as cur:
            row = await cur.fetchone()
            assert row[0] == result1["new_events"]
