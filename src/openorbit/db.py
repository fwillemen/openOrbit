"""Database connection management and repository functions.

Provides async SQLite connection lifecycle management using aiosqlite.
Includes table initialization and dependency injection for FastAPI.

Repository Pattern:
- Source management: register_osint_source, get_osint_sources,
  update_source_last_scraped
- Scrape logging: log_scrape_run
- Event management: upsert_launch_event, get_launch_events,
  count_launch_events, get_launch_event_by_slug, search_launch_events
- Attribution: add_attribution, get_event_attributions
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextlib import suppress as contextlib_suppress
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from openorbit.config import get_settings
from openorbit.models.db import (
    EventAttribution,
    LaunchEvent,
    LaunchEventCreate,
    OSINTSource,
)
from openorbit.tiering import ResultTier, result_tier_sql_expr

logger = logging.getLogger(__name__)

_db_connection: aiosqlite.Connection | None = None
_SQLITE_URL_PREFIX = "sqlite+aiosqlite:///"


def resolve_sqlite_db_path(database_url: str) -> str:
    """Resolve SQLite DATABASE_URL to a deterministic DB path.

    Relative filesystem paths are resolved against the project root (``project/``)
    so commands executed from different working directories still use one DB file.

    Args:
        database_url: SQLAlchemy-style SQLite URL.

    Returns:
        Resolved sqlite path string, or special sqlite target (e.g. ``:memory:``).

    Raises:
        ValueError: If URL is not a sqlite+aiosqlite URL.
    """
    if not database_url.startswith(_SQLITE_URL_PREFIX):
        raise ValueError(
            "DATABASE_URL must start with 'sqlite+aiosqlite:///' for SQLite mode"
        )

    raw_path = database_url.removeprefix(_SQLITE_URL_PREFIX)

    # Keep special SQLite targets untouched.
    if raw_path == ":memory:" or raw_path.startswith("file:"):
        return raw_path

    candidate = Path(raw_path)
    if candidate.is_absolute():
        return str(candidate)

    project_root = Path(__file__).resolve().parents[2]
    return str((project_root / candidate).resolve())


async def init_db() -> None:
    """Initialize database connection and create tables.

    Creates the database file if it doesn't exist and sets up
    the initial schema. Safe to call multiple times (idempotent).
    """
    global _db_connection

    settings = get_settings()
    db_path = resolve_sqlite_db_path(settings.DATABASE_URL)

    logger.info(f"Initializing database at {db_path}")

    _db_connection = await aiosqlite.connect(db_path)
    _db_connection.row_factory = aiosqlite.Row

    # Initialize schema if not already done
    await init_db_schema(_db_connection)

    logger.info("Database initialized successfully")


async def close_db() -> None:
    """Close database connection.

    Safe to call even if connection is already closed.
    """
    global _db_connection

    if _db_connection is not None:
        await _db_connection.close()
        _db_connection = None
        logger.info("Database connection closed")


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """Get database connection for dependency injection.

    Yields:
        Active database connection.

    Raises:
        RuntimeError: If database is not initialized.
    """
    if _db_connection is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    yield _db_connection


# =============================================================================
# Schema Management
# =============================================================================


async def init_db_schema(conn: aiosqlite.Connection) -> None:
    """Execute schema.sql to create all tables (idempotent).

    Args:
        conn: Active database connection.

    Raises:
        aiosqlite.Error: If schema creation fails.
    """
    try:
        # Load schema.sql from package resources
        schema_path = Path(__file__).parent / "schema.sql"
        schema_sql = schema_path.read_text(encoding="utf-8")

        # Execute schema (all statements use IF NOT EXISTS, so it's idempotent)
        await conn.executescript(schema_sql)
        await conn.commit()

        # Migration: add parse_error column if it doesn't exist yet.
        try:
            await conn.execute(
                "ALTER TABLE raw_scrape_records ADD COLUMN parse_error INTEGER NOT NULL DEFAULT 0"
            )
            await conn.commit()
            logger.info("Migrated raw_scrape_records: added parse_error column")
        except Exception:
            # Column already exists — safe to ignore.
            pass

        # Migration: add refresh_interval_hours to osint_sources if missing.
        try:
            await conn.execute(
                "ALTER TABLE osint_sources ADD COLUMN refresh_interval_hours INTEGER NOT NULL DEFAULT 6"
            )
            await conn.commit()
            logger.info("Migrated osint_sources: added refresh_interval_hours column")
        except Exception:
            # Column already exists — safe to ignore.
            pass

        # Migration: add inference_flags to launch_events if missing.
        try:
            await conn.execute(
                "ALTER TABLE launch_events ADD COLUMN inference_flags TEXT"
            )
            await conn.commit()
            logger.info("Migrated launch_events: added inference_flags column")
        except Exception:
            # Column already exists — safe to ignore.
            pass

        # PO-028: source tier and claim lifecycle migrations.
        migrations = [
            "ALTER TABLE osint_sources ADD COLUMN source_tier INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE launch_events ADD COLUMN claim_lifecycle TEXT NOT NULL DEFAULT 'indicated'",
            "ALTER TABLE launch_events ADD COLUMN event_kind TEXT NOT NULL DEFAULT 'observed'",
            "ALTER TABLE event_attributions ADD COLUMN source_url TEXT",
            "ALTER TABLE event_attributions ADD COLUMN observed_at TEXT",
            "ALTER TABLE event_attributions ADD COLUMN evidence_type TEXT",
            "ALTER TABLE event_attributions ADD COLUMN source_tier INTEGER",
            "ALTER TABLE event_attributions ADD COLUMN confidence_score INTEGER",
            "ALTER TABLE event_attributions ADD COLUMN confidence_rationale TEXT",
        ]
        for migration_sql in migrations:
            with contextlib_suppress(aiosqlite.OperationalError):
                await conn.execute(migration_sql)
        await conn.commit()

        # FTS5 migration: expand to include provider, vehicle, location columns.
        # The old table only had slug + name (2 data columns + rank = 3 total).
        # The new table has slug + name + provider + vehicle + location (5 data cols).
        try:
            async with conn.execute("SELECT * FROM launch_events_fts LIMIT 0") as cur:
                col_names = [d[0] for d in (cur.description or [])]
        except Exception:
            col_names = []

        # 5 data cols + rank = 6; old schema has 3. Rebuild if insufficient.
        if len(col_names) < 6:
            await conn.executescript(
                """
                DROP TABLE IF EXISTS launch_events_fts;
                DROP TRIGGER IF EXISTS launch_events_fts_insert;
                DROP TRIGGER IF EXISTS launch_events_fts_update;
                DROP TRIGGER IF EXISTS launch_events_fts_delete;
                CREATE VIRTUAL TABLE IF NOT EXISTS launch_events_fts USING fts5(
                    slug UNINDEXED,
                    name,
                    provider,
                    vehicle,
                    location,
                    content='launch_events',
                    content_rowid='rowid'
                );
                CREATE TRIGGER IF NOT EXISTS launch_events_fts_insert
                AFTER INSERT ON launch_events
                BEGIN
                    INSERT INTO launch_events_fts(rowid, slug, name, provider, vehicle, location)
                    VALUES (new.rowid, new.slug, new.name, new.provider, new.vehicle, new.location);
                END;
                CREATE TRIGGER IF NOT EXISTS launch_events_fts_update
                AFTER UPDATE ON launch_events
                BEGIN
                    UPDATE launch_events_fts
                    SET name = new.name, provider = new.provider,
                        vehicle = new.vehicle, location = new.location
                    WHERE rowid = old.rowid;
                END;
                CREATE TRIGGER IF NOT EXISTS launch_events_fts_delete
                AFTER DELETE ON launch_events
                BEGIN
                    DELETE FROM launch_events_fts WHERE rowid = old.rowid;
                END;
                """
            )
            await conn.execute(
                "INSERT INTO launch_events_fts(launch_events_fts) VALUES('rebuild')"
            )
            await conn.commit()
            logger.info(
                "Migrated launch_events_fts: expanded to provider/vehicle/location"
            )

        logger.info("Database schema initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database schema: {e}")
        raise


# =============================================================================
# OSINT Source Management
# =============================================================================


async def register_osint_source(
    conn: aiosqlite.Connection,
    name: str,
    url: str,
    scraper_class: str,
    enabled: bool = True,
    source_tier: int = 1,
) -> int:
    """Register a new OSINT source.

    Args:
        conn: Database connection.
        name: Human-readable source name (must be unique).
        url: Base URL of the data source.
        scraper_class: Python class path (e.g., 'openorbit.scrapers.nasa.NASAScraper').
        enabled: Whether the source is enabled (default: True).
        source_tier: Credibility tier — 1=Official, 2=Operational, 3=Analytical (default: 1).

    Returns:
        Source ID of the created source.

    Raises:
        ValueError: If source name already exists.
    """
    try:
        cursor = await conn.execute(
            """
            INSERT INTO osint_sources (name, url, scraper_class, enabled, source_tier)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, url, scraper_class, 1 if enabled else 0, source_tier),
        )
        await conn.commit()
        source_id = cursor.lastrowid
        if source_id is None:
            raise RuntimeError("Failed to retrieve source ID after insert")
        logger.info(f"Registered OSINT source '{name}' (ID: {source_id})")
        return source_id
    except aiosqlite.IntegrityError as e:
        logger.error(f"Failed to register source '{name}': {e}")
        raise ValueError(f"Source with name '{name}' already exists") from e


