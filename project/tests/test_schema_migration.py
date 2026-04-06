"""Tests for PO-028: source tier and claim lifecycle schema migration.

Verifies that new columns are added idempotently to existing tables,
models carry correct defaults, and scraper class vars are set correctly.
"""

from __future__ import annotations

import aiosqlite
import pytest

from openorbit.db import (
    add_attribution,
    init_db_schema,
    log_scrape_run,
    register_osint_source,
    upsert_launch_event,
)
from openorbit.models.db import EventAttribution, LaunchEventCreate, OSINTSource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_db() -> aiosqlite.Connection:
    """Create an in-memory DB and initialise the schema."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db_schema(conn)
    return conn


async def _seed_event(conn: aiosqlite.Connection) -> str:
    """Insert a minimal launch event and return its slug."""
    from datetime import UTC, datetime

    event = LaunchEventCreate(
        name="Test Launch",
        launch_date=datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC),
        launch_date_precision="hour",
        provider="TestCo",
        status="scheduled",
    )
    slug = await upsert_launch_event(conn, event)
    return slug


async def _seed_attribution(conn: aiosqlite.Connection, slug: str) -> tuple[int, int]:
    """Seed a source + scrape record and return (source_id, scrape_record_id)."""
    source_id = await register_osint_source(
        conn, "test_src", "https://example.com", "test.Scraper"
    )
    scrape_id = await log_scrape_run(
        conn,
        source_id=source_id,
        url="https://example.com",
        http_status=200,
        content_type="application/json",
        payload="{}",
    )
    await add_attribution(conn, slug, scrape_id)
    return source_id, scrape_id


# ---------------------------------------------------------------------------
# Schema / migration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_db_schema_idempotent() -> None:
    """Calling init_db_schema twice must not raise."""
    conn = await _make_db()
    await init_db_schema(conn)  # second call — should be a no-op
    await conn.close()


@pytest.mark.asyncio
async def test_osint_sources_has_source_tier_column() -> None:
    """osint_sources must have a source_tier column after migration."""
    conn = await _make_db()
    async with conn.execute("PRAGMA table_info(osint_sources)") as cur:
        cols = {row["name"] for row in await cur.fetchall()}
    await conn.close()
    assert "source_tier" in cols


@pytest.mark.asyncio
async def test_launch_events_has_claim_lifecycle_column() -> None:
    """launch_events must have a claim_lifecycle column after migration."""
    conn = await _make_db()
    async with conn.execute("PRAGMA table_info(launch_events)") as cur:
        cols = {row["name"] for row in await cur.fetchall()}
    await conn.close()
    assert "claim_lifecycle" in cols


@pytest.mark.asyncio
async def test_launch_events_has_event_kind_column() -> None:
    """launch_events must have an event_kind column after migration."""
    conn = await _make_db()
    async with conn.execute("PRAGMA table_info(launch_events)") as cur:
        cols = {row["name"] for row in await cur.fetchall()}
    await conn.close()
    assert "event_kind" in cols


@pytest.mark.asyncio
async def test_event_attributions_has_enrichment_columns() -> None:
    """event_attributions must have all 6 enrichment columns after migration."""
    expected = {
        "source_url",
        "observed_at",
        "evidence_type",
        "source_tier",
        "confidence_score",
        "confidence_rationale",
    }
    conn = await _make_db()
    async with conn.execute("PRAGMA table_info(event_attributions)") as cur:
        cols = {row["name"] for row in await cur.fetchall()}
    await conn.close()
    assert expected.issubset(cols)


@pytest.mark.asyncio
async def test_migration_on_old_schema() -> None:
    """Migration must add missing columns to an existing DB without new cols."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row

    # Create a minimal old-style schema without the new columns
    await conn.executescript("""
        CREATE TABLE osint_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            scraper_class TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_scraped_at TEXT
        );
        CREATE TABLE launch_events (
            slug TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            launch_date TEXT NOT NULL,
            launch_date_precision TEXT NOT NULL,
            provider TEXT NOT NULL,
            vehicle TEXT,
            location TEXT,
            pad TEXT,
            launch_type TEXT,
            status TEXT NOT NULL,
            confidence_score INTEGER NOT NULL DEFAULT 50,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE raw_scrape_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            scraped_at TEXT NOT NULL,
            url TEXT NOT NULL,
            http_status INTEGER,
            content_type TEXT,
            payload TEXT,
            error_message TEXT
        );
        CREATE TABLE event_attributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_slug TEXT NOT NULL,
            scrape_record_id INTEGER NOT NULL,
            attributed_at TEXT NOT NULL
        );
        CREATE TABLE api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            key_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            revoked_at TEXT
        );
    """)
    await conn.commit()

    # Run migration — must not raise
    await init_db_schema(conn)

    # Verify new columns exist
    async with conn.execute("PRAGMA table_info(osint_sources)") as cur:
        source_cols = {row["name"] for row in await cur.fetchall()}
    async with conn.execute("PRAGMA table_info(launch_events)") as cur:
        event_cols = {row["name"] for row in await cur.fetchall()}
    async with conn.execute("PRAGMA table_info(event_attributions)") as cur:
        attr_cols = {row["name"] for row in await cur.fetchall()}

    await conn.close()

    assert "source_tier" in source_cols
    assert "claim_lifecycle" in event_cols
    assert "event_kind" in event_cols
    assert {"source_url", "observed_at", "evidence_type", "source_tier",
             "confidence_score", "confidence_rationale"}.issubset(attr_cols)


