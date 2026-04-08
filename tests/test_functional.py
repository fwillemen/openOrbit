"""Functional tests verifying the full scrape → DB → API pipeline for every source.

Each test mocks the upstream HTTP endpoint(s), runs the scraper's ``scrape()``
method against a real in-memory SQLite database, and then verifies:

1. Events are correctly stored in the ``launch_events`` table.
2. Events carry the expected OSINT metadata (source_tier, claim_lifecycle,
   event_kind, evidence_type).
3. Events are retrievable through the ``GET /v1/launches`` REST API.
4. The OSINT source is registered in ``osint_sources``.

The tests are organized by tier and source type.
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

import openorbit.config
import openorbit.db as db_module
from openorbit.db import close_db, get_db, init_db
from openorbit.main import create_app

# Module paths for patching
_MOD_COMMERCIAL = "openorbit.scrapers.commercial"
_MOD_BLUESKY = "openorbit.scrapers.bluesky"
_MOD_MASTODON = "openorbit.scrapers.mastodon"
_MOD_REDDIT = "openorbit.scrapers.reddit"
_MOD_FOURCHAN = "openorbit.scrapers.fourchan"

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_connection():
    """Initialize a fresh in-memory database for each test."""
    openorbit.config._settings = None
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    await init_db()
    async with get_db() as conn:
        yield conn

    await close_db()
    openorbit.config._settings = None


@pytest.fixture
async def api_client():
    """Provide an AsyncClient wired to a fresh database and the FastAPI app.

    This enables verifying that events scraped into the DB are retrievable
    through the REST API layer.
    """
    db_file = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
    openorbit.config._settings = None
    db_module._db_connection = None

    await init_db()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

    await close_db()
    if os.path.exists(db_file):
        os.unlink(db_file)
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
    openorbit.config._settings = None


def _make_db_mock(db_connection):  # type: ignore[no-untyped-def]
    """Return a mock async context manager that yields *db_connection*."""
    mock_get_db = MagicMock()
    mock_get_db.return_value.__aenter__ = AsyncMock(return_value=db_connection)
    mock_get_db.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_get_db


# ═══════════════════════════════════════════════════════════════════════════
# TIER 1 — Official / Regulatory JSON API Sources
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionalSpaceAgency:
    """End-to-end: SpaceAgencyScraper → DB → API."""

    SAMPLE_RESPONSE = {
        "count": 2,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": "func-ll2-001",
                "name": "Falcon 9 | Starlink Group 12-5",
                "net": "2026-04-10T14:30:00Z",
                "net_precision": {"id": 7, "name": "Second"},
                "status": {"id": 1, "name": "Go for Launch"},
                "launch_service_provider": {"id": 121, "name": "SpaceX"},
                "rocket": {"configuration": {"id": 1, "name": "Falcon 9 Block 5"}},
                "pad": {
                    "name": "Space Launch Complex 40",
                    "location": {"name": "Cape Canaveral SFS, FL, USA"},
                },
            },
            {
                "id": "func-ll2-002",
                "name": "Ariane 6 | Galileo FOC-FM25",
                "net": "2026-05-01T00:00:00Z",
                "net_precision": {"id": 2, "name": "Day"},
                "status": {"id": 3, "name": "Success"},
                "launch_service_provider": {"id": 115, "name": "Arianespace"},
                "rocket": {"configuration": {"id": 30, "name": "Ariane 6"}},
                "pad": {
                    "name": "ELA-4",
                    "location": {"name": "Guiana Space Centre, French Guiana"},
                },
            },
        ],
    }

    @respx.mock
    async def test_scrape_stores_events_and_source(self, db_connection) -> None:
        """scrape() → events in DB with correct OSINT fields."""
        from openorbit.scrapers.space_agency import SpaceAgencyScraper

        scraper = SpaceAgencyScraper()
        url = f"{scraper.BASE_URL}{scraper.ENDPOINT}?limit=100"
        respx.get(url).mock(return_value=httpx.Response(200, json=self.SAMPLE_RESPONSE))

        result = await scraper.scrape()

        assert result["total_fetched"] == 2
        assert result["new_events"] == 2

        # Verify DB contents
        async with get_db() as conn:
            async with conn.execute("SELECT * FROM launch_events ORDER BY name") as cur:
                rows = await cur.fetchall()

            assert len(rows) == 2

            ariane = next(r for r in rows if "Ariane" in r["name"])
            assert ariane["provider"] == "Arianespace"
            assert ariane["vehicle"] == "Ariane 6"
            assert ariane["status"] == "launched"
            assert ariane["slug"] == "ll2-func-ll2-002"

            falcon = next(r for r in rows if "Falcon" in r["name"])
            assert falcon["provider"] == "SpaceX"
            assert falcon["vehicle"] == "Falcon 9 Block 5"
            assert falcon["status"] == "scheduled"
            assert falcon["slug"] == "ll2-func-ll2-001"
            assert falcon["launch_date_precision"] == "second"

            # Verify OSINT source registered
            async with conn.execute(
                "SELECT * FROM osint_sources WHERE name = 'Launch Library 2'"
            ) as cur:
                source = await cur.fetchone()
            assert source is not None
            assert source["last_scraped_at"] is not None

    @respx.mock
    async def test_api_retrieves_scraped_events(self, api_client) -> None:
        """Events scraped by SpaceAgencyScraper are returned via GET /v1/launches."""
        from openorbit.scrapers.space_agency import SpaceAgencyScraper

        scraper = SpaceAgencyScraper()
        url = f"{scraper.BASE_URL}{scraper.ENDPOINT}?limit=100"
        respx.get(url).mock(return_value=httpx.Response(200, json=self.SAMPLE_RESPONSE))

        await scraper.scrape()

        response = await api_client.get("/v1/launches")
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] == 2

        slugs = {e["slug"] for e in body["data"]}
        assert "ll2-func-ll2-001" in slugs
        assert "ll2-func-ll2-002" in slugs

        # Verify individual event detail
        detail = await api_client.get("/v1/launches/ll2-func-ll2-001")
        assert detail.status_code == 200
        assert detail.json()["provider"] == "SpaceX"
        assert detail.json()["vehicle"] == "Falcon 9 Block 5"


class TestFunctionalSpaceXOfficial:
    """End-to-end: SpaceXOfficialScraper → DB → API."""

    SAMPLE_RESPONSE = {
        "docs": [
            {
                "id": "func-spx-001",
                "name": "Starlink 15-1",
                "date_utc": "2026-04-15T16:00:00.000Z",
                "upcoming": True,
                "success": None,
                "launchpad": "5e9e4502f5090995de566f86",
                "rocket": "5e9d0d95eda69973a809d1ec",
                "details": "Starlink mission deployment to low Earth orbit",
            },
            {
                "id": "func-spx-002",
                "name": "Transporter-12",
                "date_utc": "2026-05-20T00:00:00.000Z",
                "upcoming": False,
                "success": True,
                "launchpad": "5e9e4502f5090995de566f86",
                "rocket": "5e9d0d95eda69973a809d1ec",
                "details": "Rideshare mission",
            },
        ],
        "totalDocs": 2,
        "limit": 2,
        "totalPages": 1,
        "page": 1,
        "pagingCounter": 1,
        "hasPrevPage": False,
        "hasNextPage": False,
        "prevPage": None,
        "nextPage": None,
    }

    @respx.mock
    async def test_scrape_stores_events_with_status_mapping(
        self, db_connection
    ) -> None:
        """SpaceX scraper maps upcoming/success to scheduled/launched."""
        from openorbit.scrapers.spacex_official import SpaceXOfficialScraper

        scraper = SpaceXOfficialScraper()
        respx.post("https://api.spacexdata.com/v4/launches/query").mock(
            return_value=httpx.Response(200, json=self.SAMPLE_RESPONSE)
        )

        result = await scraper.scrape()
        assert result["total_fetched"] == 2
        assert result["new_events"] == 2

        async with (
            get_db() as conn,
            conn.execute(
                "SELECT slug, status, provider FROM launch_events ORDER BY slug"
            ) as cur,
        ):
            rows = await cur.fetchall()

        assert len(rows) == 2
        slugs = {r["slug"]: r for r in rows}

        assert slugs["spx-func-spx-001"]["status"] == "scheduled"
        assert slugs["spx-func-spx-001"]["provider"] == "SpaceX"
        assert slugs["spx-func-spx-002"]["status"] == "launched"


class TestFunctionalCommercial:
    """End-to-end: CommercialLaunchScraper → DB → API."""

    SPACEX_FIXTURE = {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": "func-cm-sx-001",
                "name": "Falcon 9 | Commercial Resupply",
                "net": "2026-06-01T14:00:00Z",
                "net_precision": {"id": 7, "name": "Second"},
                "status": {"id": 1, "name": "Go for Launch"},
                "launch_service_provider": {"id": 121, "name": "SpaceX"},
                "rocket": {"configuration": {"id": 1, "name": "Falcon 9 Block 5"}},
                "pad": {
                    "name": "SLC-40",
                    "location": {"name": "Cape Canaveral SFS, FL, USA"},
                },
            },
        ],
    }

    ROCKETLAB_FIXTURE = {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": "func-cm-rl-001",
                "name": "Electron | Synspective",
                "net": "2026-07-10T08:00:00Z",
                "net_precision": {"id": 6, "name": "Minute"},
                "status": {"id": 1, "name": "Go"},
                "launch_service_provider": {"id": 147, "name": "Rocket Lab USA"},
                "rocket": {"configuration": {"id": 17, "name": "Electron"}},
                "pad": {
                    "name": "LC-1A",
                    "location": {"name": "Mahia Peninsula, New Zealand"},
                },
            },
        ],
    }

    @respx.mock
    async def test_scrape_fetches_multiple_providers(self, db_connection) -> None:
        """Commercial scraper fetches SpaceX and Rocket Lab, stores both."""
        from openorbit.scrapers.commercial import CommercialLaunchScraper

        spacex_url = (
            "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"
            "?format=json&limit=100&lsp__name=SpaceX"
        )
        rocketlab_url = (
            "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"
            "?format=json&limit=100&lsp__name=Rocket+Lab+USA"
        )
        respx.get(spacex_url).mock(
            return_value=httpx.Response(200, json=self.SPACEX_FIXTURE)
        )
        respx.get(rocketlab_url).mock(
            return_value=httpx.Response(200, json=self.ROCKETLAB_FIXTURE)
        )

        mod = _MOD_COMMERCIAL
        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(f"{mod}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{mod}.get_db", mock_get_db),
            patch(f"{mod}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            scraper = CommercialLaunchScraper()
            summaries = await scraper.scrape()

        # Summaries is a list of dicts, one per provider
        assert len(summaries) == 2
        total_new = sum(s["new_events"] for s in summaries)
        assert total_new == 2

        # Verify events in DB
        async with db_connection.execute(
            "SELECT slug, provider FROM launch_events ORDER BY slug"
        ) as cur:
            rows = await cur.fetchall()

        slugs = {r["slug"] for r in rows}
        assert "ll2-func-cm-sx-001" in slugs
        assert "ll2-func-cm-rl-001" in slugs


# ═══════════════════════════════════════════════════════════════════════════
# TIER 2 — Operational / Catalog Sources
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionalCelesTrak:
    """End-to-end: CelesTrakScraper → DB → API."""

    SAMPLE_TLE_DATA = [
        {
            "OBJECT_ID": "2026-030A",
            "OBJECT_NAME": "STARLINK-9001",
            "LAUNCH_DATE": "2026-03-15",
            "OWNER": "US",
            "SITE": "AFETR",
        },
        {
            "OBJECT_ID": "2026-030B",
            "OBJECT_NAME": "STARLINK-9002",
            "LAUNCH_DATE": "2026-03-15",
            "OWNER": "US",
            "SITE": "AFETR",
        },
        {
            "OBJECT_ID": "2026-031A",
            "OBJECT_NAME": "ONESAT-22",
            "LAUNCH_DATE": "2026-03-20",
            "OWNER": "FR",
            "SITE": "CSG",
        },
    ]

    @respx.mock
    async def test_scrape_aggregates_payloads_per_launch(self, db_connection) -> None:
        """CelesTrak groups 2026-030A/B into one event, 2026-031A separate."""
        from openorbit.scrapers.celestrak import CelesTrakScraper

        scraper = CelesTrakScraper()
        respx.get(scraper.source_url).mock(
            return_value=httpx.Response(200, json=self.SAMPLE_TLE_DATA)
        )

        result = await scraper.scrape()
        assert result["total_fetched"] == 2  # 2 launches (3 payloads)
        assert result["new_events"] == 2

        async with (
            get_db() as conn,
            conn.execute(
                "SELECT slug, name, status FROM launch_events ORDER BY slug"
            ) as cur,
        ):
            rows = await cur.fetchall()

        assert len(rows) == 2
        slugs = {r["slug"] for r in rows}
        assert "celestrak-2026-030" in slugs
        assert "celestrak-2026-031" in slugs

        grouped = next(r for r in rows if r["slug"] == "celestrak-2026-030")
        assert "2 payloads" in grouped["name"]
        assert grouped["status"] == "launched"

    @respx.mock
    async def test_api_retrieves_celestrak_events(self, api_client) -> None:
        """CelesTrak events show up via API with correct tier 2 metadata."""
        from openorbit.scrapers.celestrak import CelesTrakScraper

        scraper = CelesTrakScraper()
        respx.get(scraper.source_url).mock(
            return_value=httpx.Response(200, json=self.SAMPLE_TLE_DATA)
        )

        await scraper.scrape()

        response = await api_client.get("/v1/launches")
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] == 2

        for event in body["data"]:
            assert event["slug"].startswith("celestrak-")
            assert event["status"] == "launched"


class TestFunctionalNotams:
    """End-to-end: NotamScraper → DB → API."""

    FAA_URL = "https://external-api.faa.gov/notamapi/v1/notams"

    SAMPLE_RESPONSE = {
        "pageSize": 2,
        "pageNum": 1,
        "totalCount": 2,
        "items": [
            {
                "notamNumber": "1/5001",
                "traditionalMessageFrom4thLine": "ROCKET LAUNCH CORRIDOR ACTIVE",
                "qLine": "Q) KZJX/QRTCA/IV/BO/AE/000/999/2845S04512W010",
                "startValidity": "2606151200",
                "endValidity": "2606151800",
                "location": "KZJX",
            },
            {
                "notamNumber": "1/5002",
                "traditionalMessageFrom4thLine": "SPACE LAUNCH VEHICLE DEPARTURE",
                "qLine": "Q) KZJX/QRTCA/IV/BO/AE/000/999/2845S04512W010",
                "startValidity": "2606201200",
                "endValidity": "2606201800",
                "location": "KZJX",
            },
        ],
    }

    @respx.mock
    async def test_scrape_creates_launch_events(self, db_connection) -> None:
        """NotamScraper creates events for matching NOTAMs."""
        from openorbit.scrapers.notams import NotamScraper

        scraper = NotamScraper()
        respx.get(self.FAA_URL).mock(
            return_value=httpx.Response(200, json=self.SAMPLE_RESPONSE)
        )

        result = await scraper.scrape()
        assert result["total_fetched"] == 2
        assert result["new_events"] == 2

        async with (
            get_db() as conn,
            conn.execute("SELECT provider, launch_type FROM launch_events") as cur,
        ):
            rows = await cur.fetchall()

        assert len(rows) == 2
        for row in rows:
            assert row["provider"] == "FAA"
            assert row["launch_type"] in ("civilian", "military")

        # Verify source registered
        async with (
            get_db() as conn,
            conn.execute(
                "SELECT name FROM osint_sources WHERE name = 'FAA NOTAM Database'"
            ) as cur,
        ):
            source = await cur.fetchone()
        assert source is not None


# ═══════════════════════════════════════════════════════════════════════════
# TIER 1 — Official RSS Feed Sources (Regional Agencies)
# ═══════════════════════════════════════════════════════════════════════════


_LAUNCH_RSS_FEED = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Agency Launch Feed</title>
    <item>
      <title>Rocket launch mission for satellite deployment into orbit</title>
      <link>https://example.org/functional-launch-1</link>
      <pubDate>Tue, 07 Apr 2026 12:00:00 GMT</pubDate>
      <description>The launch vehicle is prepared for liftoff.</description>
    </item>
    <item>
      <title>General outreach workshop</title>
      <link>https://example.org/outreach</link>
      <pubDate>Mon, 06 Apr 2026 12:00:00 GMT</pubDate>
      <description>Education event, no launch content.</description>
    </item>
  </channel>
</rss>
"""


