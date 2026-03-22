"""Tests for database schema and repository functions.

Tests cover:
- Schema initialization (all tables created)
- OSINT source management (register, get, update)
- Scrape run logging
- Launch event CRUD operations
- Slug generation and collision handling
- Full-text search (FTS5)
- Event attribution
- Confidence scoring
- Foreign key cascades
"""

from __future__ import annotations

from datetime import UTC, datetime

import aiosqlite
import pytest

from openorbit.db import (
    add_attribution,
    get_event_attributions,
    get_launch_event_by_slug,
    get_launch_events,
    get_osint_sources,
    init_db_schema,
    log_scrape_run,
    register_osint_source,
    search_launch_events,
    update_source_last_scraped,
    upsert_launch_event,
)
from openorbit.models.db import LaunchEventCreate


@pytest.fixture
async def in_memory_db() -> aiosqlite.Connection:
    """Create in-memory SQLite database with schema initialized.

    Yields:
        Active database connection.
    """
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db_schema(conn)
    yield conn
    await conn.close()


@pytest.fixture
async def sample_osint_source(in_memory_db: aiosqlite.Connection) -> int:
    """Register a test OSINT source.

    Args:
        in_memory_db: Database connection fixture.

    Returns:
        Source ID.
    """
    return await register_osint_source(
        in_memory_db,
        name="Test NASA Scraper",
        url="https://www.nasa.gov/launches",
        scraper_class="openorbit.scrapers.nasa.NASAScraper",
        enabled=True,
    )


@pytest.fixture
async def sample_launch_event(in_memory_db: aiosqlite.Connection) -> str:
    """Create a test launch event.

    Args:
        in_memory_db: Database connection fixture.

    Returns:
        Event slug.
    """
    event = LaunchEventCreate(
        name="Falcon 9 | Starlink Group 7-1",
        launch_date=datetime(2025, 1, 22, 14, 30, 0, tzinfo=UTC),
        launch_date_precision="day",
        provider="SpaceX",
        vehicle="Falcon 9",
        location="Kennedy Space Center",
        pad="LC-39A",
        launch_type="civilian",
        status="scheduled",
    )
    return await upsert_launch_event(in_memory_db, event)


# =============================================================================
# Schema Initialization Tests
# =============================================================================


@pytest.mark.asyncio
async def test_init_db_schema_creates_all_tables(
    in_memory_db: aiosqlite.Connection,
) -> None:
    """Test that init_db_schema creates all required tables."""
    # Verify tables exist
    async with in_memory_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ) as cursor:
        tables = [row["name"] for row in await cursor.fetchall()]

    # Core tables that must exist
    expected_tables = [
        "event_attributions",
        "launch_events",
        "launch_events_fts",  # FTS5 virtual table
        "osint_sources",
        "raw_scrape_records",
    ]

    for table in expected_tables:
        assert table in tables, f"Table '{table}' was not created"

    # FTS5 creates additional internal tables (config, data, docsize, idx)
    # Their exact names may vary by SQLite version, so we just verify the main FTS table exists


# =============================================================================
# OSINT Source Management Tests
# =============================================================================


@pytest.mark.asyncio
async def test_register_osint_source_success(
    in_memory_db: aiosqlite.Connection,
) -> None:
    """Test successful OSINT source registration."""
    source_id = await register_osint_source(
        in_memory_db,
        name="SpaceX Launch Manifest",
        url="https://www.spacex.com/launches",
        scraper_class="openorbit.scrapers.spacex.SpaceXScraper",
        enabled=True,
    )

    assert source_id > 0

    # Verify source was created
    sources = await get_osint_sources(in_memory_db, enabled_only=False)
    assert len(sources) == 1
    assert sources[0].name == "SpaceX Launch Manifest"
    assert sources[0].scraper_class == "openorbit.scrapers.spacex.SpaceXScraper"
    assert sources[0].enabled is True


