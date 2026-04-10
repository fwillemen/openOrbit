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
from openorbit.scrapers.roscosmos_official import RoscosmosOfficialScraper


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
    RoscosmosOfficialScraper,
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


def _sample_roscosmos_rss_feed() -> str:
    """RSS payload with Roscosmos-specific vehicle and location keywords."""
    return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<rss version=\"2.0\">
  <channel>
    <title>Roscosmos News</title>
    <item>
      <title>Soyuz-2.1b rocket launch from Baikonur cosmodrome</title>
      <link>https://www.roscosmos.ru/eng/launch-soyuz</link>
      <pubDate>Tue, 23 Mar 2026 12:00:00 GMT</pubDate>
      <description>Upcoming launch of the Soyuz-2.1b rocket from Baikonur.</description>
    </item>
    <item>
      <title>Angara-A5 liftoff from Plesetsk cosmodrome</title>
      <link>https://www.roscosmos.ru/eng/launch-angara</link>
      <pubDate>Wed, 24 Mar 2026 09:00:00 GMT</pubDate>
      <description>Angara-A5 heavy-lift rocket liftoff from Plesetsk.</description>
    </item>
  </channel>
</rss>
"""


def test_roscosmos_parse_filters_launch_entries() -> None:
    """RoscosmosOfficialScraper should parse launch-like entries only."""
    scraper = RoscosmosOfficialScraper()
    events = scraper.parse(_sample_rss_feed())

    assert len(events) == 1
    assert events[0].provider == "Roscosmos"
    assert events[0].slug.startswith("roscosmos_official-")


def test_roscosmos_parse_infers_vehicle_soyuz() -> None:
    """Soyuz vehicle hint should be inferred from title text."""
    scraper = RoscosmosOfficialScraper()
    events = scraper.parse(_sample_roscosmos_rss_feed())

    soyuz_events = [e for e in events if e.vehicle and "Soyuz" in e.vehicle]
    assert len(soyuz_events) >= 1
    assert soyuz_events[0].vehicle == "Soyuz-2.1b"


def test_roscosmos_parse_infers_vehicle_angara() -> None:
    """Angara vehicle hint should be inferred from title text."""
    scraper = RoscosmosOfficialScraper()
    events = scraper.parse(_sample_roscosmos_rss_feed())

    angara_events = [e for e in events if e.vehicle and "Angara" in e.vehicle]
    assert len(angara_events) >= 1
    assert angara_events[0].vehicle == "Angara-A5"


def test_roscosmos_parse_infers_location_baikonur() -> None:
    """Baikonur location hint should be inferred from feed text."""
    scraper = RoscosmosOfficialScraper()
    events = scraper.parse(_sample_roscosmos_rss_feed())

    baikonur_events = [e for e in events if e.location and "Baikonur" in e.location]
    assert len(baikonur_events) >= 1
    assert baikonur_events[0].location == "Baikonur Cosmodrome, Kazakhstan"


def test_roscosmos_parse_infers_location_plesetsk() -> None:
    """Plesetsk location hint should be inferred from feed text."""
    scraper = RoscosmosOfficialScraper()
    events = scraper.parse(_sample_roscosmos_rss_feed())

    plesetsk_events = [e for e in events if e.location and "Plesetsk" in e.location]
    assert len(plesetsk_events) >= 1
    assert plesetsk_events[0].location == "Plesetsk Cosmodrome, Russia"


def test_roscosmos_feed_region() -> None:
    """RoscosmosOfficialScraper.feed_region should return 'eurasia'."""
    assert RoscosmosOfficialScraper.feed_region() == "eurasia"


def test_roscosmos_source_tier_is_1() -> None:
    """Roscosmos is a Tier 1 (official/regulatory) source."""
    assert RoscosmosOfficialScraper.source_tier == 1


def test_roscosmos_evidence_type() -> None:
    """Roscosmos should produce official_schedule evidence."""
    assert RoscosmosOfficialScraper.evidence_type == "official_schedule"