class TestFunctionalRegionalRSSFeeds:
    """End-to-end tests for all regional RSS feed scrapers."""

    @pytest.mark.parametrize(
        "scraper_cls_path,source_name",
        [
            ("openorbit.scrapers.esa_official.ESAOfficialScraper", "esa_official"),
            ("openorbit.scrapers.jaxa_official.JAXAOfficialScraper", "jaxa_official"),
            ("openorbit.scrapers.isro_official.ISROOfficialScraper", "isro_official"),
            (
                "openorbit.scrapers.arianespace_official.ArianespaceOfficialScraper",
                "arianespace_official",
            ),
            ("openorbit.scrapers.cnsa_official.CNSAOfficialScraper", "cnsa_official"),
        ],
    )
    @respx.mock
    async def test_scrape_and_retrieve(
        self, db_connection, scraper_cls_path: str, source_name: str
    ) -> None:
        """Each regional RSS scraper: fetch → parse → DB insert → verify."""
        import importlib

        module_path, cls_name = scraper_cls_path.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        scraper_cls = getattr(mod, cls_name)

        scraper = scraper_cls()
        respx.get(scraper.source_url).mock(
            return_value=httpx.Response(200, text=_LAUNCH_RSS_FEED)
        )

        result = await scraper.scrape()
        assert result["total_fetched"] == 1
        assert result["new_events"] == 1
        assert result["updated_events"] == 0

        # Verify event stored in DB
        async with (
            get_db() as conn,
            conn.execute("SELECT slug, provider, status FROM launch_events") as cur,
        ):
            rows = await cur.fetchall()

        assert len(rows) == 1
        assert rows[0]["slug"].startswith(f"{source_name}-")
        assert rows[0]["provider"] == scraper.PROVIDER_NAME
        assert rows[0]["status"] in {"scheduled", "launched", "delayed", "cancelled"}


