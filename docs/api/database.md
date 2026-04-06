# Database API Reference

This document details all 13 repository functions available in `openorbit.db` for type-safe database access. These functions form the primary interface for database operations.

## Overview

The repository layer provides a clean, async-first interface to the database:

- **Initialization** — Schema creation and connection lifecycle
- **Source Management** — Register and query OSINT data sources
- **Scrape Logging** — Record raw scrape attempts for audit trails
- **Event Management** — Create, update, and query launch events
- **Search** — Full-text search over launch event names
- **Attribution** — Link events to scrape sources

All functions are async and use Pydantic models for type safety.

---

## Connection Lifecycle

### `async init_db() → None`

Initialize the database connection and create tables.

**Purpose:** Set up the database file, establish connection, and create all tables with their indexes and triggers.

**Parameters:** None

**Returns:** None

**Raises:**
- `aiosqlite.Error` — If schema creation fails

**Behavior:** Idempotent — safe to call multiple times (uses `CREATE TABLE IF NOT EXISTS`).

**Example:**
```python
from openorbit.db import init_db

await init_db()  # Connects to DB_URL and creates schema
```

**Notes:**
- Called automatically during FastAPI startup via lifespan handler
- Sets up global `_db_connection` singleton
- Reads `schema.sql` from package resources

---

### `async close_db() → None`

Close the database connection.

**Purpose:** Clean up database resources, typically called during application shutdown.

**Parameters:** None

**Returns:** None

**Behavior:** Idempotent — safe to call even if connection already closed.

**Example:**
```python
from openorbit.db import close_db

await close_db()  # Closes global connection
```

**Notes:**
- Called automatically during FastAPI shutdown
- Safe to call multiple times

---

### `async get_db() → AsyncIterator[aiosqlite.Connection]`

Get database connection for dependency injection.

**Purpose:** Provides the active database connection to route handlers and other functions.

**Parameters:** None

**Yields:**
- `aiosqlite.Connection` — Active database connection

**Raises:**
- `RuntimeError` — If database is not initialized

**Example:**
```python
from fastapi import Depends
from openorbit.db import get_db

@app.get("/launches")
async def list_launches(db = Depends(get_db)) -> list:
    """List all launches."""
    from openorbit.db import get_launch_events
    events = await get_launch_events(db)
    return [event.model_dump() for event in events]
```

**Notes:**
- Used as FastAPI `Depends()` injectable
- Context manager — automatically yields connection without managing lifecycle

---

## OSINT Source Management

### `async register_osint_source(conn, name, url, scraper_class, enabled=True) → int`

Register a new OSINT data source.

**Purpose:** Add a new scraper/data source to the registry.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conn` | `aiosqlite.Connection` | ✅ | Database connection |
| `name` | `str` | ✅ | Human-readable source name (must be unique) |
| `url` | `str` | ✅ | Base URL of data source |
| `scraper_class` | `str` | ✅ | Python class path (e.g., `openorbit.scrapers.nasa.NASAScraper`) |
| `enabled` | `bool` | ❌ | Enable/disable flag (default: `True`) |

**Returns:** `int` — ID of newly created source

**Raises:**
- `ValueError` — If source name already exists

**Example:**
```python
from openorbit.db import register_osint_source, get_db

async with get_db() as conn:
    source_id = await register_osint_source(
        conn,
        name="NASA Launches",
        url="https://api.nasa.gov/launches",
        scraper_class="openorbit.scrapers.nasa.NASAScraper",
        enabled=True
    )
    print(f"Created source with ID: {source_id}")
```

**Constraints:**
- Source name must be globally unique (database constraint: UNIQUE)
- If name already exists, ValueError is raised

---

### `async get_osint_sources(conn, enabled_only=True) → list[OSINTSource]`

Retrieve all registered OSINT sources.

**Purpose:** Query the source registry with optional filtering.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conn` | `aiosqlite.Connection` | ✅ | Database connection |
| `enabled_only` | `bool` | ❌ | Filter to enabled sources only (default: `True`) |

**Returns:** `list[OSINTSource]` — List of source records

**Example:**
```python
from openorbit.db import get_osint_sources, get_db
from openorbit.models.db import OSINTSource

async with get_db() as conn:
    # Get only enabled sources
    sources = await get_osint_sources(conn, enabled_only=True)
    for source in sources:
        print(f"{source.id}: {source.name} ({source.url})")
        print(f"  Last scraped: {source.last_scraped_at}")

    # Get all sources (including disabled)
    all_sources = await get_osint_sources(conn, enabled_only=False)
```