async def get_osint_sources(
    conn: aiosqlite.Connection,
    enabled_only: bool = True,
) -> list[OSINTSource]:
    """Retrieve all OSINT sources.

    Args:
        conn: Database connection.
        enabled_only: If True, only return enabled sources (default: True).

    Returns:
        List of OSINTSource models.
    """
    query = "SELECT * FROM osint_sources"
    if enabled_only:
        query += " WHERE enabled = 1"
    query += " ORDER BY name"

    async with conn.execute(query) as cursor:
        rows = await cursor.fetchall()

    sources = []
    for row in rows:
        sources.append(
            OSINTSource(
                id=row["id"],
                name=row["name"],
                url=row["url"],
                scraper_class=row["scraper_class"],
                enabled=bool(row["enabled"]),
                last_scraped_at=(
                    datetime.fromisoformat(row["last_scraped_at"])
                    if row["last_scraped_at"]
                    else None
                ),
                refresh_interval_hours=int(row["refresh_interval_hours"])
                if row["refresh_interval_hours"] is not None
                else 6,
            )
        )

    return sources


async def update_source_last_scraped(
    conn: aiosqlite.Connection,
    source_id: int,
    timestamp: str,
) -> None:
    """Update last_scraped_at for a source.

    Args:
        conn: Database connection.
        source_id: Source ID to update.
        timestamp: ISO 8601 timestamp.

    Raises:
        ValueError: If source_id does not exist.
    """
    cursor = await conn.execute(
        "UPDATE osint_sources SET last_scraped_at = ? WHERE id = ?",
        (timestamp, source_id),
    )
    await conn.commit()

    if cursor.rowcount == 0:
        raise ValueError(f"Source ID {source_id} does not exist")

    logger.info(f"Updated last_scraped_at for source {source_id} to {timestamp}")