@pytest.mark.asyncio
async def test_register_osint_source_duplicate_name_raises(
    in_memory_db: aiosqlite.Connection,
) -> None:
    """Test that registering duplicate source name raises ValueError."""
    await register_osint_source(
        in_memory_db,
        name="NASA Scraper",
        url="https://www.nasa.gov/launches",
        scraper_class="openorbit.scrapers.nasa.NASAScraper",
    )

    with pytest.raises(ValueError, match="already exists"):
        await register_osint_source(
            in_memory_db,
            name="NASA Scraper",
            url="https://www.nasa.gov/different",
            scraper_class="openorbit.scrapers.nasa.NASAScraper",
        )


@pytest.mark.asyncio
async def test_get_osint_sources_enabled_only(
    in_memory_db: aiosqlite.Connection,
) -> None:
    """Test filtering sources by enabled status."""
    await register_osint_source(
        in_memory_db,
        name="Enabled Source",
        url="https://example.com/1",
        scraper_class="test.Scraper1",
        enabled=True,
    )
    await register_osint_source(
        in_memory_db,
        name="Disabled Source",
        url="https://example.com/2",
        scraper_class="test.Scraper2",
        enabled=False,
    )

    # Get enabled only (default)
    enabled_sources = await get_osint_sources(in_memory_db, enabled_only=True)
    assert len(enabled_sources) == 1
    assert enabled_sources[0].name == "Enabled Source"

    # Get all sources
    all_sources = await get_osint_sources(in_memory_db, enabled_only=False)
    assert len(all_sources) == 2


@pytest.mark.asyncio
async def test_update_source_last_scraped(
    in_memory_db: aiosqlite.Connection, sample_osint_source: int
) -> None:
    """Test updating last_scraped_at timestamp."""
    timestamp = datetime.now(UTC).isoformat()
    await update_source_last_scraped(in_memory_db, sample_osint_source, timestamp)

    sources = await get_osint_sources(in_memory_db, enabled_only=False)
    assert sources[0].last_scraped_at is not None
    assert sources[0].last_scraped_at.isoformat() == timestamp


@pytest.mark.asyncio
async def test_update_source_last_scraped_nonexistent_raises(
    in_memory_db: aiosqlite.Connection,
) -> None:
    """Test that updating nonexistent source raises ValueError."""
    with pytest.raises(ValueError, match="does not exist"):
        await update_source_last_scraped(
            in_memory_db, 99999, datetime.now(UTC).isoformat()
        )


# =============================================================================
# Scrape Run Logging Tests
# =============================================================================


@pytest.mark.asyncio
async def test_log_scrape_run_stores_payload(
    in_memory_db: aiosqlite.Connection, sample_osint_source: int
) -> None:
    """Test that scrape run is logged with payload."""
    payload = "<html><body>Launch data</body></html>"
    scrape_id = await log_scrape_run(
        in_memory_db,
        source_id=sample_osint_source,
        url="https://www.nasa.gov/launches/page1",
        http_status=200,
        content_type="text/html",
        payload=payload,
    )

    assert scrape_id > 0

    # Verify record was created
    async with in_memory_db.execute(
        "SELECT * FROM raw_scrape_records WHERE id = ?", (scrape_id,)
    ) as cursor:
        row = await cursor.fetchone()

    assert row["source_id"] == sample_osint_source
    assert row["http_status"] == 200
    assert row["payload"] == payload


@pytest.mark.asyncio
async def test_log_scrape_run_stores_error(
    in_memory_db: aiosqlite.Connection, sample_osint_source: int
) -> None:
    """Test that failed scrape run is logged with error message."""
    scrape_id = await log_scrape_run(
        in_memory_db,
        source_id=sample_osint_source,
        url="https://www.nasa.gov/launches/error",
        http_status=500,
        content_type=None,
        payload=None,
        error_message="Internal Server Error",
    )

    assert scrape_id > 0

    # Verify error was recorded
    async with in_memory_db.execute(
        "SELECT * FROM raw_scrape_records WHERE id = ?", (scrape_id,)
    ) as cursor:
        row = await cursor.fetchone()

    assert row["error_message"] == "Internal Server Error"
    assert row["payload"] is None


# =============================================================================
# Launch Event Management Tests
# =============================================================================


