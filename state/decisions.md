# Architecture Decision Records (ADRs)

> **Auto-updated by:** Architect agent  
> **Status:** 5 decisions recorded.

---

### ADR-001: Use src/ Layout with uv for Package Management

**Status:** Accepted  
**Date:** 2025-01-22  
**Sprint Item:** PO-001

**Context:**  
Python projects can be structured with either flat layout (package at root) or src/ layout (package under src/). We need modern, reproducible dependency management for a production API service that will be containerized. The project must follow best practices for isolation, testing, and deployment.

**Decision:**  
Adopt the src/ layout with the package at `project/src/openorbit/`. Use `uv` as the sole package manager (never `pip` directly). All dependencies declared in `pyproject.toml`. This enforces proper import hygiene, prevents accidental imports of non-packaged code, and aligns with modern Python packaging standards.

**Consequences:**  
- ✅ Clean separation between source and tests
- ✅ Import paths are explicit and match production
- ✅ `uv` provides fast, reproducible installs with lock file
- ✅ Easier to catch import errors before deployment
- ❌ Slightly more verbose project structure
- ❌ Developers must use `uv sync` instead of `pip install`

---

### ADR-002: Environment-First Configuration (12-Factor App)

**Status:** Accepted  
**Date:** 2025-01-22  
**Sprint Item:** PO-001

**Context:**  
The system must be Docker-compatible and deployable across dev/staging/prod environments. Hard-coded configuration or file-based config creates deployment friction and security risks (secrets in version control). The API will need database URLs, external API keys, and runtime settings that vary by environment.

**Decision:**  
All configuration via environment variables with sensible defaults. Use Pydantic `BaseSettings` for typed, validated configuration. Provide `.env.example` documenting all variables but never commit `.env` to git. No config files for environment-specific settings.

**Consequences:**  
- ✅ Docker-friendly (pass env vars at runtime)
- ✅ No secrets in version control
- ✅ Type-safe configuration with validation
- ✅ Easy to override in CI/CD pipelines
- ❌ Requires discipline to document new env vars
- ❌ Slightly harder to see "all settings" at a glance

---

### ADR-003: FastAPI with Async SQLite (aiosqlite)

**Status:** Accepted  
**Date:** 2025-01-22  
**Sprint Item:** PO-001

**Context:**  
Need a production-ready REST API framework. The system will handle I/O-bound operations (HTTP scraping, database queries). SQLite is sufficient for initial scale and simplifies deployment (no external DB server). Sync SQLite would block the event loop during queries.

**Decision:**  
Use FastAPI for REST API (modern, async-native, auto-docs, type validation). Use aiosqlite for async SQLite access to avoid blocking. Structure API routes under `src/openorbit/api/` as modules. Use FastAPI dependency injection for DB connections and config.

**Consequences:**  
- ✅ High-performance async I/O
- ✅ Auto-generated OpenAPI docs
- ✅ Type validation with Pydantic
- ✅ SQLite = zero external dependencies
- ✅ Easy migration to PostgreSQL later (swap aiosqlite for asyncpg)
- ❌ Slightly more complex than sync code (await everywhere)
- ❌ SQLite has concurrency limits (acceptable for v1)

---

### ADR-004: Structured Logging with JSON Output

**Status:** Accepted  
**Date:** 2025-01-22  
**Sprint Item:** PO-001

**Context:**  
Production services need structured, parseable logs for debugging and monitoring. Console logs with print() are not sufficient. Need correlation IDs for requests, log levels, timestamps, and context. Logs should be machine-readable for aggregation tools (e.g., CloudWatch, Datadog).

**Decision:**  
Use Python's `logging` module with `structlog` for structured JSON output. Configure via `config.py` with LOG_LEVEL from environment. Include request IDs via FastAPI middleware. Default to JSON output in production, pretty console output in dev.

**Consequences:**  
- ✅ Structured logs are searchable and parseable
- ✅ Request tracing with correlation IDs
- ✅ Standard log levels (DEBUG, INFO, WARNING, ERROR)
- ✅ Works with log aggregation tools
- ❌ Slightly more verbose setup than basic logging
- ❌ JSON logs less readable for humans (but dev mode fixes this)

---

### ADR-005: Modular Package Structure by Domain

**Status:** Accepted  
**Date:** 2025-01-22  
**Sprint Item:** PO-001

**Context:**  
The system will grow to include multiple data sources, scrapers, API endpoints, and models. Need clear separation of concerns for maintainability. Different team members (or agents) should be able to work on different modules without conflicts.

**Decision:**  
Organize code by domain concern:
- `openorbit/config.py` → configuration
- `openorbit/db.py` → database connection lifecycle
- `openorbit/api/` → FastAPI routes (health, launches, etc.)
- `openorbit/scrapers/` → OSINT scraper modules (one per source)
- `openorbit/models/` → Pydantic models and DB schemas
- `openorbit/main.py` → FastAPI app initialization

Each module is self-contained. API routes import models and scrapers as needed.

**Consequences:**  
- ✅ Clear boundaries between concerns
- ✅ Easy to add new scrapers without touching core logic
- ✅ Testable modules (mock dependencies)
- ✅ Supports parallel development
- ❌ More files/folders than a monolithic design
- ❌ Requires discipline to avoid circular imports

---

### ADR-006: Core Database Schema with Multi-Source Attribution

**Status:** Accepted  
**Date:** 2025-01-22  
**Sprint Item:** PO-002

