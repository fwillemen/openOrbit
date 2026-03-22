# Database Schema

openOrbit uses SQLite for event persistence with a design that's forward-compatible with PostgreSQL. This document describes the complete schema, relationships, indexes, and migration strategies.

## Overview

The schema consists of four main tables:

1. **osint_sources** — Registry of OSINT scrapers and data sources
2. **raw_scrape_records** — Immutable audit trail of all scrape attempts
3. **launch_events** — Normalized, deduplicated launch event records
4. **event_attributions** — Many-to-many linking events to scrape sources

Additional features:
- **FTS5 Virtual Table** — Full-text search on launch event names
- **Triggers** — Automatic FTS5 index synchronization
- **Indexes** — Optimized queries for common filters

---

## Table Definitions

### osint_sources

Registry of OSINT data sources and scrapers.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Unique source identifier |
| `name` | TEXT | NOT NULL, UNIQUE | Human-readable source name (e.g., "NASA Official Feed") |
| `url` | TEXT | NOT NULL | Base URL of the data source |
| `scraper_class` | TEXT | NOT NULL | Python class path (e.g., "openorbit.scrapers.nasa.NASAScraper") |
| `enabled` | INTEGER | NOT NULL, DEFAULT 1 | Enable/disable flag (0 = disabled, 1 = enabled) |
| `last_scraped_at` | TEXT | NULL | ISO 8601 timestamp of last successful scrape |

**Indexes:**
- `idx_osint_sources_enabled` — Speed up queries filtering by enabled status

**Example:**
```sql
INSERT INTO osint_sources (name, url, scraper_class, enabled)
VALUES ('NASA Launches', 'https://api.nasa.gov/launches', 'openorbit.scrapers.nasa.NASAScraper', 1);
```

---

### raw_scrape_records

Immutable audit trail of all scrape attempts. Each row represents one HTTP request to a data source.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Unique scrape record identifier |
| `source_id` | INTEGER | NOT NULL, FK → osint_sources.id | Source being scraped |
| `scraped_at` | TEXT | NOT NULL | ISO 8601 timestamp when scrape occurred |
| `url` | TEXT | NOT NULL | Exact URL that was scraped |
| `http_status` | INTEGER | NULL | HTTP status code (200, 404, 500, etc.) |
| `content_type` | TEXT | NULL | MIME type of response (text/html, application/json) |
| `payload` | TEXT | NULL | Raw response body (HTML, JSON, or null if scrape failed) |
| `error_message` | TEXT | NULL | Error details if scrape failed |

**Indexes:**
- `idx_raw_scrape_records_source` — Speed up lookups by source and timestamp

**Relationships:**
- Foreign key constraint: `source_id` → `osint_sources(id)` with ON DELETE CASCADE

**Example:**
```sql
INSERT INTO raw_scrape_records (
    source_id, scraped_at, url, http_status, content_type, payload
) VALUES (
    1, '2025-01-22T14:30:00+00:00', 'https://api.nasa.gov/launches?limit=10',
    200, 'application/json', '[{"name": "Falcon 9 v1.0"}]'
);
```

---

### launch_events

Normalized, deduplicated launch event records. Each row represents a unique launch event with confidence scoring.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `slug` | TEXT | PRIMARY KEY | URL-safe unique identifier (e.g., "spacex-falcon9-2025-01-22") |
| `name` | TEXT | NOT NULL | Event name (e.g., "Falcon 9 USSF-Delta Launch") |
| `launch_date` | TEXT | NOT NULL | ISO 8601 timestamp (UTC) of launch |
| `launch_date_precision` | TEXT | NOT NULL, CHECK | Precision level: `second`, `minute`, `hour`, `day`, `month`, `year`, or `quarter` |
| `provider` | TEXT | NOT NULL | Launch provider (e.g., "SpaceX", "NASA", "ESA") |
| `vehicle` | TEXT | NULL | Launch vehicle (e.g., "Falcon 9", "Falcon Heavy") |
| `location` | TEXT | NULL | Launch location (e.g., "Kennedy Space Center", "Baikonur") |
| `pad` | TEXT | NULL | Launch pad identifier (e.g., "LC-39A", "SLC-40") |
| `launch_type` | TEXT | CHECK | Classification: `civilian`, `military`, or `unknown` |
| `status` | TEXT | NOT NULL, CHECK | Current status: `scheduled`, `delayed`, `launched`, `failed`, or `cancelled` |
| `confidence_score` | INTEGER | NOT NULL, DEFAULT 50, CHECK (0-100) | Confidence score (0-100) based on attribution count and date precision |
| `created_at` | TEXT | NOT NULL | ISO 8601 timestamp when record was created |
| `updated_at` | TEXT | NOT NULL | ISO 8601 timestamp of last update |