@pytest.mark.asyncio
async def test_upsert_launch_event_creates_new(
    in_memory_db: aiosqlite.Connection,
) -> None:
    """Test that upsert_launch_event creates a new event."""
    event = LaunchEventCreate(
        name="Falcon Heavy | Europa Clipper",
        launch_date=datetime(2025, 10, 10, 12, 0, 0, tzinfo=UTC),
        launch_date_precision="day",
        provider="SpaceX",
        vehicle="Falcon Heavy",
        location="Kennedy Space Center",
        pad="LC-39A",
        launch_type="civilian",
        status="scheduled",
    )

    slug = await upsert_launch_event(in_memory_db, event)
    assert slug == "spacex-falconheavy-2025-10-10"

    # Verify event was created
    retrieved = await get_launch_event_by_slug(in_memory_db, slug)
    assert retrieved is not None
    assert retrieved.name == "Falcon Heavy | Europa Clipper"
    assert retrieved.provider == "SpaceX"


@pytest.mark.asyncio
async def test_upsert_launch_event_updates_existing(
    in_memory_db: aiosqlite.Connection,
) -> None:
    """Test that upsert_launch_event updates existing event."""
    event = LaunchEventCreate(
        name="Original Name",
        launch_date=datetime(2025, 1, 22, 14, 30, 0, tzinfo=UTC),
        launch_date_precision="day",
        provider="SpaceX",
        vehicle="Falcon 9",
        status="scheduled",
    )

    slug = await upsert_launch_event(in_memory_db, event)

    # Update the event
    updated_event = LaunchEventCreate(
        name="Updated Name",
        launch_date=datetime(2025, 1, 22, 15, 0, 0, tzinfo=UTC),
        launch_date_precision="day",
        provider="SpaceX",
        vehicle="Falcon 9",
        status="delayed",
        slug=slug,  # Use existing slug
    )

    updated_slug = await upsert_launch_event(in_memory_db, updated_event)
    assert updated_slug == slug

    # Verify update
    retrieved = await get_launch_event_by_slug(in_memory_db, slug)
    assert retrieved is not None
    assert retrieved.name == "Updated Name"
    assert retrieved.status == "delayed"


@pytest.mark.asyncio
async def test_upsert_launch_event_generates_slug(
    in_memory_db: aiosqlite.Connection,
) -> None:
    """Test slug auto-generation from provider, vehicle, and date."""
    event = LaunchEventCreate(
        name="Test Event",
        launch_date=datetime(2025, 3, 15, 10, 0, 0, tzinfo=UTC),
        launch_date_precision="month",
        provider="NASA",
        vehicle="SLS",
        status="scheduled",
    )

    slug = await upsert_launch_event(in_memory_db, event)
    assert slug == "nasa-sls-2025-03"


@pytest.mark.asyncio
async def test_upsert_launch_event_handles_slug_collision(
    in_memory_db: aiosqlite.Connection,
) -> None:
    """Test slug collision handling (appends -2, -3, etc.)."""
    event1 = LaunchEventCreate(
        name="First Launch",
        launch_date=datetime(2025, 1, 22, 8, 0, 0, tzinfo=UTC),
        launch_date_precision="day",
        provider="Roscosmos",
        vehicle="Soyuz",
        status="scheduled",
    )

    slug1 = await upsert_launch_event(in_memory_db, event1)
    assert slug1 == "roscosmos-soyuz-2025-01-22"

    # Create second event same day
    event2 = LaunchEventCreate(
        name="Second Launch",
        launch_date=datetime(2025, 1, 22, 14, 0, 0, tzinfo=UTC),
        launch_date_precision="day",
        provider="Roscosmos",
        vehicle="Soyuz",
        status="scheduled",
    )

    slug2 = await upsert_launch_event(in_memory_db, event2)
    assert slug2 == "roscosmos-soyuz-2025-01-22-2"