**Notes:**
- Results ordered by name (alphabetical)
- `enabled_only=True` filters using database index for performance

---

### `async update_source_last_scraped(conn, source_id, timestamp) → None`

Update the last scrape timestamp for a source.

**Purpose:** Record when a source was successfully scraped (for monitoring/scheduling).

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conn` | `aiosqlite.Connection` | ✅ | Database connection |
| `source_id` | `int` | ✅ | ID of source to update |
| `timestamp` | `str` | ✅ | ISO 8601 timestamp (e.g., `"2025-01-22T14:30:00+00:00"`) |

**Returns:** None

**Raises:**
- `ValueError` — If source_id does not exist

**Example:**
```python
from datetime import datetime, UTC
from openorbit.db import update_source_last_scraped, get_db

async with get_db() as conn:
    now = datetime.now(UTC).isoformat()
    try:
        await update_source_last_scraped(conn, source_id=1, timestamp=now)
    except ValueError as e:
        print(f"Error: {e}")  # Source not found
```

---

## Scrape Run Logging

### `async log_scrape_run(conn, source_id, url, http_status, content_type, payload, error_message=None) → int`

Record a raw scrape attempt (immutable audit trail).

**Purpose:** Log every HTTP request to a data source for debugging, monitoring, and attribution.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conn` | `aiosqlite.Connection` | ✅ | Database connection |
| `source_id` | `int` | ✅ | Source being scraped |
| `url` | `str` | ✅ | Exact URL that was scraped |
| `http_status` | `int` | ❌ | HTTP status code (200, 404, 500, etc.) |
| `content_type` | `str` | ❌ | MIME type (text/html, application/json) |
| `payload` | `str` | ❌ | Raw response body (nullable if scrape failed) |
| `error_message` | `str` | ❌ | Error message if scrape failed |

**Returns:** `int` — ID of created scrape record

**Example:**
```python
from openorbit.db import log_scrape_run, get_db

async with get_db() as conn:
    # Successful scrape
    record_id = await log_scrape_run(
        conn,
        source_id=1,
        url="https://api.nasa.gov/launches?limit=10",
        http_status=200,
        content_type="application/json",
        payload='[{"name": "Falcon 9 v1.0"}]'
    )
    print(f"Logged scrape as record {record_id}")

    # Failed scrape
    error_record_id = await log_scrape_run(
        conn,
        source_id=1,
        url="https://api.nasa.gov/launches",
        http_status=500,
        content_type=None,
        payload=None,
        error_message="Server returned 500 Internal Server Error"
    )
```

**Timestamps:** `scraped_at` is automatically set to current UTC time.

---

## Launch Event Management

### `async upsert_launch_event(conn, event) → str`

Insert or update a launch event (idempotent).

**Purpose:** Create a new launch event or update an existing one using slug-based deduplication.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conn` | `aiosqlite.Connection` | ✅ | Database connection |
| `event` | `LaunchEventCreate` | ✅ | Event data model |

**Returns:** `str` — Event slug (primary key)

**Example:**
```python
from datetime import datetime, UTC
from openorbit.models.db import LaunchEventCreate
from openorbit.db import upsert_launch_event, get_db

async with get_db() as conn:
    event = LaunchEventCreate(
        name="Falcon 9 USSF-Delta Launch",
        launch_date=datetime(2025, 1, 22, 14, 30, 0, tzinfo=UTC),
        launch_date_precision="hour",
        provider="SpaceX",
        vehicle="Falcon 9",
        location="Kennedy Space Center",
        pad="LC-39A",
        launch_type="civilian",
        status="scheduled"
    )
    
    slug = await upsert_launch_event(conn, event)
    print(f"Event slug: {slug}")  # spacex-falcon9-2025-01-22
```

**Slug Generation:**
- Auto-generated from `provider + vehicle + launch_date` with precision-based formatting
- Collision handling: appends `-2`, `-3`, etc. if slug exists
- Manual override: pass `slug` in `LaunchEventCreate.slug` to use custom slug

**Confidence Score:**
- Automatically calculated based on:
  - Number of source attributions (1 source = +0, 2 = +10, 3 = +20, 4+ = +30)
  - Date precision (second = +20, day = +5, quarter = -10)
  - Base score: 50
- Clamped to 0-100 range

**Update Behavior:**
- If slug exists: updates all fields, recalculates confidence
- If slug doesn't exist: creates new record
- Both operations are atomic and commit immediately

---

### `async get_launch_events(conn, *, date_from=None, date_to=None, provider=None, status=None, launch_type=None, limit=100, offset=0) → list[LaunchEvent]`

Query launch events with optional filters and pagination.

**Purpose:** Retrieve launch events with flexible filtering and pagination.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conn` | `aiosqlite.Connection` | ✅ | Database connection |
| `date_from` | `str` | ❌ | ISO 8601 start date (inclusive) |
| `date_to` | `str` | ❌ | ISO 8601 end date (inclusive) |
| `provider` | `str` | ❌ | Filter by launch provider (exact match) |
| `status` | `str` | ❌ | Filter by status (exact match) |
| `launch_type` | `str` | ❌ | Filter by type (exact match) |
| `limit` | `int` | ❌ | Max results (default: 100) |
| `offset` | `int` | ❌ | Pagination offset (default: 0) |