# =============================================================================
# Scrape Run Logging
# =============================================================================


async def log_scrape_run(
    conn: aiosqlite.Connection,
    source_id: int,
    url: str,
    http_status: int | None,
    content_type: str | None,
    payload: str | None,
    error_message: str | None = None,
) -> int:
    """Record a raw scrape attempt.

    Args:
        conn: Database connection.
        source_id: ID of the source being scraped.
        url: Exact URL scraped.
        http_status: HTTP status code (200, 404, etc.).
        content_type: MIME type (text/html, application/json).
        payload: Raw HTML/JSON content (nullable if scrape failed).
        error_message: Error details if scrape failed.

    Returns:
        Scrape record ID.
    """
    scraped_at = datetime.now(UTC).isoformat()

    cursor = await conn.execute(
        """
        INSERT INTO raw_scrape_records (
            source_id, scraped_at, url, http_status,
            content_type, payload, error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (source_id, scraped_at, url, http_status, content_type, payload, error_message),
    )
    await conn.commit()

    scrape_record_id = cursor.lastrowid
    if scrape_record_id is None:
        raise RuntimeError("Failed to retrieve scrape record ID after insert")
    logger.info(
        f"Logged scrape run for source {source_id}: record ID {scrape_record_id}"
    )
    return scrape_record_id


# =============================================================================
# Launch Event Management
# =============================================================================


def _generate_slug(
    provider: str,
    vehicle: str | None,
    launch_date: datetime,
    precision: str,
) -> str:
    """Generate URL-safe slug from event metadata.

    Args:
        provider: Launch provider (e.g., 'SpaceX').
        vehicle: Launch vehicle (e.g., 'Falcon 9').
        launch_date: Launch date/time.
        precision: Date precision ('second', 'minute', 'hour', 'day',
            'month', 'year', 'quarter').

    Returns:
        URL-safe slug (e.g., 'spacex-falcon9-2025-01-22').
    """
    # Normalize provider and vehicle (remove spaces first to avoid extra hyphens)
    provider_slug = re.sub(r"[^a-z0-9]+", "-", provider.replace(" ", "").lower()).strip(
        "-"
    )
    vehicle_slug = (
        re.sub(r"[^a-z0-9]+", "-", vehicle.replace(" ", "").lower()).strip("-")
        if vehicle
        else ""
    )

    # Extract date portion based on precision
    if precision == "second":
        date_slug = launch_date.strftime("%Y-%m-%d-%H-%M-%S")
    elif precision == "minute":
        date_slug = launch_date.strftime("%Y-%m-%d-%H-%M")
    elif precision == "hour":
        date_slug = launch_date.strftime("%Y-%m-%d-%H")
    elif precision == "day":
        date_slug = launch_date.strftime("%Y-%m-%d")
    elif precision == "month":
        date_slug = launch_date.strftime("%Y-%m")
    elif precision == "year":
        date_slug = launch_date.strftime("%Y")
    elif precision == "quarter":
        quarter = (launch_date.month - 1) // 3 + 1
        date_slug = f"{launch_date.year}-Q{quarter}"
    else:
        date_slug = launch_date.strftime("%Y-%m-%d")

    # Combine parts
    parts = [provider_slug]
    if vehicle_slug:
        parts.append(vehicle_slug)
    parts.append(date_slug)

    return "-".join(parts)


def _calculate_confidence_score(attribution_count: int, precision: str) -> int:
    """Calculate confidence score based on attribution count and date precision.

    Formula: Base (50) + Attribution Bonus + Precision Bonus
    - Attribution: 1 source = +0, 2 = +10, 3 = +20, 4+ = +30
    - Precision: second = +20, minute = +15, hour = +10, day = +5,
      month = 0, year = -5, quarter = -10

    Args:
        attribution_count: Number of sources confirming the event.
        precision: Date precision level.

    Returns:
        Confidence score (0-100).
    """
    base_score = 50

    # Attribution bonus (capped at +30)
    # 0 sources = +0, 1 source = +0, 2 sources = +10, 3 sources = +20, 4+ sources = +30
    attribution_bonus = max(0, min((attribution_count - 1) * 10, 30))

    # Precision bonus
    precision_bonus_map = {
        "second": 20,
        "minute": 15,
        "hour": 10,
        "day": 5,
        "month": 0,
        "year": -5,
        "quarter": -10,
    }
    precision_bonus = precision_bonus_map.get(precision, 0)

    # Calculate and clamp to 0-100
    score = base_score + attribution_bonus + precision_bonus
    return max(0, min(100, score))


async def upsert_launch_event(
    conn: aiosqlite.Connection,
    event: LaunchEventCreate,
) -> str:
    """Insert or update a launch event.

    Slug is auto-generated from provider + vehicle + launch_date if not provided.
    If slug collision occurs, appends '-2', '-3', etc.

    Args:
        conn: Database connection.
        event: LaunchEventCreate model with all required fields.

    Returns:
        Event slug (str).
    """
    # Generate slug if not provided
    if not event.slug:
        base_slug = _generate_slug(
            event.provider,
            event.vehicle,
            event.launch_date,
            event.launch_date_precision,
        )
        slug = base_slug

        # Handle collisions
        counter = 2
        while True:
            async with conn.execute(
                "SELECT 1 FROM launch_events WHERE slug = ?", (slug,)
            ) as cursor:
                exists = await cursor.fetchone()
            if not exists:
                break
            slug = f"{base_slug}-{counter}"
            counter += 1
    else:
        slug = event.slug

    # Check if event already exists
    async with conn.execute(
        "SELECT slug FROM launch_events WHERE slug = ?", (slug,)
    ) as cursor:
        existing = await cursor.fetchone()

    now = datetime.now(UTC).isoformat()

    # Get current attribution count for confidence scoring
    async with conn.execute(
        "SELECT COUNT(*) as count FROM event_attributions WHERE event_slug = ?", (slug,)
    ) as cursor:
        result = await cursor.fetchone()
        attribution_count = result["count"] if result else 0

    confidence_score = _calculate_confidence_score(
        attribution_count, event.launch_date_precision
    )

    if existing:
        # Update existing event
        await conn.execute(
            """
            UPDATE launch_events
            SET name = ?, launch_date = ?, launch_date_precision = ?, provider = ?,
                vehicle = ?, location = ?, pad = ?, launch_type = ?, status = ?,
                confidence_score = ?, updated_at = ?,
                claim_lifecycle = ?, event_kind = ?
            WHERE slug = ?
            """,
            (
                event.name,
                event.launch_date.isoformat(),
                event.launch_date_precision,
                event.provider,
                event.vehicle,
                event.location,
                event.pad,
                event.launch_type,
                event.status,
                confidence_score,
                now,
                event.claim_lifecycle,
                event.event_kind,
                slug,
            ),
        )
        logger.info(f"Updated launch event '{slug}'")
    else:
        # Insert new event
        await conn.execute(
            """
            INSERT INTO launch_events (
                slug, name, launch_date, launch_date_precision, provider, vehicle,
                location, pad, launch_type, status, confidence_score,
                claim_lifecycle, event_kind, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                event.name,
                event.launch_date.isoformat(),
                event.launch_date_precision,
                event.provider,
                event.vehicle,
                event.location,
                event.pad,
                event.launch_type,
                event.status,
                confidence_score,
                event.claim_lifecycle,
                event.event_kind,
                now,
                now,
            ),
        )
        logger.info(f"Created launch event '{slug}'")

    await conn.commit()
    return slug