@pytest.mark.asyncio
async def test_get_launch_events_filters_by_date(
    in_memory_db: aiosqlite.Connection,
) -> None:
    """Test filtering launch events by date range."""
    # Create events on different dates
    await upsert_launch_event(
        in_memory_db,
        LaunchEventCreate(
            name="Event 1",
            launch_date=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
            launch_date_precision="day",
            provider="SpaceX",
            status="scheduled",
        ),
    )
    await upsert_launch_event(
        in_memory_db,
        LaunchEventCreate(
            name="Event 2",
            launch_date=datetime(2025, 2, 1, 0, 0, 0, tzinfo=UTC),
            launch_date_precision="day",
            provider="SpaceX",
            status="scheduled",
        ),
    )
    await upsert_launch_event(
        in_memory_db,
        LaunchEventCreate(
            name="Event 3",
            launch_date=datetime(2025, 3, 1, 0, 0, 0, tzinfo=UTC),
            launch_date_precision="day",
            provider="SpaceX",
            status="scheduled",
        ),
    )

    # Filter by date range
    events = await get_launch_events(
        in_memory_db,
        date_from="2025-01-15T00:00:00Z",
        date_to="2025-02-15T00:00:00Z",
    )

    assert len(events) == 1
    assert events[0].name == "Event 2"


@pytest.mark.asyncio
async def test_get_launch_events_filters_by_provider(
    in_memory_db: aiosqlite.Connection,
) -> None:
    """Test filtering launch events by provider."""
    await upsert_launch_event(
        in_memory_db,
        LaunchEventCreate(
            name="SpaceX Event",
            launch_date=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
            launch_date_precision="day",
            provider="SpaceX",
            status="scheduled",
        ),
    )
    await upsert_launch_event(
        in_memory_db,
        LaunchEventCreate(
            name="NASA Event",
            launch_date=datetime(2025, 1, 2, 0, 0, 0, tzinfo=UTC),
            launch_date_precision="day",
            provider="NASA",
            status="scheduled",
        ),
    )

    # Filter by provider
    spacex_events = await get_launch_events(in_memory_db, provider="SpaceX")
    assert len(spacex_events) == 1
    assert spacex_events[0].provider == "SpaceX"


@pytest.mark.asyncio
async def test_get_launch_event_by_slug_found(
    in_memory_db: aiosqlite.Connection, sample_launch_event: str
) -> None:
    """Test retrieving event by slug (found)."""
    event = await get_launch_event_by_slug(in_memory_db, sample_launch_event)
    assert event is not None
    assert event.slug == sample_launch_event


@pytest.mark.asyncio
async def test_get_launch_event_by_slug_not_found(
    in_memory_db: aiosqlite.Connection,
) -> None:
    """Test retrieving event by slug (not found)."""
    event = await get_launch_event_by_slug(in_memory_db, "nonexistent-slug")
    assert event is None


# =============================================================================
# Full-Text Search Tests
# =============================================================================


@pytest.mark.asyncio
async def test_search_launch_events_fts5(in_memory_db: aiosqlite.Connection) -> None:
    """Test full-text search using FTS5."""
    await upsert_launch_event(
        in_memory_db,
        LaunchEventCreate(
            name="Falcon 9 | Starlink Group 7-1",
            launch_date=datetime(2025, 1, 22, 0, 0, 0, tzinfo=UTC),
            launch_date_precision="day",
            provider="SpaceX",
            status="scheduled",
        ),
    )
    await upsert_launch_event(
        in_memory_db,
        LaunchEventCreate(
            name="Falcon Heavy | Europa Clipper",
            launch_date=datetime(2025, 10, 10, 0, 0, 0, tzinfo=UTC),
            launch_date_precision="day",
            provider="SpaceX",
            status="scheduled",
        ),
    )
    await upsert_launch_event(
        in_memory_db,
        LaunchEventCreate(
            name="SLS | Artemis II",
            launch_date=datetime(2025, 9, 1, 0, 0, 0, tzinfo=UTC),
            launch_date_precision="day",
            provider="NASA",
            status="scheduled",
        ),
    )

    # Search for "Falcon"
    results = await search_launch_events(in_memory_db, "Falcon")
    assert len(results) == 2
    assert all("Falcon" in event.name for event in results)

    # Search for "Starlink"
    results = await search_launch_events(in_memory_db, "Starlink")
    assert len(results) == 1
    assert "Starlink" in results[0].name


