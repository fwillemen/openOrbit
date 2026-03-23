# Architecture Decision Records (ADRs)

> **Auto-updated by:** Architect agent  
> **Status:** 12 decisions recorded.

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
