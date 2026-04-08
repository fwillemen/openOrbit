"""Tests for RedditScraper."""

from __future__ import annotations

import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from openorbit.db import close_db, get_db, init_db
from openorbit.scrapers.reddit import (
    RedditScraper,
    _extract_image_urls,
    _make_slug,
    _strip_markdown,
)

# ---------------------------------------------------------------------------
# Fixtures / sample payloads
# ---------------------------------------------------------------------------

SAMPLE_POST_1: dict = {
    "permalink": "/r/spacex/comments/abc123/falcon_9_launch/",
    "title": "SpaceX Falcon 9 rocket launch from Cape Canaveral!",
    "selftext": "Just watched the Falcon 9 launch live. Amazing liftoff!",
    "author": "spacefan42",
    "created_utc": 1705340400.0,
    "subreddit": "spacex",
    "url": "https://i.redd.it/abc123.jpg",
    "post_hint": "image",
}

SAMPLE_POST_2: dict = {
    "permalink": "/r/spaceflight/comments/def456/ula_vulcan_launch/",
    "title": "ULA Vulcan Centaur launch thread - mission to orbit",
    "selftext": "",
    "author": "ulafan",
    "created_utc": 1705426800.0,
    "subreddit": "spaceflight",
    "url": "https://www.reddit.com/r/spaceflight/comments/def456/",
}

SAMPLE_POST_IRRELEVANT: dict = {
    "permalink": "/r/science/comments/ghi789/new_chemistry_paper/",
    "title": "New chemistry paper on molecular bonds",
    "selftext": "This is about chemistry, not space.",
    "author": "chemist99",
    "created_utc": 1705513200.0,
    "subreddit": "science",
    "url": "https://www.reddit.com/r/science/comments/ghi789/",
}

SAMPLE_POST_WITH_GALLERY: dict = {
    "permalink": "/r/spacex/comments/jkl012/launch_photos/",
    "title": "Launch photos from today's rocket mission",
    "selftext": "",
    "author": "photographer",
    "created_utc": 1705340400.0,
    "subreddit": "spacex",
    "url": "https://www.reddit.com/gallery/jkl012",
    "media_metadata": {
        "img1": {
            "status": "valid",
            "s": {"u": "https://preview.redd.it/img1.jpg?width=1024&amp;format=pjpg"},
        },
        "img2": {
            "status": "valid",
            "s": {"u": "https://preview.redd.it/img2.png?width=800&amp;format=png"},
        },
    },
}

SAMPLE_SUBREDDIT_RESPONSE: dict = {
    "data": {
        "children": [
            {"data": SAMPLE_POST_1},
            {"data": SAMPLE_POST_2},
        ],
    }
}

SCRAPER = RedditScraper()


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
        assert RedditScraper.source_tier == 3

    def test_evidence_type_is_media(self) -> None:
        assert RedditScraper.evidence_type == "media"

    def test_source_name(self) -> None:
        assert RedditScraper.source_name == "reddit"

    def test_source_url(self) -> None:
        assert "reddit.com" in RedditScraper.source_url

    def test_subreddits_non_empty(self) -> None:
        assert len(RedditScraper.SUBREDDITS) > 0

    def test_subreddits_contain_space_subs(self) -> None:
        subs = set(RedditScraper.SUBREDDITS)
        assert "spacex" in subs
        assert "spaceflight" in subs

    def test_refresh_interval(self) -> None:
        assert RedditScraper.refresh_interval_hours == 2


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

    def test_case_insensitive(self) -> None:
        assert SCRAPER._is_launch_relevant("ROCKET LAUNCH") is True

    def test_no_match(self) -> None:
        assert SCRAPER._is_launch_relevant("Just a chemistry paper") is False

    def test_empty_string(self) -> None:
        assert SCRAPER._is_launch_relevant("") is False


# ---------------------------------------------------------------------------
# _extract_image_urls tests
# ---------------------------------------------------------------------------


class TestExtractImageUrls:
    def test_direct_image_link(self) -> None:
        urls = _extract_image_urls({"url": "https://i.redd.it/photo.jpg"})
        assert "https://i.redd.it/photo.jpg" in urls

    def test_post_hint_image(self) -> None:
        urls = _extract_image_urls(
            {"url": "https://i.redd.it/photo.png", "post_hint": "image"}
        )
        assert len(urls) == 1

    def test_gallery_metadata(self) -> None:
        urls = _extract_image_urls(SAMPLE_POST_WITH_GALLERY)
        assert len(urls) >= 2
        assert any("img1" in u for u in urls)
        assert any("img2" in u for u in urls)

    def test_amp_decoded_in_gallery(self) -> None:
        urls = _extract_image_urls(SAMPLE_POST_WITH_GALLERY)
        for url in urls:
            assert "&amp;" not in url

    def test_preview_images(self) -> None:
        post = {
            "url": "https://www.reddit.com/r/spacex/comments/abc/",
            "preview": {
                "images": [{"source": {"url": "https://preview.redd.it/preview.jpg"}}]
            },
        }
        urls = _extract_image_urls(post)
        assert "https://preview.redd.it/preview.jpg" in urls

    def test_no_images(self) -> None:
        urls = _extract_image_urls(
            {"url": "https://www.reddit.com/r/spacex/comments/abc/"}
        )
        assert urls == []


# ---------------------------------------------------------------------------
# _strip_markdown tests
# ---------------------------------------------------------------------------