# =============================================================================
# Event Attribution Tests
# =============================================================================


@pytest.mark.asyncio
async def test_add_attribution_links_event_to_scrape(
    in_memory_db: aiosqlite.Connection,
    sample_osint_source: int,
    sample_launch_event: str,
) -> None:
    """Test linking event to scrape record via attribution."""
    scrape_id = await log_scrape_run(
        in_memory_db,
        source_id=sample_osint_source,
        url="https://www.nasa.gov/launches",
        http_status=200,
        content_type="text/html",
        payload="<html>Launch data</html>",
    )

    attribution_id = await add_attribution(in_memory_db, sample_launch_event, scrape_id)
    assert attribution_id > 0

    # Verify attribution exists
    attributions = await get_event_attributions(in_memory_db, sample_launch_event)
    assert len(attributions) == 1
    assert attributions[0].source_name == "Test NASA Scraper"


@pytest.mark.asyncio
async def test_add_attribution_idempotent(
    in_memory_db: aiosqlite.Connection,
    sample_osint_source: int,
    sample_launch_event: str,
) -> None:
    """Test that adding duplicate attribution is idempotent."""
    scrape_id = await log_scrape_run(
        in_memory_db,
        source_id=sample_osint_source,
        url="https://www.nasa.gov/launches",
        http_status=200,
        content_type="text/html",
        payload="<html>Launch data</html>",
    )

    attribution_id_1 = await add_attribution(
        in_memory_db, sample_launch_event, scrape_id
    )
    attribution_id_2 = await add_attribution(
        in_memory_db, sample_launch_event, scrape_id
    )

    # Should return same ID
    assert attribution_id_1 == attribution_id_2

    # Should still have only one attribution
    attributions = await get_event_attributions(in_memory_db, sample_launch_event)
    assert len(attributions) == 1


@pytest.mark.asyncio
async def test_add_attribution_nonexistent_event_raises(
    in_memory_db: aiosqlite.Connection, sample_osint_source: int
) -> None:
    """Test that adding attribution with nonexistent event raises ValueError."""
    scrape_id = await log_scrape_run(
        in_memory_db,
        source_id=sample_osint_source,
        url="https://www.nasa.gov/launches",
        http_status=200,
        content_type="text/html",
        payload="<html>Launch data</html>",
    )

    with pytest.raises(ValueError, match="does not exist"):
        await add_attribution(in_memory_db, "nonexistent-slug", scrape_id)


@pytest.mark.asyncio
async def test_get_event_attributions_returns_sources(
    in_memory_db: aiosqlite.Connection, sample_launch_event: str
) -> None:
    """Test retrieving all attributions for an event."""
    # Register multiple sources
    source1 = await register_osint_source(
        in_memory_db, name="NASA", url="https://nasa.gov", scraper_class="test.NASA"
    )
    source2 = await register_osint_source(
        in_memory_db,
        name="SpaceX",
        url="https://spacex.com",
        scraper_class="test.SpaceX",
    )

    # Log scrapes
    scrape1 = await log_scrape_run(
        in_memory_db, source1, "https://nasa.gov/1", 200, "text/html", "<html>1</html>"
    )
    scrape2 = await log_scrape_run(
        in_memory_db,
        source2,
        "https://spacex.com/1",
        200,
        "text/html",
        "<html>2</html>",
    )

    # Add attributions
    await add_attribution(in_memory_db, sample_launch_event, scrape1)
    await add_attribution(in_memory_db, sample_launch_event, scrape2)

    # Retrieve attributions
    attributions = await get_event_attributions(in_memory_db, sample_launch_event)
    assert len(attributions) == 2

    source_names = {attr.source_name for attr in attributions}
    assert source_names == {"NASA", "SpaceX"}


# =============================================================================
# Confidence Score Tests
# =============================================================================