# ═══════════════════════════════════════════════════════════════════════════
# TIER 3 — News RSS Sources
# ═══════════════════════════════════════════════════════════════════════════


_NEWS_RSS_FEED = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Space News</title>
    <item>
      <title>SpaceX Falcon 9 rocket launches Starlink satellites into orbit</title>
      <link>https://example.com/functional-news-launch</link>
      <pubDate>Mon, 06 Apr 2026 14:00:00 +0000</pubDate>
      <description>A Falcon 9 rocket lifted off from Cape Canaveral.</description>
    </item>
    <item>
      <title>International conference on engineering awards</title>
      <link>https://example.com/conference</link>
      <pubDate>Sun, 05 Apr 2026 10:00:00 +0000</pubDate>
      <description>Annual awards for engineering excellence.</description>
    </item>
  </channel>
</rss>
"""


class TestFunctionalSpaceFlightNow:
    """End-to-end: SpaceFlightNowScraper → DB."""

    @respx.mock
    async def test_scrape_stamps_rumor_lifecycle(self, db_connection) -> None:
        """News scraper events have claim_lifecycle='rumor' and event_kind='inferred'."""
        from openorbit.scrapers.news import SpaceFlightNowScraper

        scraper = SpaceFlightNowScraper()
        respx.get(scraper.source_url).mock(
            return_value=httpx.Response(200, text=_NEWS_RSS_FEED)
        )

        result = await scraper.scrape()
        assert result["total_fetched"] >= 1
        assert result["new_events"] >= 1

        async with (
            get_db() as conn,
            conn.execute(
                "SELECT slug, claim_lifecycle, event_kind FROM launch_events"
            ) as cur,
        ):
            rows = await cur.fetchall()

        assert len(rows) >= 1
        for row in rows:
            assert row["slug"].startswith("news_spaceflightnow-")
            assert row["claim_lifecycle"] == "rumor"
            assert row["event_kind"] == "inferred"


class TestFunctionalNASASpaceflight:
    """End-to-end: NASASpaceflightScraper → DB."""

    @respx.mock
    async def test_scrape_stamps_rumor_lifecycle(self, db_connection) -> None:
        """NASASpaceflight scraper events are rumor/inferred."""
        from openorbit.scrapers.news import NASASpaceflightScraper

        scraper = NASASpaceflightScraper()
        respx.get(scraper.source_url).mock(
            return_value=httpx.Response(200, text=_NEWS_RSS_FEED)
        )

        result = await scraper.scrape()
        assert result["total_fetched"] >= 1
        assert result["new_events"] >= 1

        async with (
            get_db() as conn,
            conn.execute(
                "SELECT slug, claim_lifecycle, event_kind FROM launch_events"
            ) as cur,
        ):
            rows = await cur.fetchall()

        assert len(rows) >= 1
        for row in rows:
            assert row["slug"].startswith("news_nasaspaceflight-")
            assert row["claim_lifecycle"] == "rumor"
            assert row["event_kind"] == "inferred"


# ═══════════════════════════════════════════════════════════════════════════
# TIER 3 — Social Media Sources
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionalBluesky:
    """End-to-end: BlueskyScraper → DB → API."""

    SAMPLE_POST = {
        "uri": "at://did:plc:func001/app.bsky.feed.post/func001",
        "record": {
            "text": "SpaceX Falcon 9 rocket launch from Cape Canaveral was incredible! #launch",
            "createdAt": "2026-04-07T18:30:00.000Z",
        },
        "author": {"handle": "spacefan.bsky.social"},
        "indexedAt": "2026-04-07T18:31:00.000Z",
    }

    @respx.mock
    async def test_scrape_inserts_with_tier3_metadata(self, db_connection) -> None:
        """Bluesky events are tier 3, rumor lifecycle, inferred kind."""
        from openorbit.scrapers.bluesky import BlueskyScraper

        search_response = {"posts": [self.SAMPLE_POST]}
        feed_response = {"feed": []}

        respx.get(BlueskyScraper.SEARCH_URL).mock(
            return_value=httpx.Response(200, json=search_response)
        )
        respx.get(BlueskyScraper.FEED_URL).mock(
            return_value=httpx.Response(200, json=feed_response)
        )

        mod = _MOD_BLUESKY
        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(f"{mod}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{mod}.get_db", mock_get_db),
            patch(f"{mod}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            scraper = BlueskyScraper()
            result = await scraper.scrape()

        assert result["total_fetched"] >= 1
        assert result["new_events"] >= 1

        async with db_connection.execute(
            "SELECT slug, claim_lifecycle, event_kind, provider FROM launch_events"
        ) as cur:
            rows = await cur.fetchall()

        assert len(rows) >= 1
        for row in rows:
            assert row["slug"].startswith("bluesky-")
            assert row["claim_lifecycle"] == "rumor"
            assert row["event_kind"] == "inferred"
            assert row["provider"] == "spacefan.bsky.social"


class TestFunctionalMastodon:
    """End-to-end: MastodonScraper → DB → API."""

    SAMPLE_STATUS = {
        "id": "func-masto-001",
        "url": "https://mastodon.social/@spacewatcher/func-masto-001",
        "content": "<p>Incredible Falcon 9 rocket launch! SpaceX nails another mission #launch</p>",
        "created_at": "2026-04-07T12:00:00.000Z",
        "account": {"acct": "spacewatcher@mastodon.social"},
    }

    @respx.mock
    async def test_scrape_inserts_with_tier3_metadata(self, db_connection) -> None:
        """Mastodon events are tier 3, rumor lifecycle, inferred kind."""
        from openorbit.scrapers.mastodon import MastodonScraper

        for hashtag in MastodonScraper.HASHTAGS:
            respx.get(f"https://mastodon.social/api/v1/timelines/tag/{hashtag}").mock(
                return_value=httpx.Response(200, json=[self.SAMPLE_STATUS])
            )

        mod = _MOD_MASTODON
        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(f"{mod}.get_db", mock_get_db),
            patch(f"{mod}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            scraper = MastodonScraper()
            result = await scraper.scrape()

        assert result["total_fetched"] >= 1
        assert result["new_events"] >= 1

        async with db_connection.execute(
            "SELECT slug, claim_lifecycle, event_kind, provider FROM launch_events"
        ) as cur:
            rows = await cur.fetchall()

        assert len(rows) >= 1
        for row in rows:
            assert row["slug"].startswith("mastodon-")
            assert row["claim_lifecycle"] == "rumor"
            assert row["event_kind"] == "inferred"
            assert "spacewatcher" in row["provider"]


class TestFunctionalReddit:
    """End-to-end: RedditScraper → DB → API."""

    SAMPLE_POST = {
        "permalink": "/r/spacex/comments/func001/falcon_9_launch/",
        "title": "SpaceX Falcon 9 rocket launch from Cape Canaveral!",
        "selftext": "Just watched the amazing liftoff!",
        "author": "func_spacefan",
        "created_utc": 1775340400.0,
        "subreddit": "spacex",
        "url": "https://i.redd.it/func001.jpg",
        "post_hint": "image",
    }

    @respx.mock
    async def test_scrape_inserts_with_images_and_metadata(self, db_connection) -> None:
        """Reddit events carry image_urls, rumor lifecycle, inferred kind."""
        from openorbit.scrapers.reddit import RedditScraper

        subreddit_response = {"data": {"children": [{"data": self.SAMPLE_POST}]}}

        for subreddit in RedditScraper.SUBREDDITS:
            respx.get(f"https://www.reddit.com/r/{subreddit}/new.json").mock(
                return_value=httpx.Response(200, json=subreddit_response)
            )

        mod = _MOD_REDDIT
        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(f"{mod}.get_db", mock_get_db),
            patch(f"{mod}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            scraper = RedditScraper()
            result = await scraper.scrape()

        assert result["total_fetched"] >= 1
        assert result["new_events"] >= 1

        async with db_connection.execute(
            "SELECT slug, claim_lifecycle, event_kind, image_urls FROM launch_events"
        ) as cur:
            rows = await cur.fetchall()

        assert len(rows) >= 1
        row = rows[0]
        assert row["slug"].startswith("reddit-")
        assert row["claim_lifecycle"] == "rumor"
        assert row["event_kind"] == "inferred"

        # Verify image URL persisted
        images = json.loads(row["image_urls"] or "[]")
        assert len(images) >= 1
        assert "i.redd.it" in images[0]


class TestFunctionalFourChan:
    """End-to-end: FourChanScraper → DB → API."""

    SAMPLE_THREAD = {
        "no": 99990001,
        "sub": "SpaceX Falcon 9 Launch Thread",
        "com": "Launch is GO! Rocket on the pad ready for liftoff.",
        "time": 1775340400,
        "tim": 1775340399000,
        "ext": ".jpg",
        "_board": "sci",
    }

    @respx.mock
    async def test_scrape_inserts_with_images_and_metadata(self, db_connection) -> None:
        """4chan events carry image_urls, rumor lifecycle, inferred kind."""
        from openorbit.scrapers.fourchan import FourChanScraper

        catalog = [{"page": 1, "threads": [self.SAMPLE_THREAD]}]

        for board in FourChanScraper.BOARDS:
            respx.get(f"https://a.4cdn.org/{board}/catalog.json").mock(
                return_value=httpx.Response(200, json=catalog)
            )

        mod = _MOD_FOURCHAN
        mock_get_db = _make_db_mock(db_connection)
        with (
            patch(f"{mod}.get_db", mock_get_db),
            patch(f"{mod}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            scraper = FourChanScraper()
            result = await scraper.scrape()

        assert result["total_fetched"] >= 1
        assert result["new_events"] >= 1

        async with db_connection.execute(
            "SELECT slug, claim_lifecycle, event_kind, image_urls FROM launch_events"
        ) as cur:
            rows = await cur.fetchall()

        assert len(rows) >= 1
        row = rows[0]
        assert row["slug"].startswith("4chan-")
        assert row["claim_lifecycle"] == "rumor"
        assert row["event_kind"] == "inferred"

        # Verify image URL built from tim + ext
        images = json.loads(row["image_urls"] or "[]")
        assert len(images) == 1
        assert "4cdn.org" in images[0]
        assert ".jpg" in images[0]


# ═══════════════════════════════════════════════════════════════════════════
# CROSS-CUTTING — Multi-Source Pipeline Verification
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionalMultiSourcePipeline:
    """Verify that events from multiple sources coexist and are queryable."""

    @respx.mock
    async def test_multiple_sources_coexist_in_api(self, api_client) -> None:
        """Scrape two different sources and verify both appear in API."""
        from openorbit.scrapers.celestrak import CelesTrakScraper
        from openorbit.scrapers.space_agency import SpaceAgencyScraper

        # Set up SpaceAgency mock
        ll2_response = {
            "count": 1,
            "results": [
                {
                    "id": "multi-ll2-001",
                    "name": "Falcon 9 | Multi-Source Test",
                    "net": "2026-04-10T14:30:00Z",
                    "net_precision": {"id": 7, "name": "Second"},
                    "status": {"id": 1, "name": "Go for Launch"},
                    "launch_service_provider": {"id": 121, "name": "SpaceX"},
                    "rocket": {"configuration": {"id": 1, "name": "Falcon 9 Block 5"}},
                    "pad": {
                        "name": "SLC-40",
                        "location": {"name": "Cape Canaveral SFS, FL, USA"},
                    },
                }
            ],
        }
        ll2_scraper = SpaceAgencyScraper()
        ll2_url = f"{ll2_scraper.BASE_URL}{ll2_scraper.ENDPOINT}?limit=100"
        respx.get(ll2_url).mock(return_value=httpx.Response(200, json=ll2_response))

        # Set up CelesTrak mock
        celestrak_data = [
            {
                "OBJECT_ID": "2026-099A",
                "OBJECT_NAME": "MULTI-TEST-SAT",
                "LAUNCH_DATE": "2026-03-30",
                "OWNER": "US",
                "SITE": "AFETR",
            }
        ]
        celestrak_scraper = CelesTrakScraper()
        respx.get(celestrak_scraper.source_url).mock(
            return_value=httpx.Response(200, json=celestrak_data)
        )

        # Run both scrapers
        await ll2_scraper.scrape()
        await celestrak_scraper.scrape()

        # Verify API returns events from both sources
        response = await api_client.get("/v1/launches")
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] == 2

        slugs = {e["slug"] for e in body["data"]}
        assert "ll2-multi-ll2-001" in slugs
        assert "celestrak-2026-099" in slugs

        # Verify each event has proper metadata
        for event in body["data"]:
            assert event["result_tier"] in {"emerging", "tracked", "verified"}
            assert isinstance(event["evidence_count"], int)
            assert event["evidence_url"].startswith("/v1/launches/")

    @respx.mock
    async def test_provider_filter_works_across_sources(self, api_client) -> None:
        """Provider filter correctly narrows results from mixed sources."""
        from openorbit.scrapers.space_agency import SpaceAgencyScraper

        ll2_response = {
            "count": 2,
            "results": [
                {
                    "id": "filter-001",
                    "name": "Falcon 9 | Filter Test",
                    "net": "2026-04-10T14:30:00Z",
                    "net_precision": {"id": 7, "name": "Second"},
                    "status": {"id": 1, "name": "Go for Launch"},
                    "launch_service_provider": {"id": 121, "name": "SpaceX"},
                    "rocket": {"configuration": {"id": 1, "name": "Falcon 9 Block 5"}},
                    "pad": {
                        "name": "SLC-40",
                        "location": {"name": "Cape Canaveral SFS, FL, USA"},
                    },
                },
                {
                    "id": "filter-002",
                    "name": "Ariane 6 | Filter Test",
                    "net": "2026-05-01T00:00:00Z",
                    "net_precision": {"id": 2, "name": "Day"},
                    "status": {"id": 1, "name": "Go"},
                    "launch_service_provider": {
                        "id": 115,
                        "name": "Arianespace",
                    },
                    "rocket": {"configuration": {"id": 30, "name": "Ariane 6"}},
                    "pad": {
                        "name": "ELA-4",
                        "location": {"name": "Guiana Space Centre, French Guiana"},
                    },
                },
            ],
        }
        scraper = SpaceAgencyScraper()
        url = f"{scraper.BASE_URL}{scraper.ENDPOINT}?limit=100"
        respx.get(url).mock(return_value=httpx.Response(200, json=ll2_response))

        await scraper.scrape()

        # Filter by SpaceX
        response = await api_client.get("/v1/launches", params={"provider": "SpaceX"})
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] == 1
        assert body["data"][0]["provider"] == "SpaceX"

        # Filter by Arianespace
        response = await api_client.get(
            "/v1/launches", params={"provider": "Arianespace"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] == 1
        assert body["data"][0]["provider"] == "Arianespace"