async def get_launch_events(
    conn: aiosqlite.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    provider: str | None = None,
    status: str | None = None,
    launch_type: str | None = None,
    min_confidence: float | None = None,
    result_tier: ResultTier | None = None,
    has_inference_flag: str | None = None,
    cursor_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[LaunchEvent]:
    """Query launch events with optional filters.

    Args:
        conn: Database connection.
        date_from: Filter events from this date (ISO 8601).
        date_to: Filter events to this date (ISO 8601).
        provider: Case-insensitive substring match on provider name.
        status: Filter by event status.
        launch_type: Filter by launch type.
        min_confidence: Minimum confidence_score (inclusive).
        result_tier: Filter by derived result tier.
        has_inference_flag: Filter to events containing this flag in inference_flags.
        cursor_id: Cursor-based pagination — return rows with rowid > cursor_id.
        limit: Maximum number of results (default: 100).
        offset: Result offset for page-based pagination (default: 0).

    Returns:
        List of LaunchEvent models.
    """
    query = """
        SELECT 
            e.rowid as id,
            e.*,
            (SELECT COUNT(*) FROM event_attributions WHERE event_slug = e.slug) as attribution_count
        FROM launch_events e
        WHERE 1=1
    """
    params: list[str | int | float] = []

    if date_from:
        query += " AND launch_date >= ?"
        params.append(date_from)

    if date_to:
        query += " AND launch_date <= ?"
        params.append(date_to)

    if provider:
        query += " AND LOWER(provider) LIKE LOWER(?)"
        params.append(f"%{provider}%")

    if status:
        query += " AND status = ?"
        params.append(status)

    if launch_type:
        query += " AND launch_type = ?"
        params.append(launch_type)

    if min_confidence is not None:
        query += " AND confidence_score >= ?"
        params.append(min_confidence)

    if result_tier:
        query += f" AND ({result_tier_sql_expr('e')}) = ?"
        params.append(result_tier)

    if has_inference_flag:
        query += " AND inference_flags LIKE ?"
        params.append(f'%"{has_inference_flag}"%')

    if cursor_id is not None:
        # Cursor pagination: keyed on rowid ascending.
        query += " AND e.rowid > ?"
        params.append(cursor_id)
        query += " ORDER BY e.rowid ASC LIMIT ?"
        params.append(limit)
    else:
        query += " ORDER BY launch_date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    async with conn.execute(query, params) as cursor:
        rows = await cursor.fetchall()

    events = []
    for row in rows:
        events.append(
            LaunchEvent(
                id=row["id"],
                slug=row["slug"],
                name=row["name"],
                launch_date=datetime.fromisoformat(row["launch_date"]),
                launch_date_precision=row["launch_date_precision"],
                provider=row["provider"],
                vehicle=row["vehicle"],
                location=row["location"],
                pad=row["pad"],
                launch_type=row["launch_type"],
                status=row["status"],
                confidence_score=row["confidence_score"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                attribution_count=row["attribution_count"],
                inference_flags=json.loads(row["inference_flags"] or "[]"),
            )
        )

    return events


async def count_launch_events(
    conn: aiosqlite.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    provider: str | None = None,
    status: str | None = None,
    launch_type: str | None = None,
    min_confidence: float | None = None,
    result_tier: ResultTier | None = None,
    has_inference_flag: str | None = None,
) -> int:
    """Count launch events matching the given filters.

    Mirrors the filter logic of get_launch_events() but returns a total count
    for use in pagination metadata.

    Args:
        conn: Database connection.
        date_from: Filter events from this date (ISO 8601).
        date_to: Filter events to this date (ISO 8601).
        provider: Case-insensitive substring match on provider name.
        status: Filter by event status.
        launch_type: Filter by launch type.
        min_confidence: Minimum confidence_score (inclusive).
        result_tier: Filter by derived result tier.
        has_inference_flag: Filter to events containing this flag in inference_flags.

    Returns:
        Total count of matching launch events.
    """
    query = "SELECT COUNT(*) FROM launch_events e WHERE 1=1"
    params: list[str | int | float] = []

    if date_from:
        query += " AND launch_date >= ?"
        params.append(date_from)

    if date_to:
        query += " AND launch_date <= ?"
        params.append(date_to)

    if provider:
        query += " AND LOWER(provider) LIKE LOWER(?)"
        params.append(f"%{provider}%")

    if status:
        query += " AND status = ?"
        params.append(status)

    if launch_type:
        query += " AND launch_type = ?"
        params.append(launch_type)

    if min_confidence is not None:
        query += " AND confidence_score >= ?"
        params.append(min_confidence)

    if result_tier:
        query += f" AND ({result_tier_sql_expr('e')}) = ?"
        params.append(result_tier)

    if has_inference_flag:
        query += " AND inference_flags LIKE ?"
        params.append(f'%"{has_inference_flag}"%')

    async with conn.execute(query, params) as cursor:
        row = await cursor.fetchone()

    if row is None:
        return 0
    count = row[0]
    return int(count) if count is not None else 0


async def get_launch_event_by_slug(
    conn: aiosqlite.Connection,
    slug: str,
) -> LaunchEvent | None:
    """Retrieve a single launch event by slug.

    Args:
        conn: Database connection.
        slug: Event slug (primary key).

    Returns:
        LaunchEvent or None if not found.
    """
    query = """
        SELECT 
            e.rowid as id,
            e.*,
            (SELECT COUNT(*) FROM event_attributions WHERE event_slug = e.slug) as attribution_count
        FROM launch_events e
        WHERE e.slug = ?
    """

    async with conn.execute(query, (slug,)) as cursor:
        row = await cursor.fetchone()

    if not row:
        return None

    return LaunchEvent(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        launch_date=datetime.fromisoformat(row["launch_date"]),
        launch_date_precision=row["launch_date_precision"],
        provider=row["provider"],
        vehicle=row["vehicle"],
        location=row["location"],
        pad=row["pad"],
        launch_type=row["launch_type"],
        status=row["status"],
        confidence_score=row["confidence_score"],
        claim_lifecycle=row["claim_lifecycle"] or "indicated",
        event_kind=row["event_kind"] or "observed",
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        attribution_count=row["attribution_count"],
        inference_flags=json.loads(row["inference_flags"] or "[]"),
    )


async def search_launch_events(
    conn: aiosqlite.Connection,
    query: str,
    limit: int = 20,
) -> list[LaunchEvent]:
    """Full-text search launch events by name using FTS5.

    Args:
        conn: Database connection.
        query: Search query string.
        limit: Maximum number of results (default: 20).

    Returns:
        List of LaunchEvent models ordered by relevance.
    """
    fts_query = """
        SELECT e.*, 
               (SELECT COUNT(*) FROM event_attributions WHERE event_slug = e.slug) as attribution_count
        FROM launch_events_fts
        JOIN launch_events e ON e.slug = launch_events_fts.slug
        WHERE launch_events_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """

    async with conn.execute(fts_query, (query, limit)) as cursor:
        rows = await cursor.fetchall()

    events = []
    for row in rows:
        events.append(
            LaunchEvent(
                slug=row["slug"],
                name=row["name"],
                launch_date=datetime.fromisoformat(row["launch_date"]),
                launch_date_precision=row["launch_date_precision"],
                provider=row["provider"],
                vehicle=row["vehicle"],
                location=row["location"],
                pad=row["pad"],
                launch_type=row["launch_type"],
                status=row["status"],
                confidence_score=row["confidence_score"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                attribution_count=row["attribution_count"],
                inference_flags=json.loads(row["inference_flags"] or "[]"),
            )
        )

    return events


async def fts_search(
    conn: aiosqlite.Connection,
    q: str,
    *,
    result_tier: ResultTier | None = None,
    limit: int = 25,
    offset: int = 0,
) -> list[LaunchEvent]:
    """Full-text search launch events using FTS5 MATCH, ordered by BM25 relevance.

    Args:
        conn: Database connection.
        q: FTS5 query string (supports FTS5 syntax).
        result_tier: Optional filter by result tier.
        limit: Maximum number of results.
        offset: Result offset for page-based pagination.

    Returns:
        List of LaunchEvent models ordered by relevance.
    """
    if not q or not q.strip():
        return []

    sql = """
        SELECT e.rowid as id, e.*,
               (SELECT COUNT(*) FROM event_attributions WHERE event_slug = e.slug) as attribution_count
        FROM launch_events_fts fts
        JOIN launch_events e ON e.rowid = fts.rowid
        WHERE launch_events_fts MATCH ?
    """
    params: list[str | int | float] = [q]

    if result_tier is not None:
        sql += f" AND ({result_tier_sql_expr('e')}) = ?"
        params.append(result_tier)

    sql += " ORDER BY rank LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    async with conn.execute(sql, params) as cursor:
        rows = await cursor.fetchall()

    events = []
    for row in rows:
        events.append(
            LaunchEvent(
                id=row["id"],
                slug=row["slug"],
                name=row["name"],
                launch_date=datetime.fromisoformat(row["launch_date"]),
                launch_date_precision=row["launch_date_precision"],
                provider=row["provider"],
                vehicle=row["vehicle"],
                location=row["location"],
                pad=row["pad"],
                launch_type=row["launch_type"],
                status=row["status"],
                confidence_score=row["confidence_score"],
                claim_lifecycle=row["claim_lifecycle"] or "indicated",
                event_kind=row["event_kind"] or "observed",
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                attribution_count=row["attribution_count"],
                inference_flags=json.loads(row["inference_flags"] or "[]"),
            )
        )

    return events


async def count_fts_search(
    conn: aiosqlite.Connection,
    q: str,
    *,
    result_tier: ResultTier | None = None,
) -> int:
    """Count launch events matching a full-text search query.

    Args:
        conn: Database connection.
        q: FTS5 query string.
        result_tier: Optional filter by result tier.

    Returns:
        Total count of matching launch events.
    """
    if not q or not q.strip():
        return 0

    sql = """
        SELECT COUNT(*) FROM launch_events_fts fts
        JOIN launch_events e ON e.rowid = fts.rowid
        WHERE launch_events_fts MATCH ?
    """
    params: list[str | int | float] = [q]

    if result_tier is not None:
        sql += f" AND ({result_tier_sql_expr('e')}) = ?"
        params.append(result_tier)

    async with conn.execute(sql, params) as cursor:
        row = await cursor.fetchone()

    return int(row[0]) if row and row[0] is not None else 0


# =============================================================================
# Inference Flags
# =============================================================================


async def update_inference_flags(
    conn: aiosqlite.Connection,
    slug: str,
    flags: list[str],
) -> None:
    """Persist inference flags for a launch event.

    Args:
        conn: Database connection.
        slug: Event slug to update.
        flags: List of inference flag strings to store (replaces existing).
    """
    import json as _json

    await conn.execute(
        "UPDATE launch_events SET inference_flags = ? WHERE slug = ?",
        (_json.dumps(flags), slug),
    )
    await conn.commit()
    logger.debug(f"Updated inference_flags for '{slug}': {flags}")


# =============================================================================
# Event Attribution
# =============================================================================


async def add_attribution(
    conn: aiosqlite.Connection,
    event_slug: str,
    scrape_record_id: int,
    *,
    source_url: str | None = None,
    observed_at: str | None = None,
    evidence_type: str | None = None,
    source_tier: int | None = None,
    confidence_score: int | None = None,
    confidence_rationale: str | None = None,
) -> int:
    """Link a launch event to a scrape record.

    Idempotent: no-op if attribution already exists.

    Args:
        conn: Database connection.
        event_slug: Event slug (FK to launch_events).
        scrape_record_id: Scrape record ID (FK to raw_scrape_records).
        source_url: Optional direct URL of the evidence.
        observed_at: ISO 8601 timestamp of when evidence was observed.
        evidence_type: Classification of the evidence (e.g., 'official_schedule', 'notam').
        source_tier: Credibility tier of the source — 1=Official, 2=Operational, 3=Analytical.
        confidence_score: 0–100 confidence score for this attribution.
        confidence_rationale: Human-readable rationale for the confidence score.

    Returns:
        Attribution ID (existing or newly created).

    Raises:
        ValueError: If event_slug or scrape_record_id does not exist.
    """
    # Verify event exists
    async with conn.execute(
        "SELECT 1 FROM launch_events WHERE slug = ?", (event_slug,)
    ) as cursor:
        if not await cursor.fetchone():
            raise ValueError(f"Event slug '{event_slug}' does not exist")

    # Verify scrape record exists
    async with conn.execute(
        "SELECT 1 FROM raw_scrape_records WHERE id = ?", (scrape_record_id,)
    ) as cursor:
        if not await cursor.fetchone():
            raise ValueError(f"Scrape record ID {scrape_record_id} does not exist")

    # Check if attribution already exists
    async with conn.execute(
        "SELECT id FROM event_attributions WHERE event_slug = ? AND scrape_record_id = ?",
        (event_slug, scrape_record_id),
    ) as cursor:
        existing = await cursor.fetchone()

    if existing:
        logger.info(
            f"Attribution already exists: event '{event_slug}' ↔ "
            f"scrape {scrape_record_id}"
        )
        existing_id = existing["id"]
        if not isinstance(existing_id, int):
            raise TypeError(f"Attribution ID must be int, got {type(existing_id)}")
        return existing_id

    # Create new attribution
    attributed_at = datetime.now(UTC).isoformat()
    cursor = await conn.execute(
        """INSERT INTO event_attributions (
            event_slug, scrape_record_id, attributed_at,
            source_url, observed_at, evidence_type,
            source_tier, confidence_score, confidence_rationale
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_slug,
            scrape_record_id,
            attributed_at,
            source_url,
            observed_at,
            evidence_type,
            source_tier,
            confidence_score,
            confidence_rationale,
        ),
    )
    await conn.commit()

    attribution_id = cursor.lastrowid
    if attribution_id is None:
        raise RuntimeError("Failed to retrieve attribution ID after insert")
    logger.info(
        f"Created attribution: event '{event_slug}' ↔ "
        f"scrape {scrape_record_id} (ID: {attribution_id})"
    )

    # Recalculate confidence score for the event
    async with conn.execute(
        "SELECT COUNT(*) as count FROM event_attributions WHERE event_slug = ?",
        (event_slug,),
    ) as cursor:
        result = await cursor.fetchone()
        attribution_count = result["count"] if result else 0

    async with conn.execute(
        "SELECT launch_date_precision FROM launch_events WHERE slug = ?",
        (event_slug,),
    ) as cursor:
        event_row = await cursor.fetchone()
        if event_row is None:
            raise RuntimeError(f"Event '{event_slug}' not found after attribution")
        precision = event_row["launch_date_precision"]

    confidence_score = _calculate_confidence_score(attribution_count, precision)
    await conn.execute(
        "UPDATE launch_events SET confidence_score = ?, updated_at = ? WHERE slug = ?",
        (confidence_score, datetime.now(UTC).isoformat(), event_slug),
    )
    await conn.commit()

    return attribution_id


async def get_event_attributions(
    conn: aiosqlite.Connection,
    event_slug: str,
) -> list[EventAttribution]:
    """Get all source attributions for an event.

    Args:
        conn: Database connection.
        event_slug: Event slug.

    Returns:
        List of EventAttribution models.
    """
    query = """
        SELECT 
            s.name as source_name,
            r.scraped_at,
            r.url,
            a.source_url,
            a.observed_at,
            a.evidence_type,
            a.source_tier,
            a.confidence_score,
            a.confidence_rationale
        FROM event_attributions a
        JOIN raw_scrape_records r ON a.scrape_record_id = r.id
        JOIN osint_sources s ON r.source_id = s.id
        WHERE a.event_slug = ?
        ORDER BY r.scraped_at DESC
    """

    async with conn.execute(query, (event_slug,)) as cursor:
        rows = await cursor.fetchall()

    attributions = []
    for row in rows:
        attributions.append(
            EventAttribution(
                source_name=row["source_name"],
                scraped_at=datetime.fromisoformat(row["scraped_at"]),
                url=row["url"],
                source_url=row["source_url"],
                observed_at=(
                    datetime.fromisoformat(row["observed_at"])
                    if row["observed_at"]
                    else None
                ),
                evidence_type=row["evidence_type"],
                source_tier=row["source_tier"],
                confidence_score=row["confidence_score"],
                confidence_rationale=row["confidence_rationale"],
            )
        )

    return attributions


# =============================================================================
# Parse-Error Flagging
# =============================================================================


async def flag_parse_error(
    scrape_record_id: int,
    conn: aiosqlite.Connection | None = None,
) -> None:
    """Mark a raw_scrape_records row as having a parse error.

    Args:
        scrape_record_id: PK of the raw_scrape_records row to flag.
        conn: Optional connection override; falls back to the global connection.

    Raises:
        RuntimeError: If no database connection is available.
        ValueError: If scrape_record_id does not exist.
    """
    connection = conn if conn is not None else _db_connection
    if connection is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    async with connection.execute(
        "SELECT 1 FROM raw_scrape_records WHERE id = ?", (scrape_record_id,)
    ) as cursor:
        if not await cursor.fetchone():
            raise ValueError(f"scrape_record_id {scrape_record_id!r} not found")

    await connection.execute(
        "UPDATE raw_scrape_records SET parse_error = 1 WHERE id = ?",
        (scrape_record_id,),
    )
    await connection.commit()
    logger.info(f"Flagged scrape record {scrape_record_id} as parse_error")
