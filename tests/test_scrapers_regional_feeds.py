"""Tests for regional public-feed adapters (ESA/JAXA/ISRO/Arianespace/CNSA)."""

from __future__ import annotations

import os

import httpx
import pytest
import respx

from openorbit.db import close_db, get_db, init_db
from openorbit.scrapers.arianespace_official import ArianespaceOfficialScraper
from openorbit.scrapers.cnsa_official import CNSAOfficialScraper
from openorbit.scrapers.esa_official import ESAOfficialScraper
from openorbit.scrapers.isro_official import ISROOfficialScraper
from openorbit.scrapers.jaxa_official import JAXAOfficialScraper


@pytest.fixture
async def db_connection():
    """Initialize in-memory DB and clean up after each test."""
    from openorbit import config

    config._settings = None
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    await init_db()
    async with get_db() as conn:
        yield conn

    await close_db()
    config._settings = None


def _sample_rss_feed() -> str:
    """Minimal RSS payload containing launch and non-launch entries."""
    return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<rss version=\"2.0\">
  <channel>
    <title>Agency Updates</title>
    <item>
      <title>Launch mission update for Earth observation satellite</title>
      <link>https://example.org/launch-1</link>
      <pubDate>Tue, 23 Mar 2026 12:00:00 GMT</pubDate>
      <description>Launch campaign is ready for liftoff.</description>
    </item>
    <item>
      <title>General science outreach event</title>
      <link>https://example.org/outreach</link>
      <pubDate>Tue, 22 Mar 2026 12:00:00 GMT</pubDate>
      <description>No mission operations.</description>
    </item>
  </channel>
</rss>
"""


def _sample_rss_feed_with_hints() -> str:
    """RSS payload with source-specific vehicle/location and excluded keywords."""
    return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<rss version=\"2.0\">
  <channel>
    <title>Agency Updates</title>
    <item>
      <title>Ariane 6 launch campaign from Kourou</title>
      <link>https://example.org/launch-vehicle-location</link>
      <pubDate>Tue, 23 Mar 2026 12:00:00 GMT</pubDate>
      <description>Upcoming launch scheduled for next window.</description>
    </item>
    <item>
      <title>Satellite engineering workshop announced</title>
      <link>https://example.org/workshop</link>
      <pubDate>Tue, 22 Mar 2026 12:00:00 GMT</pubDate>
      <description>Training and outreach session.</description>
    </item>
  </channel>
</rss>
"""


REGIONAL_SCRAPERS = [
    ESAOfficialScraper,
    JAXAOfficialScraper,
    ISROOfficialScraper,
    ArianespaceOfficialScraper,
    CNSAOfficialScraper,
]


@pytest.mark.parametrize("scraper_cls", REGIONAL_SCRAPERS)
def test_parse_filters_launch_entries(scraper_cls: type) -> None:
    """Each regional feed scraper should parse launch-like entries only."""
    scraper = scraper_cls()
    events = scraper.parse(_sample_rss_feed())

    assert len(events) == 1
    assert events[0].provider == scraper.PROVIDER_NAME
    assert events[0].status in {"scheduled", "launched", "delayed", "cancelled"}
    assert events[0].slug.startswith(f"{scraper.source_name}-")


def test_parse_applies_exclusion_keywords() -> None:
    """Feed entries with launch words plus exclusion words are dropped."""
    scraper = ESAOfficialScraper()
    events = scraper.parse(_sample_rss_feed_with_hints())

    # Only first entry should remain; workshop/training entry should be filtered out.
    assert len(events) == 1
    assert "workshop" not in events[0].name.lower()


def test_parse_infers_vehicle_and_location_from_hints() -> None:
    """Per-source hints should populate vehicle and location fields."""
    scraper = ESAOfficialScraper()
    events = scraper.parse(_sample_rss_feed_with_hints())

    assert len(events) == 1
    assert events[0].vehicle == "Ariane 6"
    assert events[0].location == "Guiana Space Centre, French Guiana"


@pytest.mark.parametrize("scraper_cls", REGIONAL_SCRAPERS)
@respx.mock
async def test_scrape_creates_events(scraper_cls: type, db_connection) -> None:
    """Each regional scraper should fetch, parse, and insert launch events."""
    scraper = scraper_cls()
    respx.get(scraper.source_url).mock(return_value=httpx.Response(200, text=_sample_rss_feed()))

    result = await scraper.scrape()
    assert result["total_fetched"] == 1
    assert result["new_events"] == 1
    assert result["updated_events"] == 0


@pytest.mark.parametrize("scraper_cls", REGIONAL_SCRAPERS)
@respx.mock
async def test_scrape_idempotent(scraper_cls: type, db_connection) -> None:
    """Running same regional feed twice should update, not duplicate."""
    scraper = scraper_cls()
    respx.get(scraper.source_url).mock(return_value=httpx.Response(200, text=_sample_rss_feed()))

    first = await scraper.scrape()
    assert first["new_events"] == 1

    respx.get(scraper.source_url).mock(return_value=httpx.Response(200, text=_sample_rss_feed()))
    second = await scraper.scrape()
    assert second["new_events"] == 0
    assert second["updated_events"] == 1