class TestStripMarkdown:
    def test_strips_links(self) -> None:
        assert "click here" in _strip_markdown("[click here](https://example.com)")

    def test_strips_bold(self) -> None:
        result = _strip_markdown("**bold text**")
        assert "bold" in result
        assert "**" not in result

    def test_plain_text_unchanged(self) -> None:
        assert _strip_markdown("plain text") == "plain text"


# ---------------------------------------------------------------------------
# parse() unit tests
# ---------------------------------------------------------------------------


class TestParse:
    @pytest.mark.asyncio
    async def test_returns_correct_count(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_POST_1, SAMPLE_POST_2]))
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_slug_format(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_POST_1]))
        assert events[0].slug is not None
        assert events[0].slug.startswith("reddit-")

    @pytest.mark.asyncio
    async def test_claim_lifecycle_is_rumor(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_POST_1, SAMPLE_POST_2]))
        for event in events:
            assert event.claim_lifecycle == "rumor"

    @pytest.mark.asyncio
    async def test_event_kind_is_inferred(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_POST_1, SAMPLE_POST_2]))
        for event in events:
            assert event.event_kind == "inferred"

    @pytest.mark.asyncio
    async def test_provider_includes_author(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_POST_1]))
        assert "spacefan42" in events[0].provider

    @pytest.mark.asyncio
    async def test_name_from_title(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_POST_1]))
        assert "Falcon 9" in events[0].name

    @pytest.mark.asyncio
    async def test_launch_date_parsed(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_POST_1]))
        assert isinstance(events[0].launch_date, datetime)

    @pytest.mark.asyncio
    async def test_precision_is_day(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_POST_1]))
        assert events[0].launch_date_precision == "day"

    @pytest.mark.asyncio
    async def test_status_is_scheduled(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_POST_1]))
        assert events[0].status == "scheduled"

    @pytest.mark.asyncio
    async def test_image_urls_captured(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_POST_1]))
        assert len(events[0].image_urls) >= 1
        assert "i.redd.it" in events[0].image_urls[0]

    @pytest.mark.asyncio
    async def test_gallery_image_urls_captured(self) -> None:
        events = await SCRAPER.parse(json.dumps([SAMPLE_POST_WITH_GALLERY]))
        assert len(events[0].image_urls) >= 2

    @pytest.mark.asyncio
    async def test_invalid_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid JSON"):
            await SCRAPER.parse("not-json")

    @pytest.mark.asyncio
    async def test_missing_permalink_skipped(self) -> None:
        bad = {"title": "launch today", "author": "x", "created_utc": 0}
        events = await SCRAPER.parse(json.dumps([bad]))
        assert events == []

    @pytest.mark.asyncio
    async def test_missing_title_skipped(self) -> None:
        bad = {
            "permalink": "/r/spacex/comments/abc/test/",
            "author": "x",
            "created_utc": 0,
        }
        events = await SCRAPER.parse(json.dumps([bad]))
        assert events == []


# ---------------------------------------------------------------------------
# Dedup test
# ---------------------------------------------------------------------------


class TestDedupByPermalink:
    def test_make_slug_deterministic(self) -> None:
        slug1 = _make_slug("/r/spacex/comments/abc/test/")
        slug2 = _make_slug("/r/spacex/comments/abc/test/")
        assert slug1 == slug2

    def test_make_slug_different_permalinks(self) -> None:
        slug1 = _make_slug("/r/spacex/comments/abc/test1/")
        slug2 = _make_slug("/r/spacex/comments/def/test2/")
        assert slug1 != slug2


# ---------------------------------------------------------------------------
# Integration tests — DB insert
# ---------------------------------------------------------------------------


_MOD = "openorbit.scrapers.reddit"


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
        """scrape() inserts launch-relevant posts from subreddits."""
        for subreddit in RedditScraper.SUBREDDITS:
            respx.get(f"https://www.reddit.com/r/{subreddit}/new.json").mock(
                return_value=httpx.Response(200, json=SAMPLE_SUBREDDIT_RESPONSE)
            )

        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            scraper = RedditScraper()
            result = await scraper.scrape()

        assert result["total_fetched"] >= 1
        assert result["new_events"] >= 1

        async with db_connection.execute("SELECT COUNT(*) FROM launch_events") as cur:
            row = await cur.fetchone()
            assert row[0] >= 1

    @respx.mock
    async def test_scrape_dedup_second_run(self, db_connection) -> None:
        """Second scrape() with same posts must not create duplicate events."""
        for subreddit in RedditScraper.SUBREDDITS:
            respx.get(f"https://www.reddit.com/r/{subreddit}/new.json").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "data": {"children": [{"data": SAMPLE_POST_1}]},
                    },
                )
            )

        mock_get_db = _make_db_mock(db_connection)

        with (
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result1 = await RedditScraper().scrape()

        # Reset for second run
        respx.mock.reset()
        for subreddit in RedditScraper.SUBREDDITS:
            respx.get(f"https://www.reddit.com/r/{subreddit}/new.json").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "data": {"children": [{"data": SAMPLE_POST_1}]},
                    },
                )
            )

        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=db_connection)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result2 = await RedditScraper().scrape()

        assert result1["new_events"] >= 1
        assert result2["new_events"] == 0

    @respx.mock
    async def test_irrelevant_posts_not_inserted(self, db_connection) -> None:
        """Posts without launch keywords are filtered out."""
        for subreddit in RedditScraper.SUBREDDITS:
            respx.get(f"https://www.reddit.com/r/{subreddit}/new.json").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "data": {"children": [{"data": SAMPLE_POST_IRRELEVANT}]},
                    },
                )
            )

        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result = await RedditScraper().scrape()

        assert result["total_fetched"] == 0
        assert result["new_events"] == 0