**Returns:** `list[LaunchEvent]` — Matching events ordered by date (newest first)

**Example:**
```python
from openorbit.db import get_launch_events, get_db

async with get_db() as conn:
    # Get SpaceX launches in 2025
    events = await get_launch_events(
        conn,
        date_from="2025-01-01T00:00:00+00:00",
        date_to="2025-12-31T23:59:59+00:00",
        provider="SpaceX",
        status="scheduled",
        limit=50,
        offset=0
    )
    
    for event in events:
        print(f"{event.name} ({event.status}) - {event.launch_date}")
        print(f"  Confidence: {event.confidence_score}%, Sources: {event.attribution_count}")
```

**Notes:**
- Results include `attribution_count` (number of sources confirming event)
- Ordered by `launch_date DESC` (newest first)
- Filters are combined with AND logic

---

### `async get_launch_event_by_slug(conn, slug) → LaunchEvent | None`

Retrieve a single launch event by slug (fastest lookup).

**Purpose:** Get a specific event using its primary key.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conn` | `aiosqlite.Connection` | ✅ | Database connection |
| `slug` | `str` | ✅ | Event slug (primary key) |

**Returns:** `LaunchEvent | None` — Event if found, else None

**Example:**
```python
from openorbit.db import get_launch_event_by_slug, get_db

async with get_db() as conn:
    event = await get_launch_event_by_slug(conn, "spacex-falcon9-2025-01-22")
    
    if event:
        print(f"Found: {event.name}")
        print(f"Status: {event.status}")
    else:
        print("Event not found")
```

**Notes:**
- Primary key lookup — fastest query (O(1) on indexed slug)
- Includes attribution count

---

### `async search_launch_events(conn, query, limit=20) → list[LaunchEvent]`

Full-text search launch events by name using FTS5.

**Purpose:** Find events using natural language search with relevance ranking.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conn` | `aiosqlite.Connection` | ✅ | Database connection |
| `query` | `str` | ✅ | FTS5 search query (supports operators) |
| `limit` | `int` | ❌ | Max results (default: 20) |

**Returns:** `list[LaunchEvent]` — Matching events ordered by relevance

**FTS5 Query Syntax:**

| Pattern | Example | Meaning |
|---------|---------|---------|
| Simple word | `falcon` | Contains "falcon" anywhere |
| Phrase | `"falcon 9"` | Contains exact phrase "falcon 9" |
| AND operator | `falcon AND 2025` | Contains both "falcon" AND "2025" |
| OR operator | `falcon OR spacex` | Contains either "falcon" OR "spacex" |
| NOT operator | `falcon NOT heavy` | Contains "falcon" but NOT "heavy" |

**Example:**
```python
from openorbit.db import search_launch_events, get_db

async with get_db() as conn:
    # Simple search
    results = await search_launch_events(conn, "falcon", limit=20)
    
    # Phrase search
    results = await search_launch_events(conn, '"Falcon 9"', limit=10)
    
    # Boolean search
    results = await search_launch_events(conn, "falcon AND 2025 NOT heavy", limit=20)
    
    for event in results:
        print(f"{event.name} - {event.launch_date}")
```

**Notes:**
- Indexed on event name only (slug is excluded from FTS)
- Results ordered by FTS5 relevance ranking
- Case-insensitive search

---

## Event Attribution

### `async add_attribution(conn, event_slug, scrape_record_id) → int`

Link a launch event to a scrape record (idempotent).

**Purpose:** Record which scrape record(s) provided evidence for a launch event.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conn` | `aiosqlite.Connection` | ✅ | Database connection |
| `event_slug` | `str` | ✅ | Event slug (must exist) |
| `scrape_record_id` | `int` | ✅ | Scrape record ID (must exist) |

**Returns:** `int` — Attribution ID (existing or newly created)

**Raises:**
- `ValueError` — If event_slug or scrape_record_id doesn't exist

**Side Effects:**
- Automatically recalculates event's confidence score
- Updates event's `updated_at` timestamp

**Example:**
```python
from openorbit.db import add_attribution, log_scrape_run, get_db

