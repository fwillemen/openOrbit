"""Tests for Tier 3 News RSS scrapers (SpaceFlightNow and NASASpaceflight)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from openorbit.db import close_db, get_db, init_db
from openorbit.scrapers.news import (
    NASASpaceflightScraper,
    NewsRSSScraper,
    SpaceFlightNowScraper,
)

_MOD = "openorbit.scrapers.news"

# ---------------------------------------------------------------------------
# RSS XML Fixtures
# ---------------------------------------------------------------------------

SFN_FEED_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Spaceflight Now</title>
    <link>https://spaceflightnow.com</link>
    <item>
      <title>SpaceX Falcon 9 rocket to launch Starlink satellites from Cape Canaveral</title>
      <link>https://spaceflightnow.com/2025/06/01/starlink-launch/</link>
      <pubDate>Sun, 01 Jun 2025 14:00:00 +0000</pubDate>
      <description>A SpaceX Falcon 9 rocket is scheduled for liftoff from Space Launch Complex 40 carrying a new batch of Starlink internet satellites into orbit.</description>
    </item>
    <item>
      <title>Rocket Lab Electron mission countdown begins for Earth observation satellite</title>
      <link>https://spaceflightnow.com/2025/07/10/electron-mission/</link>
      <pubDate>Thu, 10 Jul 2025 08:00:00 +0000</pubDate>
      <description>Rocket Lab has started the countdown for its Electron rocket mission carrying a commercial Earth observation spacecraft from Mahia, New Zealand.</description>
    </item>
    <item>
      <title>NASA conference on workforce diversity</title>
      <link>https://spaceflightnow.com/2025/05/15/nasa-conference/</link>
      <pubDate>Thu, 15 May 2025 10:00:00 +0000</pubDate>
      <description>NASA is hosting a conference on education and outreach programs.</description>
    </item>
  </channel>
</rss>
"""

NSF_FEED_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>NASASpaceflight.com</title>
    <link>https://www.nasaspaceflight.com</link>
    <item>
      <title>Ariane 6 rocket prepares for its next mission to orbit from Kourou</title>
      <link>https://www.nasaspaceflight.com/2025/06/ariane-6-orbit/</link>
      <pubDate>Mon, 02 Jun 2025 10:30:00 +0000</pubDate>
      <description>Arianespace is counting down to the launch of Ariane 6 rocket carrying two satellites into geostationary orbit from Europe's Spaceport in French Guiana.</description>
    </item>
    <item>
      <title>SLS mission countdown: Artemis spacecraft targeting lunar orbit insertion</title>
      <link>https://www.nasaspaceflight.com/2025/08/artemis-sls-orbit/</link>
      <pubDate>Fri, 01 Aug 2025 00:00:00 +0000</pubDate>
      <description>NASA's Space Launch System rocket is in final countdown for an Artemis mission, with spacecraft scheduled for lunar orbit.</description>
    </item>
    <item>
      <title>Industry award ceremony for best aerospace internship program</title>
      <link>https://www.nasaspaceflight.com/2025/05/internship-award/</link>
      <pubDate>Wed, 14 May 2025 09:00:00 +0000</pubDate>
      <description>Annual internship and education award for aerospace companies.</description>
    </item>
  </channel>
</rss>
"""

# Feed with a single item
MINIMAL_SFN_FEED_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Spaceflight Now</title>
    <item>
      <title>New satellite rocket mission countdown starts</title>
      <link>https://spaceflightnow.com/2025/09/01/mission/</link>
      <pubDate>Mon, 01 Sep 2025 12:00:00 +0000</pubDate>
      <description>A new rocket is on the launch pad for a mission to orbit a communication spacecraft.</description>
    </item>
  </channel>
</rss>
"""