**Context:**  
The system must aggregate launch event data from multiple OSINT sources and handle deduplication, source attribution, and confidence scoring. Data may conflict across sources (different dates, names, etc.). We need to preserve raw scrape data for audit/replay while maintaining a normalized, deduplicated view of launch events. The schema must be PostgreSQL-compatible for future migration but start with SQLite.

**Decision:**  
Design a four-table schema:

1. **osint_sources** — Registry of data sources (scrapers)
2. **raw_scrape_records** — Immutable audit log of every scrape (HTML/JSON payload)
3. **launch_events** — Normalized, deduplicated launch event records
4. **event_attributions** — Many-to-many link between events and source records

**Schema design principles:**
- Separate concerns: raw data (audit) vs. normalized data (query)
- Multi-source attribution: one event can have many sources
- Confidence scoring: 0-100 integer (higher = more certain; computed from source count + date precision)
- Date precision tracking: second/minute/hour/day/month/year/quarter
- Full-text search support: FTS5 virtual table for event names/descriptions
- PostgreSQL compatibility: use standard types (TEXT, INTEGER, REAL), avoid SQLite-specific features

**Consequences:**  
- ✅ Clean separation of raw vs. normalized data
- ✅ Audit trail for every scrape run
- ✅ Multi-source deduplication with attribution
- ✅ Confidence scoring based on evidence strength
- ✅ Fast text search on event names
- ✅ Easy PostgreSQL migration path
- ❌ Slightly more complex than single-table design
- ❌ Deduplication logic required in application layer (future work)

---

### ADR-007: Async Repository Pattern with Typed Helpers

**Status:** Accepted  
**Date:** 2025-01-22  
**Sprint Item:** PO-002

**Context:**  
Need a clean abstraction layer between raw SQL and application code. Multiple modules (scrapers, API handlers) will query and update launch events. Direct SQL in every module leads to code duplication, SQL injection risks, and hard-to-test code. FastAPI is async-native, so blocking DB calls would harm performance.

**Decision:**  
Implement an async repository pattern in `db.py` with typed helper functions:
- `upsert_launch_event()` — Insert or update a launch event
- `get_launch_events()` — Query events with filters (date range, provider, status)
- `get_launch_event_by_id()` / `get_launch_event_by_slug()` — Single event retrieval
- `add_attribution()` — Link an event to a source scrape
- `log_scrape_run()` — Record a raw scrape payload
- `register_osint_source()` / `get_osint_sources()` — Manage source registry

All functions use Pydantic models for input/output (type-safe). Queries use parameterized SQL (safe from injection). Transaction support via context managers.

**Consequences:**  
- ✅ Type-safe database access (Pydantic validation)
- ✅ DRY principle (no SQL duplication)
- ✅ Testable in isolation (mock connection)
- ✅ SQL injection protection (parameterized queries)
- ✅ Async-native (no event loop blocking)
- ❌ Slight overhead vs. raw SQL
- ❌ Requires Pydantic models for all DB entities

---

### ADR-008: Database Initialization via CLI Command

**Status:** Accepted  
**Date:** 2025-01-22  
**Sprint Item:** PO-002

**Context:**  
Database schema must be initialized before the app starts. Need a repeatable, idempotent way to create tables. Docker containers and CI/CD pipelines need deterministic setup. Developers need a simple command to reset their local DB.

**Decision:**  
Add a `__main__.py` entry point to `openorbit.db` module that supports:
```bash
uv run python -m openorbit.db init
```

The `init` command reads `schema.sql` from the package and executes it. Uses `CREATE TABLE IF NOT EXISTS` for idempotency. Safe to run multiple times. Future migrations will extend this with versioned migration support (alembic or similar).

**Consequences:**  
- ✅ Simple, documented setup process
- ✅ Docker-friendly (run in entrypoint)
- ✅ Idempotent (safe to re-run)
- ✅ Version control for schema (schema.sql in git)
- ❌ No automatic migration support yet (manual for now)
- ❌ Requires uv to be available

---

### ADR-009: Event Deduplication Strategy (Slug-Based)

**Status:** Accepted  
**Date:** 2025-01-22  
**Sprint Item:** PO-002

**Context:**  
Multiple OSINT sources will report the same launch event with slight variations in naming (e.g., "Falcon 9" vs "Falcon 9 Block 5", "SpaceX" vs "SpaceX Corp"). Need a deterministic way to identify duplicates without relying on external IDs (which sources don't share). Human-readable URLs for the API require stable identifiers.

**Decision:**  
Use **slug-based deduplication**:
- Generate a slug from (provider + vehicle + launch_date) → `spacex-falcon9-2025-01-22`
- Slug is a TEXT PRIMARY KEY on launch_events
- Scrapers normalize provider/vehicle names before upserting
- Slug collision (same provider+vehicle on same day) → add a suffix: `-2`, `-3`
- API URLs: `/api/launches/{slug}` instead of numeric IDs

Confidence score increases when multiple sources agree on the same event (matched by slug).

**Consequences:**  
- ✅ Deterministic deduplication (same inputs → same slug)
- ✅ Human-readable API URLs
- ✅ Multi-source attribution boosts confidence
- ✅ No dependency on external IDs
- ❌ Slug collisions possible (handled by suffix)
- ❌ Provider/vehicle name normalization required (future work)
- ❌ Slug changes if core facts change (acceptable tradeoff)

---

## Template

### ADR-001: [Short title]

**Status:** Proposed | Accepted | Deprecated  
**Date:** YYYY-MM-DD

**Context:**  
[Describe the situation and problem being addressed.]

**Decision:**  
[State the decision clearly.]

**Consequences:**  
[What becomes easier or harder as a result?]

---

*ADRs will be added here by the Architect agent as design decisions are made.*
