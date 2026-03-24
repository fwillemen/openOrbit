-- OpenOrbit Database Schema
-- SQLite schema for launch event tracking with multi-source attribution
-- Compatible with SQLite 3.x; PostgreSQL migration planned for future

-- =============================================================================
-- OSINT Sources (Data Source Registry)
-- =============================================================================
CREATE TABLE IF NOT EXISTS osint_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    scraper_class TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,  -- 0 = disabled, 1 = enabled
    last_scraped_at TEXT  -- ISO 8601 timestamp (nullable)
);

CREATE INDEX IF NOT EXISTS idx_osint_sources_enabled 
ON osint_sources(enabled);

-- =============================================================================
-- Raw Scrape Records (Immutable Audit Trail)
-- =============================================================================
CREATE TABLE IF NOT EXISTS raw_scrape_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    scraped_at TEXT NOT NULL,  -- ISO 8601 timestamp
    url TEXT NOT NULL,
    http_status INTEGER,  -- HTTP status code (200, 404, etc.)
    content_type TEXT,  -- MIME type (text/html, application/json)
    payload TEXT,  -- Raw HTML/JSON content (nullable if scrape failed)
    error_message TEXT,  -- Error details if scrape failed
    FOREIGN KEY (source_id) REFERENCES osint_sources(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_raw_scrape_records_source 
ON raw_scrape_records(source_id, scraped_at DESC);

-- =============================================================================
-- Launch Events (Normalized, Deduplicated Launch Records)
-- =============================================================================
CREATE TABLE IF NOT EXISTS launch_events (
    slug TEXT PRIMARY KEY,  -- URL-safe unique identifier (e.g., 'spacex-falcon9-2025-01-22')
    name TEXT NOT NULL,
    launch_date TEXT NOT NULL,  -- ISO 8601 timestamp (UTC)
    launch_date_precision TEXT NOT NULL CHECK (
        launch_date_precision IN ('second', 'minute', 'hour', 'day', 'month', 'year', 'quarter')
    ),
    provider TEXT NOT NULL,  -- Launch provider (e.g., 'SpaceX', 'NASA')
    vehicle TEXT,  -- Launch vehicle (e.g., 'Falcon 9', nullable)
    location TEXT,  -- Launch location (e.g., 'Kennedy Space Center', nullable)
    pad TEXT,  -- Launch pad (e.g., 'LC-39A', nullable)
    launch_type TEXT CHECK (launch_type IN ('civilian', 'military', 'unknown')),
    status TEXT NOT NULL CHECK (
        status IN ('scheduled', 'delayed', 'launched', 'failed', 'cancelled')
    ),
    confidence_score INTEGER NOT NULL DEFAULT 50 CHECK (
        confidence_score BETWEEN 0 AND 100
    ),
    created_at TEXT NOT NULL,  -- ISO 8601 timestamp
    updated_at TEXT NOT NULL   -- ISO 8601 timestamp
);

CREATE INDEX IF NOT EXISTS idx_launch_events_date 
ON launch_events(launch_date);

CREATE INDEX IF NOT EXISTS idx_launch_events_provider 
ON launch_events(provider);

CREATE INDEX IF NOT EXISTS idx_launch_events_status 
ON launch_events(status);

CREATE INDEX IF NOT EXISTS idx_launch_events_type 
ON launch_events(launch_type);

-- =============================================================================
-- Event Attributions (Many-to-Many: Events ↔ Scrape Records)
-- =============================================================================
CREATE TABLE IF NOT EXISTS event_attributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_slug TEXT NOT NULL,
    scrape_record_id INTEGER NOT NULL,
    attributed_at TEXT NOT NULL,  -- ISO 8601 timestamp
    FOREIGN KEY (event_slug) REFERENCES launch_events(slug) ON DELETE CASCADE,
    FOREIGN KEY (scrape_record_id) REFERENCES raw_scrape_records(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_event_attributions_unique 
ON event_attributions(event_slug, scrape_record_id);

CREATE INDEX IF NOT EXISTS idx_event_attributions_event 
ON event_attributions(event_slug);

-- =============================================================================
-- Full-Text Search Index (SQLite FTS5)
-- =============================================================================
CREATE VIRTUAL TABLE IF NOT EXISTS launch_events_fts USING fts5(
    slug UNINDEXED, 
    name, 
    content='launch_events', 
    content_rowid='rowid'
);

-- =============================================================================
-- API Keys (Authentication)
-- =============================================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL,   -- PBKDF2-SHA256 hex digest
    salt TEXT NOT NULL,       -- Hex-encoded random salt (64 chars)
    is_admin INTEGER NOT NULL DEFAULT 0,  -- 1 = admin, 0 = read-only
    created_at TEXT NOT NULL,  -- ISO 8601 timestamp
    revoked_at TEXT            -- NULL while active; set on revocation
);

CREATE INDEX IF NOT EXISTS idx_api_keys_revoked
ON api_keys(revoked_at);


CREATE TRIGGER IF NOT EXISTS launch_events_fts_insert 
AFTER INSERT ON launch_events 
BEGIN 
    INSERT INTO launch_events_fts(rowid, slug, name) 
    VALUES (new.rowid, new.slug, new.name); 
END;

CREATE TRIGGER IF NOT EXISTS launch_events_fts_update 
AFTER UPDATE ON launch_events 
BEGIN 
    UPDATE launch_events_fts 
    SET name = new.name 
    WHERE rowid = old.rowid; 
END;

CREATE TRIGGER IF NOT EXISTS launch_events_fts_delete 
AFTER DELETE ON launch_events 
BEGIN 
    DELETE FROM launch_events_fts 
    WHERE rowid = old.rowid; 
END;