# ---------------------------------------------------------------------------
# Function-level tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_attribution_with_enrichment_fields() -> None:
    """add_attribution must persist and return enrichment fields."""
    from openorbit.db import get_event_attributions

    conn = await _make_db()
    slug = await _seed_event(conn)
    source_id = await register_osint_source(
        conn, "enriched_src", "https://enriched.example.com", "test.Enriched"
    )
    scrape_id = await log_scrape_run(
        conn,
        source_id=source_id,
        url="https://enriched.example.com/data",
        http_status=200,
        content_type="application/json",
        payload="{}",
    )

    await add_attribution(
        conn,
        slug,
        scrape_id,
        source_url="https://enriched.example.com/evidence",
        evidence_type="official_schedule",
        source_tier=1,
        confidence_score=90,
        confidence_rationale="Primary official feed",
    )

    attributions = await get_event_attributions(conn, slug)
    await conn.close()

    assert len(attributions) == 1
    attr = attributions[0]
    assert attr.source_url == "https://enriched.example.com/evidence"
    assert attr.evidence_type == "official_schedule"
    assert attr.source_tier == 1
    assert attr.confidence_score == 90
    assert attr.confidence_rationale == "Primary official feed"


@pytest.mark.asyncio
async def test_add_attribution_backward_compat() -> None:
    """add_attribution with only 3 positional args must still work."""
    conn = await _make_db()
    slug = await _seed_event(conn)
    source_id, scrape_id = await _seed_attribution(conn, slug)

    # Idempotent re-call — must not raise
    from openorbit.db import get_event_attributions

    attributions = await get_event_attributions(conn, slug)
    await conn.close()

    assert len(attributions) >= 1
    attr = attributions[0]
    # Optional fields should be None when not provided
    assert attr.evidence_type is None
    assert attr.source_tier is None


# ---------------------------------------------------------------------------
# Model default tests
# ---------------------------------------------------------------------------


def test_launch_event_create_model_defaults() -> None:
    """LaunchEventCreate must have correct defaults for new fields."""
    from datetime import UTC, datetime

    event = LaunchEventCreate(
        name="Test",
        launch_date=datetime(2025, 1, 1, tzinfo=UTC),
        launch_date_precision="day",
        provider="TestCo",
        status="scheduled",
    )
    assert event.claim_lifecycle == "indicated"
    assert event.event_kind == "observed"


def test_osint_source_model_source_tier_default() -> None:
    """OSINTSource must default source_tier to 1."""

    src = OSINTSource(
        id=1,
        name="test",
        url="https://test.example.com",
        scraper_class="test.Scraper",
        enabled=True,
    )
    assert src.source_tier == 1


def test_event_attribution_model_optional_fields() -> None:
    """EventAttribution optional enrichment fields must default to None."""
    from datetime import UTC, datetime

    attr = EventAttribution(
        source_name="test",
        scraped_at=datetime(2025, 1, 1, tzinfo=UTC),
        url="https://test.example.com",
    )
    assert attr.source_url is None
    assert attr.observed_at is None
    assert attr.evidence_type is None
    assert attr.source_tier is None
    assert attr.confidence_score is None
    assert attr.confidence_rationale is None


# ---------------------------------------------------------------------------
# Scraper class-var tests
# ---------------------------------------------------------------------------


def test_scraper_class_vars_tier_1_sources() -> None:
    """Tier-1 scrapers must have source_tier=1 and evidence_type='official_schedule'."""
    from openorbit.scrapers.arianespace_official import ArianespaceOfficialScraper
    from openorbit.scrapers.cnsa_official import CNSAOfficialScraper
    from openorbit.scrapers.commercial import CommercialLaunchScraper
    from openorbit.scrapers.esa_official import ESAOfficialScraper
    from openorbit.scrapers.isro_official import ISROOfficialScraper
    from openorbit.scrapers.jaxa_official import JAXAOfficialScraper
    from openorbit.scrapers.space_agency import SpaceAgencyScraper
    from openorbit.scrapers.spacex_official import SpaceXOfficialScraper

    tier1_scrapers = [
        SpaceAgencyScraper,
        SpaceXOfficialScraper,
        CommercialLaunchScraper,
        ESAOfficialScraper,
        JAXAOfficialScraper,
        ISROOfficialScraper,
        ArianespaceOfficialScraper,
        CNSAOfficialScraper,
    ]
    for scraper_cls in tier1_scrapers:
        assert scraper_cls.source_tier == 1, (
            f"{scraper_cls.__name__}.source_tier expected 1, got {scraper_cls.source_tier}"
        )
        assert scraper_cls.evidence_type == "official_schedule", (
            f"{scraper_cls.__name__}.evidence_type expected 'official_schedule', "
            f"got {scraper_cls.evidence_type}"
        )


def test_scraper_class_vars_tier_2_sources() -> None:
    """Tier-2 scrapers must have source_tier=2 and correct evidence_type."""
    from openorbit.scrapers.celestrak import CelesTrakScraper
    from openorbit.scrapers.notams import NotamScraper

    assert CelesTrakScraper.source_tier == 2
    assert CelesTrakScraper.evidence_type == "tle_anomaly"
    assert NotamScraper.source_tier == 2
    assert NotamScraper.evidence_type == "notam"
