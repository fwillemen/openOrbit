"""Tests for CommercialLaunchScraper."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from openorbit.db import close_db, get_db, init_db
from openorbit.scrapers.commercial import CommercialLaunchScraper

# Shorthand for patching the commercial scraper module
_MOD = "openorbit.scrapers.commercial"

# Fixtures
# ---------------------------------------------------------------------------

SPACEX_FIXTURE: dict = {
    "count": 2,
    "next": None,
    "previous": None,
    "results": [
        {
            "id": "sx-001",
            "name": "Falcon 9 | Starlink Group 10-1",
            "net": "2025-06-01T14:00:00Z",
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
            "id": "sx-002",
            "name": "Falcon Heavy | USSF-67",
            "net": "2025-07-15T00:00:00Z",
            "net_precision": {"id": 2, "name": "Day"},
            "status": {"id": 2, "name": "TBD"},
            "launch_service_provider": {"id": 121, "name": "SpaceX"},
            "rocket": {"configuration": {"id": 2, "name": "Falcon Heavy"}},
            "pad": {
                "name": "LC-39A",
                "location": {"name": "Kennedy Space Center, FL, USA"},
            },
        },
    ],
}

ROCKETLAB_FIXTURE: dict = {
    "count": 2,
    "next": None,
    "previous": None,
    "results": [
        {
            "id": "rl-001",
            "name": "Electron | Finding Hot Rocks",
            "net": "2025-08-10T08:00:00Z",
            "net_precision": {"id": 6, "name": "Minute"},
            "status": {"id": 1, "name": "Go"},
            "launch_service_provider": {"id": 147, "name": "Rocket Lab USA"},
            "rocket": {"configuration": {"id": 17, "name": "Electron"}},
            "pad": {
                "name": "LC-1A",
                "location": {"name": "Mahia Peninsula, New Zealand"},
            },
        },
        {
            "id": "rl-002",
            "name": "Electron | NROL-199",
            "net": "2025-09-01T00:00:00Z",
            "net_precision": {"id": 1, "name": "Month"},
            "status": {"id": 4, "name": "TBC"},
            "launch_service_provider": {"id": 147, "name": "Rocket Lab USA"},
            "rocket": {"configuration": {"id": 17, "name": "Electron"}},
            "pad": {
                "name": "LC-2",
                "location": {"name": "Wallops Island, VA, USA"},
            },
        },
    ],
}


@pytest.fixture
async def db_connection():
    """Provide a fresh in-memory database connection for each test."""
    from openorbit import config

    config._settings = None
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    await init_db()
    async with get_db() as conn:
        yield conn

    await close_db()
    config._settings = None


# ---------------------------------------------------------------------------
# parse() unit tests (no HTTP, no DB)
# ---------------------------------------------------------------------------


class TestParsing:
    """Unit tests for CommercialLaunchScraper.parse()."""

    def test_parse_spacex_fixture_returns_two_events(self) -> None:
        """parse() with SpaceX fixture yields two LaunchEventCreate models."""
        scraper = CommercialLaunchScraper()
        events = scraper.parse(json.dumps(SPACEX_FIXTURE), "LL2 Commercial – SpaceX")
        assert len(events) == 2

    def test_parse_spacex_first_event_fields(self) -> None:
        """First SpaceX event has correct name, vehicle, location, status."""
        scraper = CommercialLaunchScraper()
        events = scraper.parse(json.dumps(SPACEX_FIXTURE), "LL2 Commercial – SpaceX")
        ev = events[0]
        assert "Falcon 9" in ev.name
        assert ev.vehicle == "Falcon 9 Block 5"
        assert ev.location == "Cape Canaveral SFS, FL, USA"
        assert ev.status == "scheduled"
        assert ev.launch_type == "civilian"
        assert ev.slug == "ll2-sx-001"

    def test_parse_spacex_precision_exact_maps_to_second(self) -> None:
        """LL2 'Second' precision maps to db precision 'second'."""
        scraper = CommercialLaunchScraper()
        events = scraper.parse(json.dumps(SPACEX_FIXTURE), "LL2 Commercial – SpaceX")
        assert events[0].launch_date_precision == "second"

    def test_parse_spacex_precision_day_maps_to_day(self) -> None:
        """LL2 'Day' precision maps to db precision 'day'."""
        scraper = CommercialLaunchScraper()
        events = scraper.parse(json.dumps(SPACEX_FIXTURE), "LL2 Commercial – SpaceX")
        assert events[1].launch_date_precision == "day"

    def test_parse_rocketlab_fixture_returns_two_events(self) -> None:
        """parse() with Rocket Lab fixture yields two LaunchEventCreate models."""
        scraper = CommercialLaunchScraper()
        events = scraper.parse(
            json.dumps(ROCKETLAB_FIXTURE), "LL2 Commercial – Rocket Lab"
        )
        assert len(events) == 2

    def test_parse_rocketlab_provider_name(self) -> None:
        """Rocket Lab provider name is preserved (or alias resolved) correctly."""
        scraper = CommercialLaunchScraper()
        events = scraper.parse(
            json.dumps(ROCKETLAB_FIXTURE), "LL2 Commercial – Rocket Lab"
        )
        # provider must be non-empty and contain "rocket"
        provider_lower = events[0].provider.lower()
        assert "rocket" in provider_lower

    def test_parse_rocketlab_month_precision(self) -> None:
        """LL2 'Month' precision maps to db precision 'month'."""
        scraper = CommercialLaunchScraper()
        events = scraper.parse(
            json.dumps(ROCKETLAB_FIXTURE), "LL2 Commercial – Rocket Lab"
        )
        assert events[1].launch_date_precision == "month"

    def test_parse_empty_results_returns_empty_list(self) -> None:
        """parse() with empty results list returns []."""
        scraper = CommercialLaunchScraper()
        events = scraper.parse(
            json.dumps({"count": 0, "results": []}),
            "LL2 Commercial – SpaceX",
        )
        assert events == []

    def test_parse_missing_results_key_returns_empty_list(self) -> None:
        """parse() with missing 'results' key returns []."""
        scraper = CommercialLaunchScraper()
        events = scraper.parse(json.dumps({"count": 0}), "LL2 Commercial – SpaceX")
        assert events == []

    def test_parse_invalid_json_raises_value_error(self) -> None:
        """parse() raises ValueError on invalid JSON."""
        scraper = CommercialLaunchScraper()
        with pytest.raises(ValueError, match="Invalid JSON"):
            scraper.parse("not json {{{", "LL2 Commercial – SpaceX")

    def test_parse_skips_malformed_event_no_net(self) -> None:
        """Malformed event without 'net' field is skipped; valid events returned."""
        malformed_data = {
            "count": 2,
            "results": [
                {
                    "id": "good-1",
                    "name": "Good Launch",
                    "net": "2025-10-01T12:00:00Z",
                    "net_precision": {"id": 2, "name": "Day"},
                    "status": {"id": 1, "name": "Go"},
                    "launch_service_provider": {"name": "SpaceX"},
                    "rocket": {"configuration": {"name": "Falcon 9"}},
                    "pad": {
                        "name": "SLC-40",
                        "location": {"name": "Cape Canaveral, FL, USA"},
                    },
                },
                {
                    "id": "bad-1",
                    "name": "Bad Launch",
                    # 'net' is missing — will cause NormalizationError
                    "net_precision": {"id": 2, "name": "Day"},
                    "status": {"id": 1, "name": "Go"},
                    "launch_service_provider": {"name": "SpaceX"},
                    "rocket": {"configuration": {"name": "Falcon 9"}},
                    "pad": {"name": "SLC-40", "location": {"name": "Cape Canaveral"}},
                },
            ],
        }
        scraper = CommercialLaunchScraper()
        events = scraper.parse(json.dumps(malformed_data), "LL2 Commercial – SpaceX")
        # Only the valid event should be returned
        assert len(events) == 1
        assert events[0].name == "Good Launch"

    def test_parse_does_not_crash_on_all_malformed(self) -> None:
        """parse() returns empty list (not exception) when all events are malformed."""
        all_bad = {
            "count": 1,
            "results": [{"id": "x", "name": "Bad", "status": {"name": "Go"}}],
        }
        scraper = CommercialLaunchScraper()
        events = scraper.parse(json.dumps(all_bad), "LL2 Commercial – SpaceX")
        assert events == []


# ---------------------------------------------------------------------------
# _map_ll2_to_raw() unit tests
# ---------------------------------------------------------------------------


class TestMapLl2ToRaw:
    """Unit tests for _map_ll2_to_raw."""

    def test_maps_all_expected_keys(self) -> None:
        """_map_ll2_to_raw returns dict with all required pipeline keys."""
        scraper = CommercialLaunchScraper()
        ll2 = SPACEX_FIXTURE["results"][0]
        raw = scraper._map_ll2_to_raw(ll2)
        for key in (
            "name",
            "launch_date",
            "launch_date_precision",
            "provider",
            "vehicle",
            "location",
            "pad",
            "launch_type",
            "status",
            "confidence_score",
        ):
            assert key in raw

    def test_success_status_maps_correctly(self) -> None:
        """'Success' LL2 status → 'success' pipeline status."""
        scraper = CommercialLaunchScraper()
        ll2 = {
            "id": "t1",
            "name": "X",
            "net": "2025-01-01T00:00:00Z",
            "net_precision": {"name": "Day"},
            "status": {"name": "Success"},
            "launch_service_provider": {"name": "SpaceX"},
            "rocket": {"configuration": {"name": "Falcon 9"}},
            "pad": {"name": "SLC-40", "location": {"name": "Cape"}},
        }
        raw = scraper._map_ll2_to_raw(ll2)
        assert raw["status"] == "success"

    def test_failure_status_maps_correctly(self) -> None:
        """'Failure' LL2 status → 'failure' pipeline status."""
        scraper = CommercialLaunchScraper()
        ll2 = dict(SPACEX_FIXTURE["results"][0])
        ll2["status"] = {"name": "Partial Failure"}
        raw = scraper._map_ll2_to_raw(ll2)
        assert raw["status"] == "failure"

    def test_confidence_score_is_0_7(self) -> None:
        """confidence_score is always 0.7 for commercial scraper."""
        scraper = CommercialLaunchScraper()
        raw = scraper._map_ll2_to_raw(SPACEX_FIXTURE["results"][0])
        assert raw["confidence_score"] == pytest.approx(0.7)

    def test_launch_type_is_civilian(self) -> None:
        """launch_type is always 'civilian'."""
        scraper = CommercialLaunchScraper()
        raw = scraper._map_ll2_to_raw(SPACEX_FIXTURE["results"][0])
        assert raw["launch_type"] == "civilian"


# ---------------------------------------------------------------------------
# HTTP + DB integration tests (mocked HTTP, real in-memory DB)
# ---------------------------------------------------------------------------


class TestScrapeIntegration:
    """Integration tests using respx to mock HTTP and a real in-memory DB."""

    def _make_db_mock(self, db_connection):  # type: ignore[no-untyped-def]
        """Return a mock async context manager that yields db_connection."""
        mock_get_db = MagicMock()
        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=db_connection)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=None)
        return mock_get_db

    @respx.mock
    async def test_scrape_spacex_calls_correct_url(self, db_connection) -> None:
        """scrape() requests the LL2 URL with lsp__name=SpaceX for SpaceX."""
        spacex_url = (
            "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"
            "?format=json&limit=100&lsp__name=SpaceX"
        )
        rocketlab_url = (
            "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"
            "?format=json&limit=100&lsp__name=Rocket+Lab+USA"
        )
        respx.get(spacex_url).mock(
            return_value=httpx.Response(200, json=SPACEX_FIXTURE)
        )
        respx.get(rocketlab_url).mock(
            return_value=httpx.Response(200, json={"count": 0, "results": []})
        )

        scraper = CommercialLaunchScraper()
        mock_get_db = self._make_db_mock(db_connection)
        with (
            patch(f"{_MOD}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            await scraper.scrape()

        assert respx.calls.call_count >= 1
        called_urls = [str(call.request.url) for call in respx.calls]
        assert any("lsp__name=SpaceX" in u for u in called_urls)

    @respx.mock
    async def test_scrape_rocketlab_calls_correct_url(self, db_connection) -> None:
        """scrape() requests the LL2 URL with lsp__name=Rocket+Lab+USA."""
        spacex_url = (
            "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"
            "?format=json&limit=100&lsp__name=SpaceX"
        )
        rocketlab_url = (
            "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"
            "?format=json&limit=100&lsp__name=Rocket+Lab+USA"
        )
        respx.get(spacex_url).mock(
            return_value=httpx.Response(200, json={"count": 0, "results": []})
        )
        respx.get(rocketlab_url).mock(
            return_value=httpx.Response(200, json=ROCKETLAB_FIXTURE)
        )

        scraper = CommercialLaunchScraper()
        mock_get_db = self._make_db_mock(db_connection)
        with (
            patch(f"{_MOD}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            await scraper.scrape()

        called_urls = [str(call.request.url) for call in respx.calls]
        assert any("Rocket+Lab+USA" in u for u in called_urls)

    @respx.mock
    async def test_http_error_returns_zero_summary(self, db_connection) -> None:
        """HTTP 503 for a provider causes that provider's summary to show 0 events."""
        spacex_url = (
            "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"
            "?format=json&limit=100&lsp__name=SpaceX"
        )
        rocketlab_url = (
            "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"
            "?format=json&limit=100&lsp__name=Rocket+Lab+USA"
        )
        respx.get(spacex_url).mock(return_value=httpx.Response(503))
        respx.get(rocketlab_url).mock(
            return_value=httpx.Response(200, json={"count": 0, "results": []})
        )

        scraper = CommercialLaunchScraper()
        scraper.settings.SCRAPER_MAX_RETRIES = 1  # type: ignore[assignment]
        mock_get_db = self._make_db_mock(db_connection)
        with (
            patch(f"{_MOD}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            summaries = await scraper.scrape()

        spacex_summary = next((s for s in summaries if s["provider"] == "SpaceX"), None)
        assert spacex_summary is not None
        assert spacex_summary["total_fetched"] == 0

    @respx.mock
    async def test_http_client_error_no_retry(self, db_connection) -> None:
        """HTTP 404 (4xx) is not retried; provider summary shows 0 events."""
        spacex_url = (
            "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"
            "?format=json&limit=100&lsp__name=SpaceX"
        )
        rocketlab_url = (
            "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"
            "?format=json&limit=100&lsp__name=Rocket+Lab+USA"
        )
        respx.get(spacex_url).mock(return_value=httpx.Response(404))
        respx.get(rocketlab_url).mock(
            return_value=httpx.Response(200, json={"count": 0, "results": []})
        )

        scraper = CommercialLaunchScraper()
        mock_get_db = self._make_db_mock(db_connection)
        with (
            patch(f"{_MOD}.asyncio.sleep", new_callable=AsyncMock),
            patch(f"{_MOD}.get_db", mock_get_db),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            summaries = await scraper.scrape()

        spacex_summary = next(s for s in summaries if s["provider"] == "SpaceX")
        assert spacex_summary["total_fetched"] == 0

    async def test_delay_between_providers_called(self) -> None:
        """asyncio.sleep is called once with SCRAPER_DELAY_SECONDS between providers."""
        scraper = CommercialLaunchScraper()

        async def fake_scrape_provider(conn, name, ll2_filter):  # type: ignore[no-untyped-def]
            return {
                "provider": name,
                "total_fetched": 0,
                "new_events": 0,
                "updated_events": 0,
            }

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(scraper, "_scrape_provider", side_effect=fake_scrape_provider),
            patch(f"{_MOD}.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch(f"{_MOD}.get_db", return_value=mock_ctx),
            patch(f"{_MOD}.init_db", new_callable=AsyncMock),
            patch("openorbit.db._db_connection", new=object(), create=True),
        ):
            await scraper.scrape()

        mock_sleep.assert_called_once_with(scraper.settings.SCRAPER_DELAY_SECONDS)