**Indexes:**
- `idx_launch_events_date` — Filter by launch date range
- `idx_launch_events_provider` — Filter by launch provider
- `idx_launch_events_status` — Filter by event status
- `idx_launch_events_type` — Filter by launch type

**Slug Generation:**

Slugs are auto-generated from provider + vehicle + launch_date with collision handling:

```
Format: {provider}-{vehicle}-{date_portion}
Example: spacex-falcon9-2025-01-22
         nasa-artemis-2025-Q2
         spacex-falcon9-2025-01-22-2  (collision variant)
```

**Confidence Score Calculation:**

```
Base Score = 50
+ Attribution Bonus:
    1 source   = +0
    2 sources  = +10
    3 sources  = +20
    4+ sources = +30
+ Precision Bonus:
    second     = +20
    minute     = +15
    hour       = +10
    day        = +5
    month      = 0
    year       = -5
    quarter    = -10

Final score clamped to 0-100
```

**Example:**
```sql
INSERT INTO launch_events (
    slug, name, launch_date, launch_date_precision, provider, vehicle,
    location, pad, launch_type, status, confidence_score, created_at, updated_at
) VALUES (
    'spacex-falcon9-2025-01-22', 'Falcon 9 USSF-Delta Launch',
    '2025-01-22T14:30:00+00:00', 'hour', 'SpaceX', 'Falcon 9',
    'Kennedy Space Center', 'LC-39A', 'civilian', 'scheduled', 65,
    '2025-01-20T10:00:00+00:00', '2025-01-20T10:00:00+00:00'
);
```

---

### event_attributions

Many-to-many linking table connecting launch events to their source attributions. Enables multi-source event confirmation.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Unique attribution identifier |
| `event_slug` | TEXT | NOT NULL, FK → launch_events.slug | Event being attributed |
| `scrape_record_id` | INTEGER | NOT NULL, FK → raw_scrape_records.id | Scrape record providing the attribution |
| `attributed_at` | TEXT | NOT NULL | ISO 8601 timestamp when attribution was made |

**Indexes:**
- `idx_event_attributions_unique` — Enforce one attribution per event/scrape pair
- `idx_event_attributions_event` — Speed up lookups by event

**Relationships:**
- Foreign key: `event_slug` → `launch_events(slug)` with ON DELETE CASCADE
- Foreign key: `scrape_record_id` → `raw_scrape_records(id)` with ON DELETE CASCADE

**Example:**
```sql
INSERT INTO event_attributions (event_slug, scrape_record_id, attributed_at)
VALUES ('spacex-falcon9-2025-01-22', 1, '2025-01-20T10:05:00+00:00');
```

---

## Full-Text Search (FTS5)

Launch events support full-text search via SQLite's FTS5 virtual table.

### Virtual Table Definition

```sql
CREATE VIRTUAL TABLE launch_events_fts USING fts5(
    slug UNINDEXED,
    name,
    content='launch_events',
    content_rowid='rowid'
);
```

**Columns:**
- `slug` — Event slug (UNINDEXED — not searchable, just for result identification)
- `name` — Event name (indexed for FTS5 search)

**Automatic Synchronization:**

Three triggers automatically keep the FTS5 index in sync with the main table:

1. **insert trigger** — Adds rows to FTS5 when events are created
2. **update trigger** — Updates FTS5 when event names change
3. **delete trigger** — Removes rows from FTS5 when events are deleted

### FTS5 Query Syntax

```sql
-- Simple phrase search
SELECT * FROM launch_events_fts WHERE name MATCH 'falcon'
  INNER JOIN launch_events e ON launch_events_fts.slug = e.slug;

-- Boolean operators
SELECT * FROM launch_events_fts WHERE name MATCH 'falcon AND 2025'
  INNER JOIN launch_events e ON launch_events_fts.slug = e.slug;

-- Phrase search
SELECT * FROM launch_events_fts WHERE name MATCH '"Falcon 9"'
  INNER JOIN launch_events e ON launch_events_fts.slug = e.slug;

-- Ranked by relevance
SELECT * FROM launch_events_fts
  INNER JOIN launch_events e ON launch_events_fts.slug = e.slug
  ORDER BY rank
  LIMIT 20;
```

---

## Relationships and Constraints

```
osint_sources (1) ──── (∞) raw_scrape_records
                              │
                              │ scrape_record_id
                              │
                        event_attributions
                              │
                              │ event_slug
                              │
                        (∞) launch_events (1)
```

**Cascade Behavior:**

- Deleting an OSINT source cascades deletion of all its scrape records
- Deleting scrape records cascades deletion of event attributions
- Deleting a launch event cascades deletion of all its attributions

This ensures referential integrity while maintaining audit trails (raw scrape records are immutable until their source is deleted).

---

## Performance Considerations

### Index Coverage

All commonly-filtered columns have indexes:

| Query Pattern | Index Used | Expected Cost |
|---------------|------------|---------------|
| `WHERE enabled = 1` | `idx_osint_sources_enabled` | O(log n) |
| `WHERE status = 'scheduled'` | `idx_launch_events_status` | O(log n) |
| `WHERE launch_date >= ? AND launch_date <= ?` | `idx_launch_events_date` | O(log n) |
| `WHERE provider = 'SpaceX'` | `idx_launch_events_provider` | O(log n) |
| `WHERE launch_type = 'civilian'` | `idx_launch_events_type` | O(log n) |
| FTS5 phrase search | `launch_events_fts` | O(log n) |

### Query Optimization Tips

1. **Use LIMIT for large result sets:**
   ```sql
   SELECT * FROM launch_events WHERE status = 'scheduled' LIMIT 100;
   ```

2. **Combine filters for range queries:**
   ```sql
   SELECT * FROM launch_events
   WHERE launch_date >= ? AND launch_date <= ? AND status = 'scheduled';
   ```

3. **Prefer slug lookup for single events:**
   ```sql
   SELECT * FROM launch_events WHERE slug = ? -- fastest (primary key)
   ```

4. **Use FTS5 for text search (not LIKE):**
   ```sql
   -- ✅ Fast
   SELECT * FROM launch_events_fts WHERE name MATCH 'falcon' ...
   
   -- ❌ Slow (full table scan)
   SELECT * FROM launch_events WHERE name LIKE '%falcon%' ...
   ```

---

## Migration to PostgreSQL

This schema is designed to be PostgreSQL-compatible. Migration steps:

### 1. Type Mappings

| SQLite | PostgreSQL |
|--------|-----------|
| INTEGER PRIMARY KEY AUTOINCREMENT | BIGSERIAL PRIMARY KEY |
| TEXT | VARCHAR or TEXT |
| INTEGER (boolean) | BOOLEAN (use 0/1 literals or cast) |
| TEXT (ISO 8601) | TIMESTAMP WITH TIME ZONE |

### 2. FTS Migration

SQLite FTS5 → PostgreSQL full-text search options:

**Option A: Built-in GIN indexes**
```sql
CREATE TABLE launch_events (
    ...
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', name)
    ) STORED
);

CREATE INDEX idx_launch_events_search ON launch_events USING gin(search_vector);
```

**Option B: Continue using FTS5 compatibility layer** (recommended for minimal migration effort)

### 3. Trigger Portability

SQLite triggers → PostgreSQL triggers:

```sql
-- PostgreSQL equivalent
CREATE OR REPLACE FUNCTION sync_launch_events_fts_insert()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO launch_events_fts(slug, name) VALUES (NEW.slug, NEW.name);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER launch_events_fts_insert
AFTER INSERT ON launch_events
FOR EACH ROW
EXECUTE FUNCTION sync_launch_events_fts_insert();
```

### 4. Test Plan

```bash
# 1. Export SQLite schema
sqlite3 openorbit.db .schema > sqlite_schema.sql

# 2. Create equivalent PostgreSQL schema
psql -U postgres < postgresql_schema.sql

# 3. Migrate data (using pg_restore or custom ETL)
# 4. Run integration tests against PostgreSQL
# 5. Verify indexes and performance
```

---

## Examples

### Creating a Launch Event

```python
from openorbit.models.db import LaunchEventCreate
from openorbit.db import upsert_launch_event

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
# Returns: "spacex-falcon9-2025-01-22"
```

### Querying Events with Filters

```python
from openorbit.db import get_launch_events

events = await get_launch_events(
    conn,
    date_from="2025-01-01T00:00:00+00:00",
    date_to="2025-12-31T23:59:59+00:00",
    provider="SpaceX",
    status="scheduled",
    limit=50
)
```

### Full-Text Search

```python
from openorbit.db import search_launch_events

results = await search_launch_events(conn, query="falcon AND 2025", limit=20)
```

### Adding Event Attribution

```python
from openorbit.db import add_attribution

# Link an event to a scrape record
attribution_id = await add_attribution(
    conn,
    event_slug="spacex-falcon9-2025-01-22",
    scrape_record_id=42
)
# Confidence score automatically recalculated
```

---

## Backup and Recovery

### Manual Backup

```bash
sqlite3 openorbit.db ".dump" > openorbit_backup.sql
```

### Restore from Backup

```bash
sqlite3 openorbit_new.db < openorbit_backup.sql
```

### Automated Backups

```bash
# Daily backup (example cron job)
0 2 * * * sqlite3 /path/to/openorbit.db ".dump" > /backups/openorbit_$(date +\%Y-\%m-\%d).sql
```

---

## See Also

- [API Reference](../api/database.md) — Repository function documentation
- [CLI Reference](../cli.md) — Database initialization command
- [Developer Guide](../development.md) — How to work with the repository layer