# Empty feed
EMPTY_FEED_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Empty</title></channel></rss>
"""


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_connection():  # type: ignore[return]
    """Provide a fresh in-memory database connection for each test."""
    from openorbit import config

    config._settings = None
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    await init_db()
    async with get_db() as conn:
        yield conn

    await close_db()
    config._settings = None


def _make_db_mock(db_conn):  # type: ignore[no-untyped-def]
    """Return async context manager mock that yields db_conn."""
    mock = MagicMock()
    mock.return_value.__aenter__ = AsyncMock(return_value=db_conn)
    mock.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock


# ---------------------------------------------------------------------------
# Class-variable tests (no HTTP, no DB)
# ---------------------------------------------------------------------------


class TestClassVariables:
    """Verify class-level metadata on the news scrapers."""

    def test_spaceflightnow_source_tier_is_3(self) -> None:
        assert SpaceFlightNowScraper.source_tier == 3

    def test_nasaspaceflight_source_tier_is_3(self) -> None:
        assert NASASpaceflightScraper.source_tier == 3

    def test_spaceflightnow_evidence_type_is_media(self) -> None:
        assert SpaceFlightNowScraper.evidence_type == "media"

    def test_nasaspaceflight_evidence_type_is_media(self) -> None:
        assert NASASpaceflightScraper.evidence_type == "media"

    def test_spaceflightnow_source_name(self) -> None:
        assert SpaceFlightNowScraper.source_name == "news_spaceflightnow"

    def test_nasaspaceflight_source_name(self) -> None:
        assert NASASpaceflightScraper.source_name == "news_nasaspaceflight"

    def test_spaceflightnow_feed_region_is_global(self) -> None:
        assert SpaceFlightNowScraper.feed_region() == "global"

    def test_nasaspaceflight_feed_region_is_global(self) -> None:
        assert NASASpaceflightScraper.feed_region() == "global"

    def test_keywords_include_orbit(self) -> None:
        assert "orbit" in NewsRSSScraper.KEYWORDS

    def test_keywords_include_countdown(self) -> None:
        assert "countdown" in NewsRSSScraper.KEYWORDS

    def test_keywords_include_mission(self) -> None:
        assert "mission" in NewsRSSScraper.KEYWORDS


# ---------------------------------------------------------------------------
# parse() unit tests — SpaceFlightNow
# ---------------------------------------------------------------------------


class TestSpaceFlightNowParse:
    """parse() unit tests for SpaceFlightNowScraper."""

    def test_parse_returns_only_launch_relevant_events(self) -> None:
        """parse() filters out non-launch items (conference/education)."""
        scraper = SpaceFlightNowScraper()
        events = scraper.parse(SFN_FEED_XML)
        # 3 items in feed; 1 filtered (conference/outreach)
        assert len(events) == 2

    def test_parse_all_events_have_rumor_claim_lifecycle(self) -> None:
        """Every parsed event must have claim_lifecycle='rumor'."""
        scraper = SpaceFlightNowScraper()
        events = scraper.parse(SFN_FEED_XML)
        assert all(e.claim_lifecycle == "rumor" for e in events)

    def test_parse_all_events_have_inferred_event_kind(self) -> None:
        """Every parsed event must have event_kind='inferred'."""
        scraper = SpaceFlightNowScraper()
        events = scraper.parse(SFN_FEED_XML)
        assert all(e.event_kind == "inferred" for e in events)

    def test_parse_events_have_correct_provider(self) -> None:
        scraper = SpaceFlightNowScraper()
        events = scraper.parse(SFN_FEED_XML)
        assert all(e.provider == "SpaceFlightNow" for e in events)

    def test_parse_minimal_feed_returns_one_event(self) -> None:
        scraper = SpaceFlightNowScraper()
        events = scraper.parse(MINIMAL_SFN_FEED_XML)
        assert len(events) == 1
        assert events[0].claim_lifecycle == "rumor"
        assert events[0].event_kind == "inferred"

    def test_parse_empty_feed_returns_no_events(self) -> None:
        scraper = SpaceFlightNowScraper()
        events = scraper.parse(EMPTY_FEED_XML)
        assert events == []

    def test_parse_event_name_matches_title(self) -> None:
        scraper = SpaceFlightNowScraper()
        events = scraper.parse(MINIMAL_SFN_FEED_XML)
        assert (
            "satellite" in events[0].name.lower() or "rocket" in events[0].name.lower()
        )

    def test_parse_event_has_slug(self) -> None:
        scraper = SpaceFlightNowScraper()
        events = scraper.parse(SFN_FEED_XML)
        for e in events:
            assert e.slug is not None
            assert e.slug.startswith("news_spaceflightnow-")


# ---------------------------------------------------------------------------
# parse() unit tests — NASASpaceflight
# ---------------------------------------------------------------------------


class TestNASASpaceflightParse:
    """parse() unit tests for NASASpaceflightScraper."""

    def test_parse_returns_only_launch_relevant_events(self) -> None:
        """parse() filters out non-launch items."""
        scraper = NASASpaceflightScraper()
        events = scraper.parse(NSF_FEED_XML)
        # 3 items; 1 filtered (internship award)
        assert len(events) == 2

    def test_parse_all_events_have_rumor_claim_lifecycle(self) -> None:
        scraper = NASASpaceflightScraper()
        events = scraper.parse(NSF_FEED_XML)
        assert all(e.claim_lifecycle == "rumor" for e in events)

    def test_parse_all_events_have_inferred_event_kind(self) -> None:
        scraper = NASASpaceflightScraper()
        events = scraper.parse(NSF_FEED_XML)
        assert all(e.event_kind == "inferred" for e in events)

    def test_parse_events_have_correct_provider(self) -> None:
        scraper = NASASpaceflightScraper()
        events = scraper.parse(NSF_FEED_XML)
        assert all(e.provider == "NASASpaceflight" for e in events)

    def test_parse_event_has_slug(self) -> None:
        scraper = NASASpaceflightScraper()
        events = scraper.parse(NSF_FEED_XML)
        for e in events:
            assert e.slug is not None
            assert e.slug.startswith("news_nasaspaceflight-")

    def test_parse_empty_feed_returns_no_events(self) -> None:
        scraper = NASASpaceflightScraper()
        events = scraper.parse(EMPTY_FEED_XML)
        assert events == []


# ---------------------------------------------------------------------------
# Fuzzy entity linking tests (in-memory DB)
# ---------------------------------------------------------------------------


class TestFuzzyMatching:
    """Unit tests for _fuzzy_match() logic."""

    def test_fuzzy_match_same_provider_same_date_returns_slug(self) -> None:
        """Exact provider+date match returns the existing slug."""
        from datetime import UTC, datetime

        scraper = SpaceFlightNowScraper()
        existing = [
            {
                "slug": "spacex-abc123",
                "provider": "SpaceFlightNow",
                "launch_date": "2025-06-01T14:00:00+00:00",
            }
        ]
        from openorbit.models.db import LaunchEventCreate

        candidate = LaunchEventCreate(
            name="Test",
            launch_date=datetime(2025, 6, 1, 14, 0, 0, tzinfo=UTC),
            launch_date_precision="day",
            provider="SpaceFlightNow",
            status="scheduled",
            claim_lifecycle="rumor",
            event_kind="inferred",
        )
        slug = scraper._fuzzy_match(candidate, existing)
        assert slug == "spacex-abc123"

    def test_fuzzy_match_within_one_day_returns_slug(self) -> None:
        """Provider+date within 1 day window returns the existing slug."""
        from datetime import UTC, datetime

        from openorbit.models.db import LaunchEventCreate

        scraper = SpaceFlightNowScraper()
        existing = [
            {
                "slug": "sfn-xyz789",
                "provider": "SpaceFlightNow",
                "launch_date": "2025-06-01T00:00:00+00:00",
            }
        ]
        candidate = LaunchEventCreate(
            name="Test article",
            launch_date=datetime(2025, 6, 1, 23, 59, 0, tzinfo=UTC),
            launch_date_precision="day",
            provider="SpaceFlightNow",
            status="scheduled",
            claim_lifecycle="rumor",
            event_kind="inferred",
        )
        slug = scraper._fuzzy_match(candidate, existing)
        assert slug == "sfn-xyz789"

    def test_fuzzy_match_beyond_one_day_returns_none(self) -> None:
        """Provider+date more than 1 day apart returns None."""
        from datetime import UTC, datetime

        from openorbit.models.db import LaunchEventCreate

        scraper = SpaceFlightNowScraper()
        existing = [
            {
                "slug": "sfn-old",
                "provider": "SpaceFlightNow",
                "launch_date": "2025-06-01T00:00:00+00:00",
            }
        ]
        candidate = LaunchEventCreate(
            name="Distant article",
            launch_date=datetime(2025, 6, 3, 12, 0, 0, tzinfo=UTC),
            launch_date_precision="day",
            provider="SpaceFlightNow",
            status="scheduled",
            claim_lifecycle="rumor",
            event_kind="inferred",
        )
        slug = scraper._fuzzy_match(candidate, existing)
        assert slug is None

    def test_fuzzy_match_different_provider_returns_none(self) -> None:
        """Mismatched provider returns None even if dates match."""
        from datetime import UTC, datetime

        from openorbit.models.db import LaunchEventCreate

        scraper = SpaceFlightNowScraper()
        existing = [
            {
                "slug": "spacex-xyz",
                "provider": "SpaceX",
                "launch_date": "2025-06-01T14:00:00+00:00",
            }
        ]
        candidate = LaunchEventCreate(
            name="Test",
            launch_date=datetime(2025, 6, 1, 14, 0, 0, tzinfo=UTC),
            launch_date_precision="day",
            provider="SpaceFlightNow",
            status="scheduled",
            claim_lifecycle="rumor",
            event_kind="inferred",
        )
        slug = scraper._fuzzy_match(candidate, existing)
        assert slug is None

    def test_fuzzy_match_empty_existing_returns_none(self) -> None:
        """Empty existing events list always returns None."""
        from datetime import UTC, datetime

        from openorbit.models.db import LaunchEventCreate

        scraper = SpaceFlightNowScraper()
        candidate = LaunchEventCreate(
            name="Test",
            launch_date=datetime(2025, 6, 1, 14, 0, 0, tzinfo=UTC),
            launch_date_precision="day",
            provider="SpaceFlightNow",
            status="scheduled",
            claim_lifecycle="rumor",
            event_kind="inferred",
        )
        assert scraper._fuzzy_match(candidate, []) is None


# ---------------------------------------------------------------------------
# Integration tests — scrape() with in-memory DB + respx
# ---------------------------------------------------------------------------


class TestScrapeIntegration:
    """Integration tests for scrape() using respx + in-memory DB."""

    @respx.mock
    async def test_scrape_spaceflightnow_creates_new_events(
        self, db_connection
    ) -> None:
        """scrape() with no existing events creates new rumor events."""
        respx.get("https://spaceflightnow.com/feed/").mock(
            return_value=httpx.Response(200, text=SFN_FEED_XML)
        )
        scraper = SpaceFlightNowScraper()
        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(
                "openorbit.scrapers.public_feed.asyncio.sleep", new_callable=AsyncMock
            ),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result = await scraper.scrape()

        assert result["total_fetched"] == 2
        assert result["new_events"] == 2
        assert result["updated_events"] == 0

    @respx.mock
    async def test_scrape_nasaspaceflight_creates_new_events(
        self, db_connection
    ) -> None:
        """scrape() with NASASpaceflight feed creates new rumor events."""
        respx.get("https://www.nasaspaceflight.com/feed/").mock(
            return_value=httpx.Response(200, text=NSF_FEED_XML)
        )
        scraper = NASASpaceflightScraper()
        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(
                "openorbit.scrapers.public_feed.asyncio.sleep", new_callable=AsyncMock
            ),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result = await scraper.scrape()

        assert result["total_fetched"] == 2
        assert result["new_events"] == 2
        assert result["updated_events"] == 0

    @respx.mock
    async def test_scrape_fuzzy_match_existing_event_attribution_only(
        self, db_connection
    ) -> None:
        """scrape() links to an existing event when provider+date match."""
        from datetime import UTC, datetime

        from openorbit.db import upsert_launch_event
        from openorbit.models.db import LaunchEventCreate

        # Pre-insert a matching event
        await upsert_launch_event(
            db_connection,
            LaunchEventCreate(
                name="SpaceX Starlink existing",
                launch_date=datetime(2025, 6, 1, 14, 0, 0, tzinfo=UTC),
                launch_date_precision="day",
                provider="SpaceFlightNow",
                status="scheduled",
                claim_lifecycle="indicated",
                event_kind="observed",
                slug="sfn-existing-slug",
            ),
        )

        respx.get("https://spaceflightnow.com/feed/").mock(
            return_value=httpx.Response(200, text=SFN_FEED_XML)
        )

        scraper = SpaceFlightNowScraper()
        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(
                "openorbit.scrapers.public_feed.asyncio.sleep", new_callable=AsyncMock
            ),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result = await scraper.scrape()

        # One event matched (updated_events), one is new
        assert result["total_fetched"] == 2
        assert result["updated_events"] >= 1

    @respx.mock
    async def test_scrape_http_error_returns_zero(self, db_connection) -> None:
        """HTTP 503 results in zero events scraped."""
        respx.get("https://spaceflightnow.com/feed/").mock(
            return_value=httpx.Response(503)
        )
        scraper = SpaceFlightNowScraper()
        scraper.settings.SCRAPER_MAX_RETRIES = 1  # type: ignore[assignment]
        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(
                "openorbit.scrapers.public_feed.asyncio.sleep", new_callable=AsyncMock
            ),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            result = await scraper.scrape()

        assert result["total_fetched"] == 0
        assert result["new_events"] == 0

    @respx.mock
    async def test_scrape_new_events_have_rumor_lifecycle(self, db_connection) -> None:
        """Events created by scrape() must have claim_lifecycle='rumor'."""
        respx.get("https://spaceflightnow.com/feed/").mock(
            return_value=httpx.Response(200, text=MINIMAL_SFN_FEED_XML)
        )
        scraper = SpaceFlightNowScraper()
        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(
                "openorbit.scrapers.public_feed.asyncio.sleep", new_callable=AsyncMock
            ),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            await scraper.scrape()

        async with db_connection.execute(
            "SELECT claim_lifecycle FROM launch_events WHERE provider='SpaceFlightNow'"
        ) as cursor:
            rows = await cursor.fetchall()

        assert len(rows) >= 1
        assert all(row["claim_lifecycle"] == "rumor" for row in rows)

    @respx.mock
    async def test_scrape_source_registered_with_tier_3(self, db_connection) -> None:
        """_ensure_source_registered registers source at tier 3."""
        respx.get("https://spaceflightnow.com/feed/").mock(
            return_value=httpx.Response(200, text=EMPTY_FEED_XML)
        )
        scraper = SpaceFlightNowScraper()
        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(
                "openorbit.scrapers.public_feed.asyncio.sleep", new_callable=AsyncMock
            ),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            await scraper.scrape()

        async with db_connection.execute(
            "SELECT source_tier FROM osint_sources WHERE name='SpaceFlightNow RSS'"
        ) as cursor:
            row = await cursor.fetchone()

        assert row is not None
        assert row["source_tier"] == 3
