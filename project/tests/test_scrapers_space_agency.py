"""Tests for space agency scraper using Launch Library 2 API."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from openorbit.db import close_db, get_db, init_db
from openorbit.scrapers.space_agency import SpaceAgencyScraper


@pytest.fixture
async def db_connection():
    """Initialize test database with cleanup."""
    # Override settings to use in-memory DB for tests
    from openorbit import config

    original_db_url = config._settings.DATABASE_URL if config._settings else None

    # Force a fresh settings instance with test DB
    config._settings = None
    import os

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    await init_db()
    async with get_db() as conn:
        yield conn

    await close_db()

    # Restore original settings
    if original_db_url:
        os.environ["DATABASE_URL"] = original_db_url
    config._settings = None


@pytest.fixture
def sample_ll2_response():
    """Sample Launch Library 2 API response with 3 launches."""
    return {
        "count": 3,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": "launch-1",
                "name": "Falcon 9 Block 5 | Starlink Group 7-1",
                "net": "2025-03-15T10:30:00Z",
                "net_precision": {"id": 7, "name": "Second"},
                "status": {"id": 1, "name": "Go for Launch"},
                "launch_service_provider": {
                    "id": 121,
                    "name": "SpaceX",
                },
                "rocket": {
                    "configuration": {
                        "id": 1,
                        "name": "Falcon 9 Block 5",
                    }
                },
                "pad": {
                    "name": "Space Launch Complex 40",
                    "location": {
                        "name": "Cape Canaveral SFS, FL, USA",
                    },
                },
            },
            {
                "id": "launch-2",
                "name": "Atlas V 551 | USSF-51",
                "net": "2025-04-10T00:00:00Z",
                "net_precision": {"id": 2, "name": "Day"},
                "status": {"id": 2, "name": "TBD"},
                "launch_service_provider": {
                    "id": 124,
                    "name": "United Launch Alliance",
                },
                "rocket": {
                    "configuration": {
                        "id": 2,
                        "name": "Atlas V 551",
                    }
                },
                "pad": {
                    "name": "SLC-41",
                    "location": {
                        "name": "Cape Canaveral SFS, FL, USA",
                    },
                },
            },
            {
                "id": "launch-3",
                "name": "Electron | Test Mission",
                "net": "2025-05-01T00:00:00Z",
                "net_precision": {"id": 1, "name": "Month"},
                "status": {"id": 3, "name": "Success"},
                "launch_service_provider": {
                    "id": 147,
                    "name": "Rocket Lab",
                },
                "rocket": {
                    "configuration": {
                        "id": 17,
                        "name": "Electron",
                    }
                },
                "pad": {
                    "name": "LC-1A",
                    "location": {
                        "name": "Mahia Peninsula, New Zealand",
                    },
                },
            },
        ],
    }


@pytest.fixture
def sample_malformed_response():
    """Sample response with some malformed records."""
    return {
        "count": 2,
        "results": [
            {
                "id": "valid-launch",
                "name": "Valid Launch",
                "net": "2025-06-01T12:00:00Z",
                "net_precision": {"id": 6, "name": "Minute"},
                "status": {"id": 1, "name": "Go"},
                "launch_service_provider": {"name": "NASA"},
                "rocket": {"configuration": {"name": "SLS"}},
                "pad": {
                    "name": "LC-39B",
                    "location": {"name": "Kennedy Space Center"},
                },
            },
            {
                "id": "malformed-launch",
                # Missing "name" field (required)
                "net": "2025-07-01T12:00:00Z",
            },
        ],
    }


class TestSpaceAgencyScraper:
    """Test suite for SpaceAgencyScraper."""

    async def test_parse_valid_response(self, sample_ll2_response):
        """Test parsing a valid LL2 API response."""
        scraper = SpaceAgencyScraper()
        events = await scraper.parse(json.dumps(sample_ll2_response))

        assert len(events) == 3

        # Verify first event (Falcon 9)
        event1 = events[0]
        assert event1.name == "Falcon 9 Block 5 | Starlink Group 7-1"
        assert event1.provider == "SpaceX"
        assert event1.vehicle == "Falcon 9 Block 5"
        assert event1.location == "Cape Canaveral SFS, FL, USA"
        assert event1.pad == "Space Launch Complex 40"
        assert event1.launch_date_precision == "second"
        assert event1.status == "scheduled"
        assert event1.launch_type == "civilian"
        assert event1.launch_date.tzinfo is not None  # Must be timezone-aware

        # Verify second event (Atlas V)
        event2 = events[1]
        assert event2.name == "Atlas V 551 | USSF-51"
        assert event2.provider == "United Launch Alliance"
        assert event2.launch_date_precision == "day"
        assert event2.status == "scheduled"

        # Verify third event (Electron)
        event3 = events[2]
        assert event3.name == "Electron | Test Mission"
        assert event3.provider == "Rocket Lab"
        assert event3.launch_date_precision == "month"
        assert event3.status == "launched"  # "Success" maps to "launched"

    async def test_parse_empty_results(self):
        """Test parsing response with no results."""
        scraper = SpaceAgencyScraper()
        empty_response = {"count": 0, "results": []}
        events = await scraper.parse(json.dumps(empty_response))

        assert len(events) == 0

    async def test_parse_missing_results_key(self):
        """Test parsing response without 'results' key."""
        scraper = SpaceAgencyScraper()
        invalid_response = {"count": 0}
        events = await scraper.parse(json.dumps(invalid_response))

        assert len(events) == 0

    async def test_parse_invalid_json(self):
        """Test parsing invalid JSON raises ValueError."""
        scraper = SpaceAgencyScraper()

        with pytest.raises(ValueError, match="Invalid JSON"):
            await scraper.parse("not valid json {")

    async def test_parse_malformed_records(self, sample_malformed_response):
        """Test parsing skips malformed records but keeps valid ones."""
        scraper = SpaceAgencyScraper()
        events = await scraper.parse(json.dumps(sample_malformed_response))

        # Should only get 1 valid event (malformed one is skipped)
        assert len(events) == 1
        assert events[0].name == "Valid Launch"
        assert events[0].provider == "NASA"

    async def test_status_mapping(self):
        """Test all status mappings from LL2 to our enum."""
        scraper = SpaceAgencyScraper()

        test_cases = [
            ("Go for Launch", "scheduled"),
            ("Go", "scheduled"),
            ("TBD", "scheduled"),
            ("TBC", "scheduled"),
            ("Success", "launched"),
            ("Failure", "failed"),
            ("Partial Failure", "failed"),
            ("In Flight", "launched"),
            ("Hold", "delayed"),
            ("Unknown Status", "scheduled"),  # Default fallback
        ]

        for ll2_status, expected_status in test_cases:
            response = {
                "results": [
                    {
                        "name": "Test Launch",
                        "net": "2025-01-01T00:00:00Z",
                        "net_precision": {"id": 3},
                        "status": {"name": ll2_status},
                        "launch_service_provider": {"name": "Test Provider"},
                        "rocket": {"configuration": {"name": "Test Rocket"}},
                        "pad": {
                            "name": "Test Pad",
                            "location": {"name": "Test Location"},
                        },
                    }
                ]
            }

            events = await scraper.parse(json.dumps(response))
            assert len(events) == 1
            assert events[0].status == expected_status

    async def test_precision_mapping(self):
        """Test all precision level mappings (0-7)."""
        scraper = SpaceAgencyScraper()

        precision_mappings = {
            0: "year",
            1: "month",
            2: "day",
            3: "day",
            4: "hour",
            5: "hour",
            6: "minute",
            7: "second",
        }

        for ll2_precision, expected_precision in precision_mappings.items():
            response = {
                "results": [
                    {
                        "name": f"Launch Precision {ll2_precision}",
                        "net": "2025-03-15T10:30:45Z",
                        "net_precision": {"id": ll2_precision},
                        "status": {"name": "Go"},
                        "launch_service_provider": {"name": "Provider"},
                        "rocket": {"configuration": {"name": "Rocket"}},
                        "pad": {
                            "name": "Pad",
                            "location": {"name": "Location"},
                        },
                    }
                ]
            }

            events = await scraper.parse(json.dumps(response))
            assert len(events) == 1
            assert events[0].launch_date_precision == expected_precision

    @respx.mock
    async def test_fetch_with_retry_success(self, db_connection):
        """Test successful HTTP fetch on first attempt."""
        scraper = SpaceAgencyScraper()

        # Mock successful response
        url = f"{scraper.BASE_URL}{scraper.ENDPOINT}?limit=100"
        mock_response = {"results": []}
        respx.get(url).mock(return_value=httpx.Response(200, json=mock_response))

        raw_json, status = await scraper._fetch_with_retry(url)

        assert status == 200
        assert raw_json is not None
        assert json.loads(raw_json) == mock_response

    @respx.mock
    async def test_fetch_with_retry_server_error(self, db_connection):
        """Test retry logic on 5xx server errors."""
        scraper = SpaceAgencyScraper()
        scraper.settings.SCRAPER_MAX_RETRIES = 2  # Reduce retries for faster test

        url = f"{scraper.BASE_URL}{scraper.ENDPOINT}?limit=100"

        # Mock 500 error on first attempt, success on second
        respx.get(url).mock(
            side_effect=[
                httpx.Response(500, text="Internal Server Error"),
                httpx.Response(200, json={"results": []}),
            ]
        )

        raw_json, status = await scraper._fetch_with_retry(url)

        assert status == 200
        assert raw_json is not None

    @respx.mock
    async def test_fetch_with_retry_client_error_no_retry(self, db_connection):
        """Test that 4xx errors don't trigger retries."""
        scraper = SpaceAgencyScraper()

        url = f"{scraper.BASE_URL}{scraper.ENDPOINT}?limit=100"
        respx.get(url).mock(return_value=httpx.Response(404, text="Not Found"))

        raw_json, status = await scraper._fetch_with_retry(url)

        assert status == 404
        assert raw_json is None

    @respx.mock
    async def test_fetch_with_retry_timeout(self, db_connection):
        """Test retry logic on timeout."""
        scraper = SpaceAgencyScraper()
        scraper.settings.SCRAPER_MAX_RETRIES = 1  # Single retry for faster test

        url = f"{scraper.BASE_URL}{scraper.ENDPOINT}?limit=100"
        respx.get(url).mock(side_effect=httpx.TimeoutException("Timeout"))

        raw_json, status = await scraper._fetch_with_retry(url)

        assert status is None
        assert raw_json is None

    @respx.mock
    async def test_fetch_with_retry_all_attempts_fail(self, db_connection):
        """Test that exhausted retries return None."""
        scraper = SpaceAgencyScraper()
        scraper.settings.SCRAPER_MAX_RETRIES = 2

        url = f"{scraper.BASE_URL}{scraper.ENDPOINT}?limit=100"
        respx.get(url).mock(side_effect=httpx.RequestError("Network error"))

        raw_json, status = await scraper._fetch_with_retry(url)

        assert status is None
        assert raw_json is None

    @respx.mock
    async def test_scrape_end_to_end(self, db_connection, sample_ll2_response):
        """Test full scrape workflow from fetch to database upsert."""
        scraper = SpaceAgencyScraper()

        url = f"{scraper.BASE_URL}{scraper.ENDPOINT}?limit=100"
        respx.get(url).mock(return_value=httpx.Response(200, json=sample_ll2_response))

        result = await scraper.scrape()

        assert result["total_fetched"] == 3
        assert result["new_events"] == 3  # First run, all new
        assert result["updated_events"] == 0

        # Verify events were stored
        async with (
            get_db() as conn,
            conn.execute("SELECT COUNT(*) as count FROM launch_events") as cursor,
        ):
            row = await cursor.fetchone()
            assert row["count"] == 3

    @respx.mock
    async def test_scrape_idempotent(self, db_connection, sample_ll2_response):
        """Test that running scraper twice updates existing events."""
        scraper = SpaceAgencyScraper()

        url = f"{scraper.BASE_URL}{scraper.ENDPOINT}?limit=100"
        respx.get(url).mock(return_value=httpx.Response(200, json=sample_ll2_response))

        # First run
        result1 = await scraper.scrape()
        assert result1["new_events"] == 3
        assert result1["updated_events"] == 0

        # Second run (same data)
        result2 = await scraper.scrape()
        assert result2["total_fetched"] == 3
        # All events should already exist, so updated_events should be 3
        assert result2["updated_events"] == 3
        assert result2["new_events"] == 0

        # Verify still only 3 events (no duplicates)
        async with (
            get_db() as conn,
            conn.execute("SELECT COUNT(*) as count FROM launch_events") as cursor,
        ):
            row = await cursor.fetchone()
            assert row["count"] == 3

    @respx.mock
    async def test_scrape_logs_source_update(self, db_connection, sample_ll2_response):
        """Test that scrape updates source last_scraped_at timestamp."""
        scraper = SpaceAgencyScraper()

        url = f"{scraper.BASE_URL}{scraper.ENDPOINT}?limit=100"
        respx.get(url).mock(return_value=httpx.Response(200, json=sample_ll2_response))

        await scraper.scrape()

        # Verify source was updated
        async with (
            get_db() as conn,
            conn.execute(
                """
                SELECT last_scraped_at FROM osint_sources
                WHERE name = 'Launch Library 2'
                """
            ) as cursor,
        ):
            row = await cursor.fetchone()
            assert row is not None
            assert row["last_scraped_at"] is not None

            # Verify timestamp is recent (within last minute)
            last_scraped = datetime.fromisoformat(row["last_scraped_at"])
            now = datetime.now(UTC)
            delta = (now - last_scraped).total_seconds()
            assert delta < 60  # Less than 60 seconds old

    @respx.mock
    async def test_scrape_handles_fetch_failure(self, db_connection):
        """Test that scrape handles fetch failures gracefully."""
        scraper = SpaceAgencyScraper()
        scraper.settings.SCRAPER_MAX_RETRIES = 1

        url = f"{scraper.BASE_URL}{scraper.ENDPOINT}?limit=100"
        respx.get(url).mock(side_effect=httpx.RequestError("Network error"))

        result = await scraper.scrape()

        # Should return zero counts, not raise exception
        assert result["total_fetched"] == 0
        assert result["new_events"] == 0
        assert result["updated_events"] == 0

        # Verify scrape was logged even though it failed
        async with (
            get_db() as conn,
            conn.execute(
                """
                SELECT error_message FROM raw_scrape_records
                WHERE error_message IS NOT NULL
                """
            ) as cursor,
        ):
            row = await cursor.fetchone()
            assert row is not None
            assert "Failed to fetch data" in row["error_message"]

    async def test_parse_handles_missing_optional_fields(self):
        """Test parsing when optional fields (vehicle, location, pad) are missing."""
        scraper = SpaceAgencyScraper()

        minimal_response = {
            "results": [
                {
                    "name": "Minimal Launch",
                    "net": "2025-08-01T00:00:00Z",
                    "net_precision": {"id": 3},
                    "status": {"name": "TBD"},
                    "launch_service_provider": {"name": "Provider"},
                    # No rocket, pad, or location
                }
            ]
        }

        events = await scraper.parse(json.dumps(minimal_response))

        assert len(events) == 1
        assert events[0].name == "Minimal Launch"
        assert events[0].vehicle is None
        assert events[0].location is None
        assert events[0].pad is None