@pytest.mark.asyncio
async def test_confidence_score_increases_with_attributions(
    in_memory_db: aiosqlite.Connection,
) -> None:
    """Test that confidence score increases as more sources confirm the event."""
    # Create a fresh event for this test
    event = LaunchEventCreate(
        name="Test Event for Confidence",
        launch_date=datetime(2025, 1, 22, 14, 30, 0, tzinfo=UTC),
        launch_date_precision="day",
        provider="TestProvider",
        vehicle="TestVehicle",
        status="scheduled",
    )
    slug = await upsert_launch_event(in_memory_db, event)

    # Initial confidence (base = 50, precision 'day' = +5, 0 attributions = +0)
    retrieved = await get_launch_event_by_slug(in_memory_db, slug)
    assert retrieved is not None
    assert retrieved.confidence_score == 55  # 50 + 0 + 5
    assert retrieved.attribution_count == 0

    # Add first attribution (0 -> 1 source = +0)
    source = await register_osint_source(
        in_memory_db, "Source 1", "https://example.com/1", "test.Scraper1"
    )
    scrape = await log_scrape_run(
        in_memory_db,
        source,
        "https://example.com/1",
        200,
        "text/html",
        "<html>1</html>",
    )
    await add_attribution(in_memory_db, slug, scrape)

    retrieved = await get_launch_event_by_slug(in_memory_db, slug)
    assert retrieved is not None
    assert retrieved.confidence_score == 55  # 50 + 0 + 5 (still 1 source)
    assert retrieved.attribution_count == 1

    # Add second attribution (1 -> 2 sources = +10)
    source2 = await register_osint_source(
        in_memory_db, "Source 2", "https://example.com/2", "test.Scraper2"
    )
    scrape2 = await log_scrape_run(
        in_memory_db,
        source2,
        "https://example.com/2",
        200,
        "text/html",
        "<html>2</html>",
    )
    await add_attribution(in_memory_db, slug, scrape2)

    retrieved = await get_launch_event_by_slug(in_memory_db, slug)
    assert retrieved is not None
    assert retrieved.confidence_score == 65  # 50 + 10 + 5
    assert retrieved.attribution_count == 2

    # Add third attribution (2 -> 3 sources = +20)
    source3 = await register_osint_source(
        in_memory_db, "Source 3", "https://example.com/3", "test.Scraper3"
    )
    scrape3 = await log_scrape_run(
        in_memory_db,
        source3,
        "https://example.com/3",
        200,
        "text/html",
        "<html>3</html>",
    )
    await add_attribution(in_memory_db, slug, scrape3)

    retrieved = await get_launch_event_by_slug(in_memory_db, slug)
    assert retrieved is not None
    assert retrieved.confidence_score == 75  # 50 + 20 + 5
    assert retrieved.attribution_count == 3


# =============================================================================
# Foreign Key Cascade Tests
# =============================================================================


@pytest.mark.asyncio
async def test_foreign_key_cascade_deletes(in_memory_db: aiosqlite.Connection) -> None:
    """Test that deleting source cascades to scrape records and attributions."""
    # Enable foreign keys
    await in_memory_db.execute("PRAGMA foreign_keys = ON")

    # Create source, scrape, event, and attribution
    source = await register_osint_source(
        in_memory_db, "Test Source", "https://example.com", "test.Scraper"
    )
    scrape = await log_scrape_run(
        in_memory_db,
        source,
        "https://example.com/1",
        200,
        "text/html",
        "<html>1</html>",
    )

    event = LaunchEventCreate(
        name="Test Event",
        launch_date=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        launch_date_precision="day",
        provider="Test Provider",
        status="scheduled",
    )
    slug = await upsert_launch_event(in_memory_db, event)
    await add_attribution(in_memory_db, slug, scrape)

    # Verify attribution exists
    attributions = await get_event_attributions(in_memory_db, slug)
    assert len(attributions) == 1

    # Delete source
    await in_memory_db.execute("DELETE FROM osint_sources WHERE id = ?", (source,))
    await in_memory_db.commit()

    # Verify scrape record was cascade deleted
    async with in_memory_db.execute(
        "SELECT COUNT(*) as count FROM raw_scrape_records WHERE id = ?", (scrape,)
    ) as cursor:
        result = await cursor.fetchone()
        assert result["count"] == 0

    # Verify attribution was cascade deleted
    attributions = await get_event_attributions(in_memory_db, slug)
    assert len(attributions) == 0