async with get_db() as conn:
    # 1. Log a scrape
    scrape_id = await log_scrape_run(
        conn,
        source_id=1,
        url="https://api.nasa.gov/launches",
        http_status=200,
        content_type="application/json",
        payload='[...]'
    )
    
    # 2. Link to event
    attribution_id = await add_attribution(
        conn,
        event_slug="spacex-falcon9-2025-01-22",
        scrape_record_id=scrape_id
    )
    print(f"Attribution created: {attribution_id}")
```

**Idempotence:**
- If attribution already exists (same event_slug + scrape_record_id), returns existing ID
- No-op if called twice with same parameters

---

### `async get_event_attributions(conn, event_slug) → list[EventAttribution]`

Get all source attributions for an event.

**Purpose:** See which sources have confirmed a launch event.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conn` | `aiosqlite.Connection` | ✅ | Database connection |
| `event_slug` | `str` | ✅ | Event slug |

**Returns:** `list[EventAttribution]` — List of attributions with source info

**Example:**
```python
from openorbit.db import get_event_attributions, get_db

async with get_db() as conn:
    attributions = await get_event_attributions(conn, "spacex-falcon9-2025-01-22")
    
    for attr in attributions:
        print(f"Source: {attr.source_name}")
        print(f"  URL: {attr.url}")
        print(f"  Scraped: {attr.scraped_at}")
```

**Notes:**
- Includes source name, URL, and scrape timestamp
- Ordered by scrape timestamp (newest first)
- EventAttribution model fields:
  - `source_name`: Human-readable source name
  - `url`: URL that was scraped
  - `scraped_at`: ISO 8601 timestamp of scrape

---

## Error Handling

All async functions may raise:

- `aiosqlite.Error` — Low-level SQLite errors
- `ValueError` — Data validation errors (e.g., non-existent IDs)
- `RuntimeError` — Unexpected internal errors (e.g., missing lastrowid)

**Best Practice:**

```python
from openorbit.db import add_attribution, get_db

async with get_db() as conn:
    try:
        attribution_id = await add_attribution(
            conn,
            event_slug="unknown-event",
            scrape_record_id=999
        )
    except ValueError as e:
        print(f"Validation error: {e}")  # Event or scrape record not found
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise
```

---

## Examples

### Complete Workflow

```python
from datetime import datetime, UTC
from openorbit.db import (
    init_db, close_db, get_db,
    register_osint_source, log_scrape_run,
    upsert_launch_event, add_attribution,
    get_launch_event_by_slug
)
from openorbit.models.db import LaunchEventCreate

async def main():
    # Initialize database
    await init_db()
    
    async with get_db() as conn:
        # 1. Register a data source
        source_id = await register_osint_source(
            conn,
            name="NASA Launches",
            url="https://api.nasa.gov/launches",
            scraper_class="openorbit.scrapers.nasa.NASAScraper"
        )
        
        # 2. Log a scrape run
        scrape_id = await log_scrape_run(
            conn,
            source_id=source_id,
            url="https://api.nasa.gov/launches?limit=10",
            http_status=200,
            content_type="application/json",
            payload='[{"name": "Falcon 9"}]'
        )
        
        # 3. Create an event
        event = LaunchEventCreate(
            name="Falcon 9 USSF-Delta Launch",
            launch_date=datetime(2025, 1, 22, 14, 30, 0, tzinfo=UTC),
            launch_date_precision="hour",
            provider="SpaceX",
            vehicle="Falcon 9",
            location="Kennedy Space Center",
            pad="LC-39A",
            launch_type="civilian",
            status="scheduled"
        )
        slug = await upsert_launch_event(conn, event)
        
        # 4. Link event to scrape source
        await add_attribution(conn, slug, scrape_id)
        
        # 5. Retrieve and display
        event = await get_launch_event_by_slug(conn, slug)
        print(f"Created: {event.name}")
        print(f"Confidence: {event.confidence_score}%")
        print(f"Sources: {event.attribution_count}")
    
    # Cleanup
    await close_db()
```

---

## See Also

- [Database Schema](./schema.md) — Table definitions and relationships
- [CLI Reference](../cli.md) — Database initialization command
- [Developer Guide](../development.md) — How to add new database functions
- [Pydantic Models](../../src/openorbit/models/db.py) — Model definitions
