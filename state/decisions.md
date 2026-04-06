# Architecture Decision Records (ADRs)

> **Auto-updated by:** Architect agent  
> **Status:** 13 decisions recorded.

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

### ADR-010: Async HTTP Scraper Pattern with Launch Library 2 API

**Status:** Accepted  
**Date:** 2026-03-22  
**Sprint Item:** PO-003

**Context:**  
Sprint item PO-003 requires the first production OSINT scraper targeting public space agency launch schedules. The system must fetch external data, respect rate limits, store raw responses for audit, parse into normalized events, and handle idempotent re-runs. We need a pattern that can be extended for future scrapers (military schedules, social media, news sites). The scraper must integrate with the existing async architecture (FastAPI + aiosqlite) and repository functions.

**Decision:**  
Implement scraper pattern with these design choices:

1. **Data Source:** Launch Library 2 API (https://ll.thespacedevs.com/2.2.0/)
   - Well-documented, free tier, no authentication
   - JSON responses (easier to parse than HTML)
   - Rich metadata: provider, vehicle, location, status, precision timestamps
   - Upcoming launches endpoint: `/launch/upcoming/`
   - Pagination support via `?limit=N&offset=N`

2. **Scraper Architecture:**
   - Base class: `BaseScraper` (abstract protocol for future scrapers)
   - Concrete implementation: `SpaceAgencyScraper` in `scrapers/space_agency.py`
   - Use `httpx.AsyncClient` for async HTTP (matches FastAPI async architecture)
   - Configurable timeout (30s default), max retries (3 default)
   - Exponential backoff: 2^attempt seconds between retries

3. **Rate Limiting:**
   - Respect `SCRAPER_DELAY_SECONDS` config (default: 2s)
   - Use `asyncio.sleep()` between requests
   - Add User-Agent header identifying openOrbit

4. **Parsing Strategy:**
   - LL2 JSON → LaunchEventCreate Pydantic model
   - Field mappings:
     - `name` ← `name` (string)
     - `launch_date` ← `net` (NET = "No Earlier Than" timestamp)
     - `launch_date_precision` ← inferred from `net_precision` (0=year, 1=month, ..., 7=second)
     - `provider` ← `launch_service_provider.name`
     - `vehicle` ← `rocket.configuration.name`
     - `location` ← `pad.location.name`
     - `pad` ← `pad.name`
     - `status` ← `status.name` (map "Go for Launch" → "scheduled", "Success" → "launched", etc.)
     - `launch_type` ← default to "civilian" (LL2 doesn't distinguish military)

5. **Error Handling:**
   - Network errors: log to `raw_scrape_records` with error_message
   - HTTP errors (4xx/5xx): log raw response + status code
   - Parse errors: log warning, skip malformed record, continue
   - All errors are non-fatal (scraper continues processing valid records)

6. **Workflow:**
   ```
   1. Register source (if not exists): register_osint_source()
   2. Fetch data: httpx.get() with timeout + retries
   3. Log raw response: log_scrape_run() → scrape_record_id
   4. Parse JSON: List[dict] → List[LaunchEventCreate]
   5. For each event:
      a. upsert_launch_event() → slug
      b. add_attribution(slug, scrape_record_id)
   6. Update source last_scraped: update_source_last_scraped()
   7. Return summary: {total: N, new: N, updated: N}
   ```

7. **CLI Interface:**
   - Runnable as: `uv run python -m openorbit.scrapers.space_agency`
   - Uses `asyncio.run(main())` pattern
   - Prints human-readable summary to stdout
   - Non-zero exit code on critical failure (HTTP timeout, DB unavailable)

8. **Extensibility (future-proofing):**
   - `BaseScraper` protocol defines interface: `fetch()`, `parse()`, `run()`
   - Config variables scoped by source: `SCRAPER_DELAY_SECONDS`, `SCRAPER_TIMEOUT_SECONDS`
   - Future scrapers subclass BaseScraper and implement `parse()`
   - Shared retry logic and rate limiting in base class

**Consequences:**  
- ✅ Clean, testable scraper pattern
- ✅ Rich data source (LL2 API provides high-quality metadata)
- ✅ Idempotent re-runs (upsert logic handles duplicates)
- ✅ Full audit trail (raw responses stored before parsing)
- ✅ Async-native (no event loop blocking)
- ✅ Easy to extend for future sources
- ✅ Respects rate limits (good netizen behavior)
- ❌ LL2 API has rate limits (100 req/hour on free tier) — acceptable for v1
- ❌ No military launch detection yet (requires different source)
- ❌ Dependency on external API availability (mitigated by retry logic)

---

### ADR-011: Data Normalization Pipeline & Canonical LaunchEvent Model

**Status:** Accepted  
**Date:** 2025-07-14

**Context:**  
Raw data ingested by scrapers arrives in heterogeneous formats: ISO 8601 strings, `YYYY-MM-DD`
date-only strings, `Month DD, YYYY` human-readable dates, and Unix timestamps. Provider names
vary across sources (e.g., "Space Exploration Technologies" vs "SpaceX"). Launch pad names do
not consistently include geolocation. Without a normalization layer, the DB accumulates
inconsistent records that are difficult to query and deduplicate reliably.

The existing `openorbit.models.db.LaunchEvent` represents the *database read model* (slug,
created_at, confidence_score). We need a separate *canonical domain model* that:
1. Carries validated, typed fields (not raw strings)
2. Is the authoritative shape passed from scraper → pipeline → DB write
3. Isolates parsing failures before they pollute the database

**Decision:**  
Introduce a `pipeline/` sub-package with three new files and a separate canonical Pydantic v2
model:

1. **`src/openorbit/models/launch_event.py`** — Canonical `LaunchEvent` Pydantic v2 model
   - `launch_date: datetime` with `@field_validator` that accepts ISO 8601, `YYYY-MM-DD`,
     `Month DD, YYYY`, and Unix timestamp (int/float) inputs
   - `confidence_score: int` validated to be in range 0–100
   - `launch_type: Literal["civilian", "military", "unknown"]` field validator normalizing
     common aliases ("commercial" → "civilian", etc.)
   - Clearly docstring-separated from the DB model in `models/db.py`

2. **`src/openorbit/pipeline/__init__.py`** — empty init exposing `normalize` and `NormalizationError`

3. **`src/openorbit/pipeline/exceptions.py`** — `NormalizationError(ValueError)` custom exception

4. **`src/openorbit/pipeline/aliases.py`** — two lookup tables:
   - `PROVIDER_ALIASES: dict[str, str]` mapping variant names → canonical names (≥10 entries)
   - `PAD_LOCATIONS: dict[str, dict]` mapping pad names → `{"lat": float, "lon": float,
     "location": str}` (≥10 entries covering KSC, Vandenberg, Baikonur, etc.)

5. **`src/openorbit/pipeline/normalizer.py`** — `normalize(raw: dict, source: str) -> LaunchEvent`
   - Resolves provider name via `PROVIDER_ALIASES`
   - Enriches lat/lon from `PAD_LOCATIONS` keyed on `pad` field
   - Passes cleaned dict to canonical `LaunchEvent(**cleaned)`; Pydantic validators handle
     date parsing
   - On `ValidationError` or any parse failure: raises `NormalizationError` with the original
     exception chained; caller is responsible for flagging `parse_error = 1` in DB

6. **DB schema addition** — add `parse_error INTEGER NOT NULL DEFAULT 0` column to
   `raw_scrape_records` via `ALTER TABLE` in `init_db_schema()` (safe: `IF NOT EXISTS`
   equivalent via `PRAGMA table_info` check or `ALTER TABLE … ADD COLUMN` which is idempotent
   in SQLite when column doesn't exist). A helper `flag_parse_error(scrape_record_id: int)`
   is added to `db.py`.

**Why separate canonical model vs DB model?**  
The DB `LaunchEvent` (read model) has `slug`, `created_at`, `attribution_count` — fields that
only exist *after* DB insertion. The canonical model is the *write input*: it is fully
validated before touching the DB. Keeping them separate avoids circular dependencies and makes
each model testable in isolation.

**Error handling contract:**  
- `NormalizationError` is caught by the scraper's run loop
- The scraper logs the error and calls `flag_parse_error(scrape_record_id)` so raw records are
  never silently dropped
- Failed records remain in `raw_scrape_records` with `parse_error = 1` for later reprocessing
  or manual inspection

**Consequences:**  
- ✅ Single, validated entry point for all incoming launch data
- ✅ Date parsing failures surface early with descriptive messages
- ✅ Provider/pad normalization is centrally maintained in `aliases.py`
- ✅ Zero silent data loss — every raw record is flagged on failure
- ✅ 90%+ unit test coverage is straightforward (pure functions, no I/O)
- ✅ Canonical model decoupled from DB model — each evolves independently
- ❌ Aliases table requires manual curation as new sources are added
- ❌ Altering `raw_scrape_records` requires care for existing databases (mitigated by SQLite's
  `ADD COLUMN` being additive and non-destructive)

---

### ADR-012: REST API — Core Launch Listing & Detail Endpoints (PO-005)

**Status:** Accepted  
**Date:** 2025-07-14  
**Sprint Item:** PO-005

**Context:**  
The openOrbit API needs public-facing REST endpoints for consumers to browse and retrieve launch
events. The DB layer (`get_launch_events`, `get_launch_event_by_slug`, `get_event_attributions`)
is already implemented. What is missing is:
1. A FastAPI router mounted at `/v1/launches` with list and detail endpoints
2. Dedicated response Pydantic models (separate from DB models) for the API contract
3. Pagination metadata (`total`, `page`, `per_page`) requiring a count query not yet in `db.py`
4. ASGI lifespan integration tests (needed to close the main.py coverage gap from 54%)

The existing health router in `api/health.py` is mounted directly at `/health`; v1 endpoints
must be namespaced under `/v1` to allow future versioning.

**Decision:**  

**1. New package `src/openorbit/api/v1/`**  
- `__init__.py` — exports `router` (an `APIRouter(prefix="/v1", tags=["launches"])`)
- `launches.py` — implements `GET /v1/launches` and `GET /v1/launches/{slug}`

**2. New module `src/openorbit/models/api.py` — API response models**  
Three Pydantic v2 models form the response contract, kept strictly separate from DB and pipeline
models to avoid coupling:
- `AttributionResponse` — `source_name: str`, `scraped_at: datetime`, `url: str`
- `LaunchEventResponse` — full detail model used by both list and detail endpoints:
  `slug`, `name`, `launch_date`, `launch_date_precision`, `provider`, `vehicle`, `location`,
  `pad`, `launch_type`, `status`, `confidence_score`, `attribution_count`, `created_at`,
  `updated_at`, `sources: list[AttributionResponse]`
- `PaginatedLaunchResponse` — envelope: `data: list[LaunchEventResponse]`,
  `meta: PaginationMeta` where `PaginationMeta` carries `total`, `page`, `per_page`

**3. New DB helper `count_launch_events` in `db.py`**  
Accepts the same filter parameters as `get_launch_events` (date_from, date_to, provider, status,
launch_type) and returns an `int`. This is the only DB change. The existing `get_launch_events`
signature is unchanged but its `limit`/`offset` parameters are used directly by the router.

**4. Query parameter validation via `fastapi.Query()`**  
All optional filters use `Query(None)` with explicit type annotations:
- `from_date: str | None = Query(None, alias="from")` — ISO 8601 date string
- `to_date: str | None = Query(None, alias="to")` — ISO 8601 date string
- `provider: str | None = Query(None)`
- `launch_type: Literal["civilian", "military", "public_report", "unknown"] | None = Query(None)`
- `status: Literal["scheduled", "success", "failure", "unknown"] | None = Query(None)`
- `page: int = Query(1, ge=1)`
- `per_page: int = Query(25, ge=1, le=100)`

FastAPI auto-generates 422 for invalid enum values. The `from`/`to` aliases are needed because
`from` is a Python keyword; FastAPI's `Query(alias=...)` handles this cleanly.

**5. Error responses**  
- `GET /v1/launches/{slug}` returns HTTP 404 `{"error": "not_found"}` when slug is absent
- Standard FastAPI 422 for malformed query params (automatic)

**6. Router mounting in `main.py`**  
`app.include_router(v1_router)` added to `create_app()` after the health router. The v1 router
carries `prefix="/v1"` internally so `main.py` imports it cleanly.

**7. ASGI lifespan integration test**  
`tests/test_api_launches.py` uses `httpx.AsyncClient` with `ASGITransport(app=app)` and
`lifespan="auto"` from `httpx_asgi` (or equivalent). This exercises the startup/shutdown
path in `main.py`, closing the 54% coverage gap. The test module-level fixture initialises
an in-memory SQLite DB via `aiosqlite` and seeds test data, then runs the full ASGI app.

**Why not nest `sources` in the list endpoint?**  
Fetching attributions for every event in a list of 25 requires N+1 DB queries. The list
endpoint returns `sources: []` (empty) for list items; sources are only populated on the
detail endpoint. This avoids a JOIN explosion without requiring eager loading infrastructure.
Alternatively the detail endpoint fetches attributions in a single separate query after the
main event query.

**Why a separate `models/api.py`?**  
- DB models (`models/db.py`) contain DB-side fields (`attribution_count`, raw `status` literals)
  that do not perfectly match the API contract
- Pipeline models (`models/launch_event.py`) are write-side input shapes
- API response models are the stable external contract; decoupling allows each layer to evolve
  independently and avoids polluting the public API with DB internals

**Consequences:**  
- ✅ Clean versioned URL space (`/v1/`) supports future `/v2/` without breaking changes
- ✅ Pagination implemented correctly with total count, not cursor-based (simple for OSINT use)
- ✅ ASGI lifespan tests close the main.py coverage gap and exercise DB init/teardown
- ✅ FastAPI auto-docs at `/docs` and `/redoc` work immediately via `Query()` annotations
- ✅ Attribution N+1 avoided in list; detail endpoint pays exactly 2 queries (event + sources)
- ❌ `count_launch_events` adds a second DB query on every list request (acceptable at this scale)
- ❌ `sources: []` in list items may confuse consumers who expect attribution data in lists
  (mitigated by clear OpenAPI descriptions on both endpoints)

---

### ADR-012: SpaceAgencyScraper Calls normalize() Pipeline

**Status:** Accepted  
**Date:** 2025-01-31

**Context:**  
PO-004 implemented the normalization pipeline (`openorbit.pipeline.normalize`). However,
`SpaceAgencyScraper` was built in ADR-010 before the pipeline existed and directly constructs
`LaunchEventCreate` objects from raw LL2 JSON without passing through `normalize()`. PO-006
requires commercial scrapers to call `normalize()` — this ADR records the decision not to
retrofit `SpaceAgencyScraper` now, to avoid scope creep in the current sprint.

**Decision:**  
`SpaceAgencyScraper` retains its direct-construction pattern for this sprint. The
`CommercialLaunchScraper` introduced in PO-006 will call `normalize()` as the reference
implementation. Retrofitting `SpaceAgencyScraper` is deferred to a future tech-debt sprint item.

**Consequences:**  
- ✅ PO-006 scope is contained; no unplanned changes to PO-004 deliverables
- ✅ `CommercialLaunchScraper` serves as the authoritative example of the normalize() contract
- ❌ Two scraper patterns coexist temporarily; `SpaceAgencyScraper` skips provider aliasing

---

### ADR-013: Commercial Launch Provider Scraper via LL2 Provider Filter

**Status:** Accepted  
**Date:** 2025-01-31

**Context:**  
PO-006 requires scraping ≥2 commercial launch providers (SpaceX and Rocket Lab). Options
considered:

1. **Direct HTML scraping** — SpaceX's public manifest and Rocket Lab's launch page have
   inconsistent HTML structures subject to frequent layout changes, making parsing fragile.
2. **Provider-specific JSON APIs** — RocketLaunch.Live and SpaceLaunchNow require registration
   or have usage constraints; maintenance burden is high.
3. **Launch Library 2 API with `lsp__name` filter** — LL2 already covers all commercial
   providers with the same JSON schema used by `SpaceAgencyScraper`. Free, no auth, stable API.

**Decision:**  
`CommercialLaunchScraper` in `project/src/openorbit/scrapers/commercial.py` uses the LL2
`/launch/upcoming/` endpoint with an `lsp__name` query parameter to filter by provider. A
class-level `PROVIDERS` list enumerates supported providers:

```python
PROVIDERS = [
    {"name": "SpaceX",      "ll2_filter": "SpaceX"},
    {"name": "Rocket Lab",  "ll2_filter": "Rocket Lab USA"},
]
```

For each provider the scraper:
1. Registers a distinct `osint_source` row (name = `"LL2 Commercial – <ProviderName>"`).
2. Fetches `GET /launch/upcoming/?lsp__name=<filter>&limit=100` via `httpx.AsyncClient`.
3. Stores raw JSON in `raw_scrape_records`.
4. Calls `normalize(raw_dict, source=source_name)` from `openorbit.pipeline` on each event —
   the pipeline resolves provider aliases and enriches lat/lon from `PAD_LOCATIONS`.
5. Calls `upsert_launch_event()` + `add_attribution()` idempotently.
6. Sleeps `SCRAPER_DELAY_SECONDS` between provider requests to respect rate limits.

`BeautifulSoup`/`selectolax` is listed as an available dependency for future HTML-based
providers; it is not required for the LL2-backed implementation of SpaceX and Rocket Lab.

Tests mock `httpx.AsyncClient` via `unittest.mock.AsyncMock` and assert:
- Correct `lsp__name` param sent for each provider.
- `normalize()` called once per parsed launch.
- New vs. updated counts reported correctly.
- `NormalizationError` cases logged and skipped without aborting the run.

**Consequences:**  
- ✅ Adding a third commercial provider is a one-line `PROVIDERS` entry — no new code path
- ✅ Consistent JSON schema across all LL2-backed scrapers; `_parse_launch()` reusable
- ✅ `normalize()` pipeline integrated — provider aliasing and lat/lon enrichment automatic
- ✅ Each provider has its own `osint_source` row — per-provider scrape history visible in DB
- ✅ Zero HTML fragility for SpaceX and Rocket Lab
- ❌ LL2 free tier rate-limits to ~15 req/hour; `SCRAPER_DELAY_SECONDS` must be respected
- ❌ `BeautifulSoup`/`selectolax` dependency added but only used if HTML providers added later

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

---

### ADR-014: NOTAM Scraper with FAA Public API and Keyword-Based Launch Classification

**Status:** Accepted  
**Date:** 2025-01-31

**Context:**  
Sprint item PO-007 requires harvesting publicly available NOTAMs (Notices to Airmen) as a
third OSINT source for launch event detection. NOTAMs are issued by the FAA and other aviation
authorities to alert pilots of temporary flight restrictions (TFRs), rocket launches, missile
tests, and range closures — all of which are strong indicators of launch activity. The FAA
exposes a REST API at `https://external-api.faa.gov/notamapi/v1/notams`. In practice this API
requires a registered account for sustained access, so the scraper must degrade gracefully
when credentials are absent or the API is unreachable.

NOTAM text follows a structured format with labelled line groups (`Q)`, `A)`, `B)`, `C)`,
`E)`, etc.). The `E)` (free-text) line contains the narrative — where keywords like `ROCKET`,
`SPACE LAUNCH`, `MISSILE`, and `RANGE CLOSURE` appear. The `Q)` line encodes lat/lon in a
compressed format (`DDMMN DDDMME` → decimal degrees). `B)` and `C)` lines encode validity
start/end as `YYMMDDHHMM`.

**Decision:**

1. **Scraper class** — `NotamScraper` in `project/src/openorbit/scrapers/notams.py`,
   following the same structural pattern as `SpaceAgencyScraper`:
   - `SOURCE_NAME = "FAA NOTAMs"`
   - `BASE_URL = "https://external-api.faa.gov/notamapi/v1/notams"`
   - `scrape()` — orchestrates fetch → log → parse → upsert cycle, returns summary dict
   - `parse(raw_data: str) -> list[LaunchEventCreate]` — delegates to `notam_parser`
   - `_fetch_with_retry(url, params)` — reuses exponential backoff pattern from
     `SpaceAgencyScraper`; on 401/403 logs a clear "credentials required" message and
     returns `(None, status_code)` so the scraper exits cleanly rather than retrying
   - `__main__` block calls `asyncio.run(main())` for standalone CLI use

2. **Parser module** — `project/src/openorbit/pipeline/notam_parser.py` is a **pure module**
   (no I/O, no DB, no HTTP). Public API:
   - `classify_notam(text: str) -> tuple[str | None, Literal["civilian","military","unknown"] | None]`  
     Returns `(matched_keyword, launch_type)` or `(None, None)` if no match.
     Keyword → launch_type mapping (evaluated in priority order):
     | Pattern (case-insensitive) | launch_type |
     |---|---|
     | `SPACE LAUNCH` | `civilian` |
     | `ROCKET` | `civilian` |
     | `MISSILE` | `military` |
     | `RANGE CLOSURE` | `unknown` |
     Note: the original spec mentioned `public_report` for MISSILE, but the
     `LaunchEventCreate.launch_type` Literal is constrained to `civilian | military | unknown`;
     `military` is the closest semantic match for MISSILE NOTAMs.
   - `parse_q_line(q_line: str) -> dict[str, float | None]`  
     Extracts `lat`, `lon` from the compressed coordinate in the Q-line
     (e.g., `3030N08145W` → `lat=30.5, lon=-81.75`). Returns `{"lat": None, "lon": None}`
     on parse failure.
   - `parse_validity(b_line: str, c_line: str) -> tuple[datetime | None, datetime | None]`  
     Parses `YYMMDDHHMM` strings to UTC datetimes. Returns `(None, None)` on failure.
   - `extract_launch_candidates(notams: list[dict[str, Any]]) -> list[LaunchEventCreate]`  
     Top-level function called by the scraper. Iterates NOTAM records, calls `classify_notam`
     on the `E)` text, skips non-matching records, calls `parse_q_line` and `parse_validity`
     for location/date, constructs `LaunchEventCreate` with
     `launch_date_precision = "day"` when a specific B-line date is parsed, `"week"` when
     only an approximate date is inferred.

3. **Slug scheme** — `notam-{notam_id}` where `notam_id` is taken from the API response
   field (typically the NOTAM number, e.g., `1/2345`). Slashes are replaced with hyphens.
   Idempotency follows the existing slug-based upsert in `upsert_launch_event`.

4. **Raw storage** — The full NOTAM JSON object is serialised to `raw_scrape_records.payload`
   unchanged, satisfying the requirement to store raw NOTAM text for audit / reprocessing.

5. **Offline / auth-required fallback** — When the FAA API returns 401/403 or a network
   error exhausts retries, the scraper logs a warning (`"FAA NOTAM API unavailable — check
   credentials or network"`) and returns `{"total_fetched": 0, "new_events": 0,
   "updated_events": 0}`. It does **not** raise, so the orchestration layer can proceed with
   other scrapers.

6. **Tests** — `project/tests/test_notam_parser.py` covers:
   - `classify_notam` with ≥3 sample NOTAM E-line strings (ROCKET, SPACE LAUNCH, MISSILE,
     RANGE CLOSURE, non-matching)
   - `parse_q_line` with valid and malformed Q-lines
   - `parse_validity` with valid B/C timestamps and edge cases (PERM C-line)
   - `extract_launch_candidates` with a list of mixed NOTAM dicts
   - `NotamScraper.scrape()` and `NotamScraper.parse()` with `httpx` mocked via
     `respx` or `unittest.mock`

**Consequences:**  
- ✅ Keyword classifier is a pure function — trivial to unit test without any I/O mocking
- ✅ Graceful offline fallback prevents FAA API auth requirements from blocking other scrapers
- ✅ Follows established `SpaceAgencyScraper` pattern — minimal learning curve for maintainers
- ✅ Raw NOTAM JSON preserved in `raw_scrape_records` for reprocessing
- ✅ Slug-based idempotency prevents duplicate events across repeated scrape runs
- ❌ FAA API requires account registration for production use; test coverage relies on mocks
- ❌ NOTAM coordinates use non-standard compressed format requiring custom parser
- ❌ `launch_type = "public_report"` (original spec) is not representable in the current
  Literal enum; mapped to `"military"` pending a future enum extension

---

## ADR-015: Multi-Source Event Deduplication and Merging Strategy

**Date:** 2025-07-14  
**Status:** Accepted  
**Sprint item:** PO-008

### Context

OpenOrbit ingests launch events from multiple independent scrapers (commercial, FAA NOTAM,
space-agency, etc.). Each scraper may discover the same real-world launch and create a
separate `launch_events` row, leading to duplicates. A deduplication pass must merge these
into a single canonical record without losing attribution data.

### Decision

Implement `deduplicate_and_merge(conn)` in
`project/src/openorbit/pipeline/deduplicator.py`.

**Similarity function** — two events are considered duplicates when *all three* of the
following hold:

1. **Same provider** after alias resolution via `PROVIDER_ALIASES` (e.g. "space exploration
   technologies" → "SpaceX"). Comparison is case-insensitive.
2. **Launch dates within 3 days** (`DATE_WINDOW_DAYS = 3`). This tolerates TBD-vs-confirmed
   date shifts common in launch scheduling.
3. **Same launch location** after lower-case normalisation, *or* at least one location is
   empty/None (missing location is treated as "don't disagree").

**Date window** — 3 days was chosen after analysing historical scrape data: legitimate
reschedules rarely exceed 3 days on short notice, while different missions at the same
provider on the same pad rarely fall within 3 days.

**Provider normalisation** — resolved through the existing `PROVIDER_ALIASES` dict to avoid
brittle string-equality checks across full company names and abbreviations.

**Merge strategy** — the record with the lexicographically earliest `created_at` timestamp
is kept as canonical. All `event_attributions` rows from the duplicate are reassigned to
the canonical slug. Rows that would violate the `(event_slug, scrape_record_id)` unique
constraint are deleted instead of transferred (avoiding duplicate attribution).

**Confidence score** — recalculated after each merge using
`min(0.3 * num_distinct_sources + 0.4, 1.0)` scaled to the integer DB range 0–100.
A single source gives 70 (0.7 × 100); two sources cap at 100.

**Idempotency** — guaranteed because duplicates are deleted after merging and processed
slugs are tracked in an in-memory set, so a second pass over the same data finds no further
duplicate pairs.

### Consequences

- ✅ Deduplication is fully reversible at the attribution level (raw scrape records are
  never deleted)
- ✅ Idempotent — safe to run on every pipeline cycle without degradation
- ✅ Provider alias resolution reuses existing `PROVIDER_ALIASES` with no new data
- ✅ O(n²) pair-scan is acceptable for expected volumes (< 10 000 events); tested at < 500 ms
  for 100 events in-memory
- ❌ O(n²) algorithm will need indexing or clustering if event counts reach tens of thousands
- ❌ Location normalisation is plain string equality — no geocoding or fuzzy matching; pad
  aliases (e.g. "Cape Canaveral" vs "CCAFS") could cause missed duplicates

---

## ADR-016: Launch Type Classifier Design

**Date:** 2025-07-14
**Status:** Accepted
**Sprint Item:** PO-009

### Context

OpenOrbit ingests launch events from multiple OSINT sources with varying levels of detail.
Some launches are civilian commercial missions, others are government/military, and some
are NOTAM-flagged missile-related events that should be tagged as `public_report` for
downstream filtering. A lightweight, deterministic classifier was needed that could run
in the pipeline without I/O or external lookups.

### Decision

Implement `pipeline/classifier.py` as a **pure function** `classify_launch_type()` with
a fixed priority chain:

1. **Hint passthrough** — if the scraper already determined a valid `launch_type`, accept it.
2. **MISSILE keyword** — if NOTAM keywords include `MISSILE` (case-insensitive), classify
   as `public_report`. This models the real-world pattern where NOTAM text flags missile
   tests explicitly.
3. **Provider match** — if the provider name (lowercased) contains any string from the
   `MILITARY_PROGRAMS` set in `pipeline/military_programs.py`, classify as `military`.
4. **Source name heuristic** — if the OSINT source name contains "military" or "dod",
   classify as `military`.
5. **Default** — `civilian`.

The `MILITARY_PROGRAMS` set in `military_programs.py` contains only **publicly reported**
program names (NRO, DoD, USSF, etc.) — no classified information.

### Rationale

- **Pure function** — no I/O, no DB calls; trivially unit-testable and composable.
- **Priority order is explicit and auditable** — hint > keyword > provider > source > default.
- **Extensible** — adding a new military program requires one set entry; no code changes.
- **`launch_type` filter** — `GET /v1/launches?launch_type=` already supported by the
  existing DB query layer; the classifier populates the field at ingest time.

### Consequences

- ✅ 100% unit test coverage on classifier module (15 scenarios tested)
- ✅ Zero external dependencies — purely stdlib + project modules
- ✅ Adding programs requires only updating `military_programs.py`
- ❌ Keyword matching is exact (`MISSILE` only) — fuzzy or NLP-based matching deferred
- ❌ Classifier runs at ingest time; existing events in DB are not back-filled automatically

---

## ADR-018: Docker Deployment Strategy (PO-012)

**Date:** 2025-07-18
**Status:** Accepted

### Context

openOrbit needs to be deployable as a containerised service so that operators can run the
API in isolated, reproducible environments without manual Python setup.

### Decision

Use a **multi-stage Docker build** with `python:3.12-slim` as the base image for both stages:

- **Builder stage** — installs `uv` and resolves all runtime dependencies into a `.venv`
  via `uv sync --no-dev`. The project source is then copied into the stage.
- **Runtime stage** — copies only the `.venv` and `src/` from the builder; no build tools
  or caches are included, keeping the image lean (target < 300 MB).

The container process runs as a dedicated non-root `appuser` / `appgroup` to satisfy
least-privilege requirements.

A `docker-compose.yml` is provided for local development and simple single-node deployments.
It mounts `./data` as a volume so the SQLite database persists across restarts.

A `.dockerignore` excludes `state/`, `.git/`, test fixtures, caches, and documentation
from the build context to speed up builds and avoid leaking sensitive state files.

### Alternatives Considered

- **Single-stage build** — simpler but includes build tools (uv, pip) in the final image,
  increasing size and attack surface. Rejected.
- **Alpine base** — smaller base image, but binary wheel compatibility issues with several
  dependencies (pydantic-core, uvicorn). Rejected in favour of slim.

### Consequences

- ✅ Reproducible, isolated deployments with a single `docker build` command
- ✅ Non-root runtime satisfies common security policies
- ✅ Data persists via volume mount; no data loss on container restart
- ✅ Health check endpoint enables Docker-native liveness probing
- ❌ SQLite is not suitable for multi-replica deployments; a future ADR will address
  migration to PostgreSQL if horizontal scaling is needed

---

## ADR-017 — APScheduler Background Refresh Jobs

**Status:** Accepted  
**Date:** 2025-01-01  
**Sprint item:** PO-010

### Context

openOrbit scrapers previously ran only on demand. To provide continuously updated
launch intelligence the system needs a background scheduler that periodically re-runs
each scraper without manual intervention.

### Decision

Use **APScheduler 3.x with `AsyncIOScheduler`** to schedule one `interval` job per
enabled OSINT source. The scheduler is started in the FastAPI lifespan context manager
alongside `init_db()`, and shut down cleanly on application stop.

Key design choices:

- Each job is identified as `scraper_<source_id>` to prevent duplicate registration.
- `max_instances=1` per job prevents overlapping runs of slow scrapers.
- `misfire_grace_time=300 s` allows missed jobs to still run if the process was briefly
  suspended.
- Scraper failures are caught and logged; the scheduler never crashes on a single-job
  error.
- `refresh_interval_hours` is stored in `osint_sources` (default 6 h) and applied via
  an idempotent `ALTER TABLE` migration in `init_db_schema()`.
- A new `GET /v1/sources` endpoint exposes each source's `last_scraped_at`,
  `event_count`, and `last_error` for observability.

### Consequences

- ✅ Continuous data freshness without external cron infrastructure
- ✅ Scheduler lifecycle tied to the application (starts/stops with the server)
- ✅ Per-source interval configurability stored in the DB
- ❌ APScheduler job state is in-memory; missed jobs are lost on process restart
  (acceptable for now; a persistent job store can be added if needed)

---

## ADR-019: Rate Limiting, Cursor Pagination & Advanced Filtering

**Date:** 2025-07-15  
**Status:** Accepted  
**Sprint item:** PO-013

### Context

The `/v1/launches` API lacked request throttling (no abuse protection), offered only
page-based pagination (OFFSET-heavy at scale), and provided only exact-match filtering
on `provider`. Advanced data-consumers requested fuzzy provider search, confidence-score
gating, and proximity search.

### Decision

1. **In-memory sliding-window rate limiter** (`openorbit.middleware.rate_limiter`):
   - Implemented as a Starlette `BaseHTTPMiddleware`, keyed by client IP.
   - Default: 60 requests / 60 s window. Configurable at construction time.
   - Exceeding the limit returns HTTP 429 with `Retry-After` and `X-RateLimit-*` headers.
   - Every successful response also carries `X-RateLimit-Limit` and
     `X-RateLimit-Remaining` for client-side back-off.

2. **Cursor-based pagination** alongside existing page-based:
   - `?cursor=<token>&limit=N` activates cursor mode; `?page=N&per_page=N` uses OFFSET.
   - Cursor is the URL-safe base64 encoding of the last SQLite `rowid` seen.
   - Cursor mode uses `WHERE rowid > cursor_id ORDER BY rowid ASC` — no OFFSET scan.
   - Response `meta.next_cursor` is populated when more rows remain.

3. **Advanced filters**:
   - `?provider=<fuzzy>` upgraded to `LOWER(provider) LIKE LOWER('%<value>%')`.
   - `?min_confidence=<float>` maps to `confidence_score >= ?` in SQL.
   - `?location=<lat,lon>&radius_km=<int>` applies Haversine filtering in Python
     (events without parseable lat/lon in their `location` field are excluded).

### Key design choices

- Rate limiter uses a `deque` per IP for O(1) eviction at window boundary.
- `slowapi` was rejected in favour of a zero-dependency in-memory approach; suitable
  for single-process deployments. A Redis-backed limiter should be added before
  horizontal scaling.
- Proximity filtering is Python-side because SQLite has no geo functions; acceptable
  for the current dataset size. A PostGIS migration would move this to SQL.
- `PaginationMeta.next_cursor` is `None` on page-based responses — fully
  backward-compatible.

### Consequences

- ✅ API is protected against request floods per IP
- ✅ Cursor pagination scales to large datasets without OFFSET degradation
- ✅ `provider` filter is user-friendly (partial, case-insensitive)
- ✅ Confidence and proximity filters enable quality-gated, location-aware queries
- ❌ In-memory rate-limit state is lost on restart / not shared across processes
- ❌ Proximity filter only works for events whose `location` field stores `"lat,lon"` text

---

## ADR-020 — Inference & Multi-Source Correlation Layer

**Status:** Accepted  
**Date:** 2025-01-01  
**Sprint item:** PO-011

### Context

openOrbit aggregates launch events from multiple OSINT sources. With multiple data
points available, the system can apply inference rules to detect patterns and increase
confidence in events. This forms the foundation of Phase 3 of the project roadmap.

### Decision

Implement an `InferenceEngine` class in `openorbit.pipeline.inference` that applies
three deterministic heuristic rules to annotate launch events stored in the database:

1. **`multi_source_corroboration`** — When an event is attributed to ≥2 distinct OSINT
   sources, add this flag and increase `confidence_score` by 20 points (capped at 100).
2. **`pad_reuse_pattern`** — When another event from the same launch pad occurred within
   the preceding 30 days, flag the event as exhibiting pad reuse behaviour.
3. **`notam_cluster`** — When ≥2 NOTAM-sourced events exist within a ±3-day window
   around the event, flag it as part of a NOTAM cluster signal.

Results are stored in a new `inference_flags` (JSON TEXT, nullable) column on
`launch_events`, added via an idempotent `ALTER TABLE` migration in `init_db_schema()`.

The engine is **idempotent**: re-running it on the same data produces the same flags
without duplication or confidence drift.

### API Impact

- `GET /v1/launches` — accepts `?has_inference_flag=<flag>` to filter by flag.
- `GET /v1/launches/{slug}` — response includes `inference_flags` array.

### Consequences

- ✅ Deterministic, auditable inference rules — no ML black box
- ✅ Idempotent engine safe to run on scheduler cadence
- ✅ DB migration is backwards-compatible (nullable column, try/except guard)
- ✅ API filtering enables flag-specific dashboards and alerting
- ❌ NOTAM clustering is time-window only; does not account for geographic proximity
  (deferred to a future ADR once lat/lon parsing is standardised)
- ❌ Confidence adjustment is additive and uncapped per rule; future work could weight
  rules based on source reliability

---

### ADR-011: Test Coverage Strategy for Protocol Classes, ASGI Lifecycle, and API Error Paths

**Status:** Accepted  
**Date:** 2025-07-14  
**Sprint Item:** PO-023

**Context:**  
Overall project coverage sits at 88% (target ≥85%), but four modules fall below the hard 80% minimum:

- `scrapers/base.py` — 0% (8 stmts): Pure Protocol class; no concrete implementation to instantiate, so standard test collection never exercises it.
- `main.py` — 56% (19 stmts missing): `configure_logging()` and the `lifespan()` async context manager (startup/shutdown hooks) are never invoked by the existing route-focused test suite.
- `api/v1/sources.py` — 53% (8 stmts missing): The GET `/v1/sources` route body is absent from all current tests.
- `api/v1/launches.py` — 77% (22 stmts missing): Error branches (404 on missing slug, invalid cursor, bad geo-filter params) and pagination edge cases are untested.

**Decision:**  

**`scrapers/base.py` — Protocol coverage**  
Decorate the `BaseScraper` Protocol with `@runtime_checkable`. Create a minimal concrete `DummyScraper` stub in the test module that implements `scrape()` and `parse()`. Test:
1. `isinstance(DummyScraper(), BaseScraper)` returns `True`.
2. A class missing either method fails the `isinstance` check.
3. Calling `scrape()` and `parse()` on the stub returns the expected types.

**`main.py` — ASGI lifecycle coverage**  
Mock the four I/O side-effect functions (`init_db`, `close_db`, `start_scheduler`, `stop_scheduler`) with `unittest.mock.AsyncMock` / `MagicMock`. Use `httpx.AsyncClient(transport=ASGITransport(app=create_app()))` inside an `async with` block to trigger the lifespan. Separately call `configure_logging()` directly to cover its branch. Tests:
1. Startup path: verify `init_db` and `start_scheduler` are called once.
2. Shutdown path: verify `stop_scheduler` and `close_db` are called once.
3. `configure_logging()` does not raise and sets the root log level.

**`api/v1/sources.py` — GET /v1/sources coverage**  
Use the existing `async_client` fixture. Tests:
1. Empty database → 200 with `{"sources": []}`.
2. Pre-seeded source rows → 200 with correct source objects in the response body.
3. Verify response JSON schema fields (`name`, `url`, `type`, `last_scraped_at`).

**`api/v1/launches.py` — error paths and edge cases**  
Use the `async_client` fixture. Tests:
1. `GET /v1/launches/{slug}` with a non-existent slug → 404 with error body.
2. `GET /v1/launches?cursor=INVALID` → 400 or graceful empty result (match implementation).
3. `GET /v1/launches?lat=abc&lon=def` → 422 validation error.
4. `GET /v1/launches?lat=91&lon=181` → 422 (out-of-range).
5. Pagination: first page returns `next_cursor`; fetching with that cursor returns the next page; last page returns `null` cursor.

**Files to create:**
- `project/tests/test_coverage_base.py`
- `project/tests/test_coverage_main.py`
- `project/tests/test_coverage_sources.py`
- `project/tests/test_coverage_launches_extended.py`

**Consequences:**  
- ✅ `scrapers/base.py`: 0% → ~90% (all public Protocol surface exercised)
- ✅ `main.py`: 56% → ~85%+ (lifespan hooks and logging covered via mocks)
- ✅ `api/v1/sources.py`: 53% → ~95% (route body fully exercised)
- ✅ `api/v1/launches.py`: 77% → ~90%+ (all identified error branches covered)
- ✅ Overall project coverage: 88% → ~92%+ (conservative estimate)
- ❌ Mocking `init_db`/`close_db` in lifespan tests means actual DB migration code is not exercised in those tests — integration remains covered by existing DB fixture tests

---

## ADR-012: API Key Authentication — Hashed Storage, Timing-Safe Comparison, Bootstrap via Env Var

**Status:** Accepted  
**Date:** 2025-07-14  
**Sprint Item:** PO-024

### Context

openOrbit admin endpoints (key creation, key revocation) need protection without
introducing OAuth flows, refresh tokens, or an external identity provider. A simple
static API key scheme is sufficient for the threat model (internal tooling / CI pipelines).

### Decisions

1. **Storage algorithm** — PBKDF2-SHA256 with 260,000 iterations and a 32-byte (64-char
   hex) random salt generated per key. Chosen over bcrypt to avoid a heavy native
   dependency while still providing key-stretching that makes offline brute-force
   impractical. The digest is stored as a hex string in the `key_hash` column alongside
   its `salt`.

2. **Timing-safe comparison** — All key comparisons use `hmac.compare_digest()` to
   prevent timing side-channel attacks. This applies both to the hash comparison
   (`verify_key`) and to the bootstrap env-var comparison.

3. **Bootstrap admin key** — `OPENORBIT_ADMIN_KEY` env var is read via pydantic-settings
   (`Settings.OPENORBIT_ADMIN_KEY: str | None`). If set, it is compared in memory with
   `hmac.compare_digest` on every request. It is **never** stored in the database.
   This allows zero-config deployment in CI without a DB seed step.

4. **New DB table** — `api_keys` table added to `schema.sql`:
   ```sql
   CREATE TABLE IF NOT EXISTS api_keys (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       name TEXT NOT NULL,
       key_hash TEXT NOT NULL,
       salt TEXT NOT NULL,
       is_admin INTEGER NOT NULL DEFAULT 0,
       created_at TEXT NOT NULL,
       revoked_at TEXT  -- NULL while active
   );
   ```
   Revoked keys are retained for audit; authentication checks filter on `revoked_at IS NULL`.

5. **FastAPI dependencies** — Two reusable async dependencies in `openorbit.auth`:
   - `require_admin(request)` — checks X-API-Key header then `?api_key=` query param;
     raises 401 on absence, 403 on invalid/revoked key. Accepts bootstrap key or any
     non-revoked `is_admin=1` DB key.
   - `require_valid_key(request)` — same flow but accepts any non-revoked DB key (for
     future non-admin protected endpoints).

6. **Router** — `openorbit.api.v1.auth` registers two routes under `/v1/auth`:
   - `POST /v1/auth/keys` — create key, returns plaintext key once only.
   - `DELETE /v1/auth/keys/{id}` — soft-revoke by setting `revoked_at`.
   Both depend on `require_admin`.

7. **Bootstrap key never stored** — confirmed by design: the env var is never written to
   the database, never logged, and compared only in `hmac.compare_digest` in process memory.

### Public/Protected Boundary

| Endpoint | Auth required |
|---|---|
| GET /v1/launches | ❌ public |
| GET /v1/launches/{slug} | ❌ public |
| GET /v1/sources | ❌ public |
| GET /health | ❌ public |
| POST /v1/auth/keys | ✅ admin key |
| DELETE /v1/auth/keys/{id} | ✅ admin key |

### Consequences

- ✅ Simple, auditable — all auth logic in ≤150 LOC across two files
- ✅ No token refresh — static keys suit CI pipelines and internal dashboards
- ✅ Timing-safe by design throughout
- ✅ Zero-dependency bootstrap (stdlib `hmac`, `hashlib`, `secrets` only)
- ✅ Schema change is additive and idempotent (`CREATE TABLE IF NOT EXISTS`)
- ❌ No key expiry or automatic rotation — deferred to a future ADR
- ❌ All admin keys have equal privilege — role-based scopes deferred

---

## ADR-PO014: OpenAPI Documentation Strategy

Date: 2026-03-24
Status: Accepted

### Context

openOrbit exposes a FastAPI REST API with six endpoints across three routers (launches,
sources, auth). While the Python docstrings are thorough, the auto-generated Swagger UI
at `/docs` lacks structured metadata: routes have no `tags`, `summary`, `response_description`,
or error `responses` schemas; Pydantic models carry no `json_schema_extra` examples; and no
human-readable developer guides exist in `docs/`.

### Decision

Enrich in-place — no new code modules are required. Changes fall into four areas:

1. **Route decorators** — add `tags`, `summary`, `description`, `response_description`,
   and `responses` dicts to every `@router.get/post/delete` call in:
   - `api/v1/launches.py` (2 routes)
   - `api/v1/sources.py` (1 route)
   - `api/v1/auth.py` (2 routes — partial metadata already present)

2. **Pydantic models** — add `model_config = ConfigDict(json_schema_extra={"example": ...})`
   to every response/request model in `models/api.py`:
   - `AttributionResponse`, `PaginationMeta`, `LaunchEventResponse`,
     `PaginatedLaunchResponse`, `ApiKeyCreateRequest`, `ApiKeyCreateResponse`,
     `ApiKeyRevokeResponse`

3. **FastAPI app** — add `openapi_tags` list to `create_app()` in `main.py` to provide
   tag descriptions that appear at the top of the Swagger UI tag groups.

4. **Documentation files** (authored, not generated):
   - `docs/api-reference.md` — endpoint table, parameter tables, example request/response
     for every route, error code catalogue
   - `docs/quickstart.md` — installation, env vars, first curl call, pagination walk-through,
     auth key lifecycle

### Structure of `docs/api-reference.md`

```
# API Reference
## Authentication
## Launches
### GET /v1/launches (params table, example curl, example 200 response, error table)
### GET /v1/launches/{slug} (params table, example curl, example 200/404 response)
## Sources
### GET /v1/sources (example curl, example 200 response)
## Admin — API Keys
### POST /v1/auth/keys (request body table, example curl, 201/401/403 response)
### DELETE /v1/auth/keys/{id} (example curl, 200/404/409 response)
## Error Reference (common error shapes)
```

### Structure of `docs/quickstart.md`

```
# Quick Start
## Prerequisites
## Installation (Docker vs. bare uv)
## Environment variables
## First launch query (curl)
## Filtering & pagination walk-through
## Creating an API key
## Revoking an API key
## Rate limits & error handling
```

### Consequences

- ✅ Zero new runtime dependencies — pure metadata and Markdown
- ✅ Swagger UI becomes immediately useful for third-party integrators
- ✅ `json_schema_extra` examples appear in both Swagger UI "Try it out" and ReDoc
- ✅ Human-readable guides in `docs/` fulfil PO-014 acceptance criteria
- ✅ `project/README.md` API section updated with endpoint overview table
- ❌ Examples in `json_schema_extra` are static — they must be maintained manually
  if field names change; a future ADR may automate example generation from fixtures

## ADR-PO015: Modular Source Plugin Interface

Date: 2026-03-24
Status: Accepted

### Context

openOrbit has three concrete scrapers (`SpaceAgencyScraper`, `CommercialScraper`,
`NotamScraper`) each implemented as standalone classes with no shared base class
beyond an informal `Protocol`. The scheduler discovers scrapers by querying the
`osint_sources` table for a `scraper_class` dotted-path string, then dynamically
imports the class. Adding a new scraper requires both a new Python file **and** a
manual DB row insert — two error-prone, disconnected steps.

`GET /v1/sources` reflects only DB-registered sources, missing any scraper that
has not yet been seeded into the database.

### Decision

1. **Replace `BaseScraper` Protocol with an ABC.**  `scrapers/base.py` will expose
   `BaseScraper(ABC)` with:
   - `@abstractmethod async def scrape(self) -> dict[str, int]`
   - `@abstractmethod async def parse(self, raw_data: str) -> list[LaunchEventCreate]`
   - `source_name: ClassVar[str]` — required class attribute validated in
     `__init_subclass__`
   - `source_url: ClassVar[str]` — required class attribute validated in
     `__init_subclass__`
   - `__init_subclass__` hook that auto-registers any non-abstract concrete subclass
     into the global `ScraperRegistry` singleton the moment its module is imported.

2. **Create `scrapers/registry.py`** with a `ScraperRegistry` class and a
   module-level `scraper_registry` singleton.  The registry exposes:
   - `register(cls)` — idempotent; keyed by `source_name`
   - `get_all() -> list[type[BaseScraper]]`
   - `get_by_name(name: str) -> type[BaseScraper] | None`

3. **Existing scrapers** (`SpaceAgencyScraper`, `CommercialScraper`,
   `NotamScraper`) will inherit from `BaseScraper` instead of being standalone
   classes.  Each must:
   - Rename `SOURCE_NAME` → `source_name`, `BASE_URL` → `source_url` (class attrs).
   - Add `parse()` if missing (or rename existing internal parse method to match
     the ABC signature).
   - Inherit from `BaseScraper` — `__init_subclass__` handles auto-registration.

4. **`scrapers/__init__.py`** will import all concrete scraper modules so that
   their classes are registered as a side-effect of `import openorbit.scrapers`.
   This is the canonical "plugin loading" step.

5. **`scheduler.py`** gains a new `run_scraper_job_from_registry()` function.
   `start_scheduler()` will:
   - Call `import openorbit.scrapers` (triggers auto-registration).
   - Iterate `scraper_registry.get_all()`.
   - Schedule each using a default interval (6 h) or a per-scraper
     `REFRESH_INTERVAL_HOURS` class attribute if present.
   - Fall back to the existing DB-driven approach for sources that declare a
     custom `scraper_class` path not yet migrated.

6. **`GET /v1/sources`** will merge the registry list with the DB rows.
   For each registered scraper, if no DB row exists for `source_name`, it appears
   with `{"registered": true, "db_seeded": false}`.  Existing DB-only sources
   retain their `event_count` and `last_scraped_at` data.

### Consequences

- ✅ Adding a new scraper requires only a new Python file — no DB seed needed.
- ✅ `BaseScraper` is now enforceable at import time (missing `source_name` raises
  `TypeError`), preventing silent misconfigurations.
- ✅ `GET /v1/sources` gives real-time visibility into all registered scrapers.
- ✅ `scrapers/base.py` is fully testable (no network I/O) — ≥95% coverage is
  achievable with pure-unit tests.
- ❌ Existing scrapers require minor refactoring (rename two class attrs, add
  `BaseScraper` to the class header) — low risk, well-scoped.
- ❌ Scrapers that define no DB row lose historical `event_count` until first
  scrape run; acceptable trade-off for simplicity.

## ADR-PO028: OSINT Source Tier System & Claim Lifecycle Schema Migration

**Date:** 2025-07-23
**Status:** Accepted
**Sprint:** sprint-4 / PO-028

### Context

The current schema treats all data sources and launch claims equally. As the intelligence
methodology matures, we need first-class schema support for:
- Source credibility tiers (official vs. operational vs. analytical)
- Claim lifecycle states (rumor → confirmed or retracted)
- Evidence classification per attribution record
- Per-attribution confidence scores with human-readable rationale

This enables the dashboard to display provenance-aware data and the tiering engine
to make more nuanced `verified`/`tracked`/`emerging` decisions.

### Decision

**1. Schema changes via idempotent ALTER TABLE migrations in `init_db_schema()`**

All new columns have safe defaults so existing rows remain valid. The established
try/except pattern in `init_db_schema()` is used for each column (one try/except
block per column).

**2. `osint_sources.source_tier`** — `INTEGER NOT NULL DEFAULT 1`
Tier 1 = Official/Regulatory, Tier 2 = Operational, Tier 3 = Analytical.
Updated in `schema.sql` inside `CREATE TABLE osint_sources` and via ALTER TABLE
at startup.

**3. `launch_events.claim_lifecycle`** — `TEXT NOT NULL DEFAULT 'indicated'`
CHECK IN ('rumor','indicated','corroborated','confirmed','retracted').
Updated in `schema.sql` inside `CREATE TABLE launch_events` and via ALTER TABLE.

**4. `launch_events.event_kind`** — `TEXT NOT NULL DEFAULT 'observed'`
CHECK IN ('observed','inferred').
Updated in `schema.sql` and via ALTER TABLE.

**5. `event_attributions` enrichment columns** — 6 new nullable columns:
- `source_url TEXT` — direct URL to source document
- `observed_at TEXT` — ISO 8601 when signal was seen
- `evidence_type TEXT` — CHECK IN set of 9 canonical types
- `source_tier INTEGER` — denormalized copy for fast queries
- `confidence_score INTEGER` — CHECK BETWEEN 0 AND 100
- `confidence_rationale TEXT` — human-readable explanation
All added via ALTER TABLE at startup (nullable, no default required).

**6. Scraper class vars** — `BaseScraper` gains two optional class-level ClassVar
attributes: `source_tier: ClassVar[int] = 1` and `evidence_type: ClassVar[str] = 'official_schedule'`.
Each scraper overrides them as specified in the acceptance criteria. These are
class-level only — no DB writes change except when `register_osint_source()`
writes the tier to `osint_sources.source_tier`.

**7. `add_attribution()` signature extension** — new optional keyword arguments:
`source_url`, `observed_at`, `evidence_type`, `source_tier`, `confidence_score`,
`confidence_rationale`. All default to `None` for backward compatibility. The
INSERT into `event_attributions` writes these values when provided.

**8. Pydantic models updated:**
- `OSINTSource` (db.py): add `source_tier: int = 1`
- `LaunchEventCreate` (db.py): add `claim_lifecycle` and `event_kind` with Literal defaults
- `EventAttribution` (db.py): add all 6 enrichment fields as Optional
- `AttributionResponse` (api.py): add optional `evidence_type`, `source_tier`, `confidence_score`, `confidence_rationale`
- `LaunchEventResponse` (api.py): add `claim_lifecycle` and `event_kind`

**9. Existing result tier logic is unchanged** — `tiering.py` and SQL expr remain.
The `confidence_score` column on `launch_events` (0-100 int) continues to drive
`verified`/`tracked`/`emerging` via the existing `result_tier_sql_expr()`.

### Migration Strategy

`init_db_schema()` in `db.py`:
1. Executes `schema.sql` (CREATE TABLE IF NOT EXISTS — no-op on existing tables)
2. Runs 9 idempotent ALTER TABLE blocks (one try/except per new column):
   - `osint_sources`: `source_tier`
   - `launch_events`: `claim_lifecycle`, `event_kind`
   - `event_attributions`: `source_url`, `observed_at`, `evidence_type`, `source_tier`, `confidence_score`, `confidence_rationale`
3. Each block logs success; exceptions (column exists) are silently swallowed.

### Consequences

- ✅ Zero downtime: existing data remains valid (all new columns have defaults or are nullable)
- ✅ Idempotent: safe to run on already-migrated databases
- ✅ Backward compatible: `add_attribution()` callers that omit new kwargs continue to work
- ✅ Result tier contract preserved
- ✅ Clean scraper class-level metadata (no runtime cost)
- ❌ Scrapers currently do NOT pass enrichment fields when calling `add_attribution()` — that wiring is a follow-on task (PO-029 or inline in programmer's implementation of this item)
- ❌ SQLite CHECK constraints on new columns only enforce on INSERT/UPDATE for new rows; existing rows are not validated retroactively

### Files Affected

- `project/src/openorbit/schema.sql`
- `project/src/openorbit/db.py`
- `project/src/openorbit/models/db.py`
- `project/src/openorbit/models/api.py`
- `project/src/openorbit/scrapers/base.py`
- `project/src/openorbit/scrapers/space_agency.py`
- `project/src/openorbit/scrapers/spacex_official.py`
- `project/src/openorbit/scrapers/commercial.py`
- `project/src/openorbit/scrapers/celestrak.py`
- `project/src/openorbit/scrapers/notams.py`
- `project/src/openorbit/scrapers/esa_official.py`
- `project/src/openorbit/scrapers/jaxa_official.py`
- `project/src/openorbit/scrapers/isro_official.py`
- `project/src/openorbit/scrapers/arianespace_official.py`
- `project/src/openorbit/scrapers/cnsa_official.py`
- `project/tests/test_db.py` (or new test file)

## ADR-PO016: Admin & Source Health Monitoring Endpoints

**Date:** 2025-07-14
**Status:** Accepted

### Context
Need admin endpoints for source monitoring, health stats, and manual refresh.

### Decision
- New router `admin.py` in `api/v1/` with prefix `/admin`
- `dependencies=[Depends(require_admin)]` on all routes
- New Pydantic models: `SourceHealthResponse`, `AdminStatsResponse`, `AdminRefreshResponse`
- `event_count` via subquery on `event_attributions` joined to `raw_scrape_records`
- `error_rate` calculated from `raw_scrape_records`
- `POST /refresh` returns 202 with triggered status (background execution deferred)
- Registered in `api/v1/__init__.py`

### Consequences
- All admin endpoints behind X-API-Key auth
- Backward-compatible addition

## ADR-PO029: Provenance API Evidence Chain Endpoint

**Date:** 2025-01-22
**Status:** Accepted

### Context
Need a per-event endpoint returning all attribution evidence with tier coverage summary for dashboard and API consumers to understand the epistemic basis for each launch event.

### Decision
- New router `evidence.py` in `api/v1/` with `GET /launches/{slug}/evidence`
- New Pydantic models: `EvidenceAttributionItem`, `EvidenceResponse`
- Registered in `api/v1/__init__.py` alongside launches router (no prefix — router defines `/launches/{slug}/evidence`)
- `LaunchEventResponse` gains `evidence_url: str | None` field populated as `/v1/launches/{slug}/evidence`
- DB: reuse `get_launch_event_by_slug` + `get_event_attributions`; fixed both to persist/read `claim_lifecycle` and `event_kind`

### Consequences
- Minimal DB changes (read-only queries via existing functions, with bug fix for claim_lifecycle/event_kind persistence)
- Backward-compatible (`evidence_url` added to existing response with `None` default)
- `upsert_launch_event` now correctly stores `claim_lifecycle` and `event_kind` columns

---

### ADR-015: Tier 3 News RSS Scraper — NewsRSSScraper Architecture (PO-017)

**Status:** Accepted  
**Date:** 2025-07-14  
**Sprint Item:** PO-017

**Context:**  
OpenOrbit currently ingests Tier 1 (official agency schedules) and Tier 2 (NOTAMs, operational signals) data. To build a complete OSINT picture, we need Tier 3 Analytical/Media sources. SpaceFlightNow and NASASpaceflight publish high-quality space launch journalism via standard RSS. These sources do not provide schedule data directly — they report on launches with varying degrees of confidence — so events derived from them must carry `claim_lifecycle='rumor'` until corroborated by Tier 1/2 sources.

Key requirements:
- Two concrete scrapers auto-registered in `ScraperRegistry`
- `source_tier=3`, `evidence_type='media'`
- Fuzzy entity linking: news items that reference an existing launch (matched by provider name + date proximity ±7 days) should attribute to the existing event rather than creating duplicates
- Unmatched items create new events with `claim_lifecycle='rumor'` and `event_kind='inferred'`

**Decision:**  
Introduce `project/src/openorbit/scrapers/news.py` with a class hierarchy:

```
PublicFeedScraper (existing)
  └── NewsRSSScraper (abstract, in news.py)
        ├── SpaceFlightNowScraper (concrete, auto-registered)
        └── NASASpaceflightScraper (concrete, auto-registered)
```

**Rejected alternative — single `NewsRSSScraper` iterating multiple feed URLs:**  
A single class with a list of URLs would not auto-register as two independent OSINT sources, would complicate per-source scrape logging, and would mix attribution records from two distinct journalistic outlets. Two concrete subclasses keeps sources traceable and individually enable/disable-able.

**Design details:**

1. **`NewsRSSScraper(PublicFeedScraper)`** — abstract intermediate class:
   - `source_tier: ClassVar[int] = 3`
   - `evidence_type: ClassVar[str] = "media"`
   - Overrides `parse()`: calls `super().parse()` then stamps every returned `LaunchEventCreate` with `claim_lifecycle='rumor'` and `event_kind='inferred'`
   - Overrides `_ensure_source_registered()`: passes `source_tier=3` to `register_osint_source()`
   - Overrides `scrape()`: adds fuzzy entity linking after parsing — loads existing events keyed by `(normalized_provider, date_day)`, checks each parsed event against it; matching events skip upsert and receive only an attribution; non-matching events proceed to `upsert_launch_event()`
   - Broader `KEYWORDS` tuple covering news-style verbs: `"launch"`, `"liftoff"`, `"rocket"`, `"satellite"`, `"spacecraft"`, `"mission"`, `"orbit"`, `"countdown"`

2. **`SpaceFlightNowScraper(NewsRSSScraper)`** — concrete:
   - `source_name = "news_spaceflightnow"`
   - `source_url = "https://spaceflightnow.com/feed/"`
   - `SOURCE_NAME = "SpaceFlightNow RSS"`
   - `PROVIDER_NAME = "SpaceFlightNow"`
   - `feed_region()` → `"global"`

3. **`NASASpaceflightScraper(NewsRSSScraper)`** — concrete:
   - `source_name = "news_nasaspaceflight"`
   - `source_url = "https://www.nasaspaceflight.com/feed/"`
   - `SOURCE_NAME = "NASASpaceflight RSS"`
   - `PROVIDER_NAME = "NASASpaceflight"`
   - `feed_region()` → `"global"`

4. **Fuzzy entity linking algorithm** (in `NewsRSSScraper.scrape()`):
   - After `parse()`, load existing events: `SELECT slug, provider, launch_date FROM launch_events`
   - Build index: `{(normalize_provider(p), date_day(d)): slug}`
   - For each parsed event: compute key; if found in index, skip `upsert_launch_event()` and call only `add_attribution()`; else upsert with `claim_lifecycle='rumor'`
   - Provider normalization: lowercase + strip whitespace
   - Date day key: `launch_date.date()` (UTC)
   - Match window: exact day match OR ±1 day tolerance

5. **`claim_lifecycle` and `event_kind` in `LaunchEventCreate`**: Both fields already exist (added in Sprint 4). The `parse()` override sets them directly on the model instances before returning.

6. **OSINT source seeding**: Both sources auto-registered on first `scrape()` call via `_ensure_source_registered()` with `source_tier=3`. No separate seed migration required.

**Files to create:**
- `project/src/openorbit/scrapers/news.py`
- `project/tests/test_scraper_news.py`

**Files to modify:**
- `state/decisions.md` (this record)
- `state/handoffs/sprint-5/architect.json`

**Consequences:**  
- ✅ Two independent Tier 3 OSINT sources, each with full audit trail
- ✅ `claim_lifecycle='rumor'` correctly flags unverified media items
- ✅ Fuzzy linking prevents duplicate events when news covers known launches
- ✅ Auto-registered via existing `__init_subclass__` mechanism — no registry changes needed
- ✅ `PublicFeedScraper` HTTP retry, rate limiting, and XML parsing fully reused
- ❌ Fuzzy match is approximate (day-window + provider substring) — some false positives/negatives expected; acceptable for Tier 3 analytical context
- ❌ News RSS items rarely carry precise launch times — `launch_date_precision='day'` will be the norm


---

## ADR-012: GitHub Actions CI/CD Pipeline

**Date:** 2025-07-11  
**Status:** Accepted  
**Sprint item:** PO-026  

### Context

The project needed an automated continuous integration pipeline to enforce code quality checks (lint, type-check, test) on every push and pull request, and to gate merges on passing checks.

### Decision

Implement a GitHub Actions workflow (`.github/workflows/ci.yml`) with three parallel jobs:
- **lint** — `ruff check` + `ruff format --check` on `src/` and `tests/`
- **typecheck** — `mypy src/` in strict mode
- **test** — `pytest --cov=src --cov-fail-under=80 -q`

All jobs use `ubuntu-latest`, Python 3.12, and `uv` for dependency installation.

### Consequences

- ✅ Every PR is validated automatically before merge
- ✅ 80% coverage minimum is enforced in CI, matching the project requirement
- ✅ `uv sync` keeps dependency installation fast and reproducible
- ✅ Three parallel jobs minimise total wall-clock CI time
- ❌ `uv` installed via `pip install uv` (not the official action) — acceptable for speed; can switch to `astral-sh/setup-uv` if pinning becomes important


---

## ADR-013: Bluesky Social Scraper Architecture (PO-038)

**Date:** 2026-04-06
**Status:** Accepted

### Context

Sprint 5 requires a Tier 3 social signal scraper for Bluesky (bsky.app) to ingest
launch-related posts from both keyword searches and tracked official accounts.
Requirements: zero credentials (anonymous public API only), plain httpx GET calls
(no atproto library), rate-limited at 1 req/3s.

### Decision

Implement `BlueskyScraper(BaseScraper)` in `project/src/openorbit/scrapers/bluesky.py`.

**Class-level constants:**
- `SEARCH_TERMS: ClassVar[tuple[str,...]]` — ("launch", "liftoff", "rocket", "satellite", "spacecraft")
- `TRACKED_ACCOUNTS: ClassVar[tuple[str,...]]` — (nasa.gov, spacex.com, nasaspaceflight.com, spaceflightnow.com, esa.int)
- `source_tier = 3`, `evidence_type = "media"`

**HTTP endpoints (anonymous, no credentials):**
- Search: `https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q={term}&limit=25`
- Account feed: `https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor={handle}&limit=25`

**Deduplication strategy:**
- Slug: `sha1("bluesky|{post_uri}")` — unique per Bluesky post AT-URI
- Second scrape of same post → `upsert_launch_event` is idempotent, attribution deduped by `add_attribution`

**Parsing (post → LaunchEventCreate):**
- `name`: first 120 chars of post text (truncated with "…" if longer)
- `provider`: author handle (e.g., `nasa.gov`)
- `launch_date`: `createdAt` field parsed as UTC datetime; fallback to `datetime.now(UTC)`
- `launch_date_precision`: `"day"` (social posts rarely carry exact launch times)
- `status`: `"scheduled"` (social signals are pre-event)
- `claim_lifecycle`: `"rumor"` — unverified social signal
- `event_kind`: `"inferred"` — assembled from social signals, not official schedule
- `launch_type`: `"unknown"`
- Relevance filter: post text must contain at least one SEARCH_TERMS keyword (case-insensitive)

**Scrape flow:**
1. Ensure source registered at `source_tier=3`
2. For each SEARCH_TERM → `searchPosts` API → collect posts, `asyncio.sleep(3.0)` after each call
3. For each TRACKED_ACCOUNT → `getAuthorFeed` API → collect posts, `asyncio.sleep(3.0)` after each call
4. Deduplicate collected posts by URI (dict keyed on URI)
5. Filter: keep only posts containing at least one keyword in text
6. Parse each post → `LaunchEventCreate` → `upsert_launch_event` → `add_attribution`

**Attribution metadata:**
- `evidence_type="media"`, `source_tier=3`
- `confidence_rationale="Tier 3 social signal — Bluesky"`
- `source_url=` post URI link (`https://bsky.app/profile/{handle}/post/{rkey}`)

**Rate limiting:** `asyncio.sleep(3.0)` between every HTTP call (search terms + account feeds).

**OSINT source registration:** one entry named `"Bluesky Social"` at `source_tier=3`.

### Alternatives Considered

- **`atproto` Python library**: Rejected per acceptance criteria (no third-party AT Protocol lib).
- **Authenticated API**: Rejected — public anonymous endpoint sufficient for Tier 3 signals.
- **`PublicFeedScraper` base**: Rejected — that base handles RSS/Atom XML; Bluesky returns JSON.

### Consequences

- ✅ Zero credentials — fully anonymous, no API key rotation needed
- ✅ Consistent with Tier 3 claim lifecycle (rumor/inferred) 
- ✅ Slug-based dedup (ADR-9) prevents duplicate events across repeated scrapes
- ✅ `asyncio.sleep(3.0)` respects public API rate limits
- ⚠️ Post text used as event name — low fidelity; enriched by downstream corroboration
- ⚠️ No pagination — limited to 25 results per term/account (sufficient for Tier 3 signals)

---

## ADR-021: FTS5 Full-Text Search for Launch Events

**Status:** Accepted  
**Date:** 2026-04-06  
**Sprint Item:** PO-034

**Context:**  
Users need to search launch events by name, provider, vehicle, and location using natural language queries. The existing API supports structured filtering (by date, status, tier, etc.) but not full-text search. SQLite's FTS5 extension provides performant full-text search with BM25 ranking built-in. The schema already has a basic FTS5 table (`launch_events_fts`) with only `slug` and `name` fields, but this needs expansion to support comprehensive search.

**Decision:**  
Expand the existing `launch_events_fts` FTS5 virtual table to include `provider`, `vehicle`, and `location` fields in addition to `slug` and `name`. Use SQLite FTS5's content table feature to avoid data duplication — the FTS table is an index over `launch_events`, not a separate copy. Maintain sync via three triggers (`AFTER INSERT`, `AFTER UPDATE`, `AFTER DELETE`). Add a new `fts_search()` repository function in `db.py` that combines FTS5 `MATCH` queries with existing tier/limit/offset filters. Expose this via a new `?q=` query parameter on `GET /v1/launches`. Results are ranked by FTS5's BM25 algorithm (`ORDER BY rank`).

**Migration Strategy:**  
The FTS table and triggers are defined in `schema.sql`, so they apply to new installs automatically. For existing databases, the `init_db_schema()` function in `db.py` already runs the schema via `executescript()`, which is idempotent (`IF NOT EXISTS`). After creating/updating the FTS table, a one-time backfill is performed using FTS5's `rebuild` command: `INSERT INTO launch_events_fts(launch_events_fts) VALUES('rebuild')`. This atomic operation repopulates the index from the content table.

**API Behavior:**  
When `?q=` is present on `GET /v1/launches`, the endpoint delegates to `fts_search()` instead of `get_launch_events()`. FTS search still respects `result_tier`, `limit`, and `offset` filters but ignores date/provider/status filters (since FTS matching is the primary filter). If `?q=` is absent, the existing filter logic remains unchanged.

**Consequences:**  
- ✅ **Fast full-text search** across name, provider, vehicle, location with BM25 relevance ranking
- ✅ **No new dependencies** — SQLite FTS5 is built-in (requires SQLite ≥3.9.0, which all modern systems have)
- ✅ **Idempotent migration** — safe to run on new and existing databases
- ✅ **Automatic sync** — triggers keep FTS index current with every insert/update/delete
- ✅ **Minimal storage overhead** — FTS5 content tables don't duplicate data, just index tokens
- ❌ **Write amplification** — every insert/update on `launch_events` triggers FTS index updates (negligible for this workload)
- ❌ **Limited query syntax** — FTS5 uses SQLite's FTS query syntax, not full regex or natural language understanding

**Alternatives Considered:**  
1. **Elasticsearch / Meilisearch** — Rejected due to operational complexity and external dependency overhead for this scale
2. **PostgreSQL tsvector** — Would require migrating from SQLite (out of scope for PO-034)
3. **Python-side fuzzy matching** — Too slow for large datasets, no relevance ranking

---
