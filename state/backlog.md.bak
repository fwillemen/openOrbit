# openOrbit — Product Backlog

> **Product:** openOrbit — Global Launch Event Tracking & Analysis API  
> **Owner:** Product Owner Agent  
> **Source:** `state/goal.md` — OSINT-powered launch tracking API, modelled on RocketLaunch Live  
> **Last updated:** 2025-07-14 (full reassessment)

---

## Summary

| Priority     | Count | Done |
|--------------|-------|------|
| Must Have    | 17    | 13   |
| Should Have  | 6     | 0    |
| Could Have   | 2     | 0    |
| Won't Have   | 3     | —    |
| **Total**    | **28**| **13**|

---

## Reassessment Notes

This backlog was critically reassessed after 13 delivered items. The remaining items
were re-evaluated against three questions:

1. **What prevents safe public exposure of this API today?**  
   → No auth system; `scrapers/notams.py` has **0% test coverage** (105/105 stmts); 
   `main.py` lifecycle is **44% covered** — startup/shutdown reliability is dark.

2. **What does the success criteria in `goal.md` require that isn't done?**  
   → "API is stable, **documented**, and usable for dashboards" — no developer guide exists.  
   → "Must be **modular** to allow adding new data sources" — `base.py` exists but is 
   **0% covered** and undocumented; the registry pattern is absent.

3. **What carry-forward technical debt is serious enough to block production?**  
   → `notams.py` (0%), `base.py` (0%), `main.py` lifecycle (44%), `sources.py` (53%), 
   `launches.py` error paths (77%) — collectively these represent untested critical paths.

**Changes made:**
- PO-014 (OpenAPI docs): **promoted to Must Have** — success criterion explicitly requires "documented"
- PO-015 (Plugin interface): **promoted to Must Have** — goal constraint + base.py at 0% coverage
- PO-016 (Admin endpoints): kept Should Have — depends on PO-024 (auth)
- PO-017 (4th OSINT source): **promoted to Should Have** — original scope lists news/OSINT aggregators
- PO-018 (Event history): kept Could Have — valuable analytics, not production-critical
- PO-019 (Webhooks/SSE): kept Could Have — stretch goal
- **PO-023 added (Must Have)**: Test coverage hardening — notams.py 0%, main.py lifecycle, error branches
- **PO-024 added (Must Have)**: API key authentication — required for protected endpoints
- **PO-025 added (Should Have)**: PostgreSQL migration path — explicitly listed in goal.md
- **PO-026 added (Should Have)**: CI/CD pipeline — production-readiness gate

---

## Must Have

> Core functionality without which the product fails to meet its success criteria.
> PO-001 through PO-013 are **done**. PO-014, PO-015, PO-023, PO-024 are the
> remaining Must Have items identified through post-delivery gap analysis.

---

### PO-001: Project Bootstrap, Repository Structure & Configuration Management

**Priority:** Must Have  
**Description:** Establish the full project skeleton — Python package layout, `uv`
dependency management, environment-variable config, structured logging, and a minimal
FastAPI app with a health check. Foundation for every subsequent item.

**Acceptance Criteria:**
- [x] `uv` project initialised; `pyproject.toml` defines `openorbit` package under `src/`
- [x] Package layout: `src/openorbit/{main.py, config.py, db.py, api/, scrapers/, models/}`
- [x] `config.py` reads all settings from environment variables with sensible defaults
- [x] `GET /health` returns `{"status": "ok", "version": "<semver>"}` with HTTP 200
- [x] `uv run uvicorn openorbit.main:app --reload` starts with no errors
- [x] `uv run pytest tests/` passes health-check smoke test
- [x] `.env.example` documents all required environment variables
- [x] `README.md` updated with local-dev quickstart

**Status:** `done`

---

### PO-002: Core Database Schema & SQLite Persistence Layer

**Priority:** Must Have  
**Description:** SQLite schema for launch events, OSINT sources, event attributions,
and raw scrape records. Thin async repository layer (aiosqlite). Idempotent init.
Typed helpers: `upsert_launch_event()`, `get_launch_events()`, `add_attribution()`,
`log_scrape_run()`. Schema designed for future PostgreSQL migration.

**Acceptance Criteria:**
- [x] `state/schema.sql` defines `launch_events`, `osint_sources`, `event_attributions`, `raw_scrape_records`
- [x] `launch_events` has all required columns including `confidence_score`, `launch_type`, `inference_flags`
- [x] `db.py` exposes typed async helpers
- [x] Database initialised by `uv run python -m openorbit.db init` (idempotent)
- [x] Helpers covered by unit tests using in-memory SQLite fixture

**Status:** `done`

---

### PO-003: OSINT Scraper — Space Agency Launch Schedules (Source 1)

**Priority:** Must Have  
**Description:** First production OSINT scraper. Targets NASA's public schedule /
Launch Library 2 public API. Extracts, normalises, and persists events. Idempotent
upsert. Respects `SCRAPER_DELAY_SECONDS`. Stores raw responses.

**Acceptance Criteria:**
- [x] `src/openorbit/scrapers/space_agency.py` implements `SpaceAgencyScraper`
- [x] Scraper fetches from ≥1 public space-agency source via `httpx`
- [x] Respects `SCRAPER_DELAY_SECONDS` (default 2 s)
- [x] Raw response stored in `raw_scrape_records`
- [x] Parsed events upserted idempotently
- [x] Unit tests mock HTTP layer; assert parsing of ≥3 sample payloads

**Status:** `done`

---

### PO-004: Data Normalization Pipeline & Canonical LaunchEvent Model

**Priority:** Must Have  
**Description:** Pydantic v2 `LaunchEvent` model and `normalize()` pipeline. Handles
multiple date formats → ISO 8601, provider alias resolution, pad-to-lat/lon lookup,
launch type coercion. `NormalizationError` logged and flagged in DB.

**Acceptance Criteria:**
- [x] `models/launch_event.py` defines `LaunchEvent` (Pydantic v2) with field validators
- [x] `pipeline/normalizer.py` implements `normalize(raw, source) -> LaunchEvent`
- [x] Handles ISO 8601, `YYYY-MM-DD`, `Month DD, YYYY`, Unix timestamps
- [x] Provider aliases in `pipeline/aliases.py`
- [x] Pad lookup covers ≥10 common launch sites
- [x] ≥90% coverage on normalizer module; `NormalizationError` path tested

**Status:** `done`

---

### PO-005: REST API — Core Launch Listing & Detail Endpoints

**Priority:** Must Have  
**Description:** Primary user-facing output. `GET /v1/launches` with date/provider/
type/status filters. `GET /v1/launches/{id}` with full source attribution and
confidence score. Standard response envelope.

**Acceptance Criteria:**
- [x] `GET /v1/launches` paginated, filterable by date, provider, type, status
- [x] `GET /v1/launches/{id}` returns full detail with `sources` and `confidence_score`
- [x] HTTP 404 for missing events; HTTP 422 for invalid params
- [x] Integration tests cover list (empty + populated), detail (found + not found), filters

**Status:** `done`

---

### PO-006: OSINT Scraper — Commercial Launch Providers (Source 2)

**Priority:** Must Have  
**Description:** Second OSINT scraper. SpaceX press kit + Rocket Lab. Feeds the same
normalization pipeline. Idempotent, rate-limited, attribution-tagged.

**Acceptance Criteria:**
- [x] `scrapers/commercial.py` implements `CommercialLaunchScraper`
- [x] Covers ≥2 commercial providers; respects rate limiting
- [x] Unit tests with mocked HTTP; ≥1 sample payload per provider

**Status:** `done`

---

### PO-007: OSINT Scraper — Public NOTAMs & Maritime Advisories (Source 3)

**Priority:** Must Have  
**Description:** Third OSINT scraper. FAA NOTAM public endpoint. Keyword extraction
(`ROCKET`, `MISSILE`, `SPACE LAUNCH`, `RANGE CLOSURE`). Launch type inference from
keywords. Stored in `raw_scrape_records`.

**Acceptance Criteria:**
- [x] `scrapers/notams.py` implements `NotamScraper`
- [x] Keyword regex/filter in `pipeline/notam_parser.py`
- [x] `launch_type` inferred from keyword presence
- [x] Unit tests: keyword extraction from ≥3 NOTAM sample strings

**Status:** `done`

---

### PO-008: Multi-Source Aggregation, Deduplication & Entity Merging

**Priority:** Must Have  
**Description:** Post-scrape deduplication pass. Events clustered by provider + date
window (±3 days) + location. Merged records retain all source attributions. Confidence
formula: `min(0.3 * num_sources + 0.4, 1.0)`. Idempotent, performance-bounded.

**Acceptance Criteria:**
- [x] `pipeline/deduplicator.py` implements `deduplicate_and_merge()`
- [x] Duplicate criteria: same provider, dates ≤3 days apart, same location
- [x] Merged event retains union of attributions; idempotent
- [x] Unit tests: exact duplicate, near-duplicate, non-duplicate

**Status:** `done`

---

### PO-009: Source Attribution, Confidence Scoring & Launch Type Classification

**Priority:** Must Have  
**Description:** Every API response carries source attribution, confidence score
(0.0–1.0), and launch type classification. Classifier uses source identity, provider
name, and keyword signals. Known military programs list (OSINT-only).

**Acceptance Criteria:**
- [x] Responses include `sources` array with name, URL, `scraped_at`
- [x] `confidence_score` stored and updated by deduplicator
- [x] `pipeline/classifier.py` assigns type; unit tests cover ≥5 distinct scenarios
- [x] `GET /v1/launches?launch_type=public_report` filters correctly

**Status:** `done`

---

### PO-010: APScheduler Background Refresh Jobs & Respectful Scraping

**Priority:** Must Have  
**Description:** APScheduler `AsyncIOScheduler` runs each scraper on a configurable
interval. Per-host rate limiting via `httpx` limits. Errors logged without crashing
the scheduler. Clean startup/shutdown in FastAPI `lifespan`.

**Acceptance Criteria:**
- [x] `scheduler.py` registers each scraper as a separate interval job
- [x] Refresh interval configurable per-source
- [x] Failed scrape run logged; scheduler continues
- [x] `GET /v1/sources` returns `last_scraped_at`, `event_count`, `last_error`
- [x] Scheduler starts/stops in lifespan

**Status:** `done`

---

### PO-011: Basic Inference & Multi-Source Correlation Layer

**Priority:** Must Have  
**Description:** Post-deduplication inference engine with ≥3 rules:
`multi_source_corroboration` (confidence +0.2 for ≥2 source categories),
`historical_pad_pattern` (pad reuse within 30 days), `notam_cluster_signal`
(≥2 NOTAMs within 100 km / 7 days). Events annotated with `inference_flags`.

**Acceptance Criteria:**
- [x] `pipeline/inference.py` implements `InferenceEngine` with ≥3 rules
- [x] `inference_flags` column in `launch_events`
- [x] `GET /v1/launches/{id}` includes `inference_flags`
- [x] `GET /v1/launches?has_inference_flag=notam_cluster` filters by flag
- [x] Unit tests: positive + negative case per rule

**Status:** `done`

---

### PO-012: Docker Deployment — Dockerfile & docker-compose

**Priority:** Must Have  
**Description:** Minimal `python:3.12-slim` multi-stage Docker image. Non-root user.
`docker-compose.yml` for local dev with volume-mounted DB. `docs/deployment.md`.

**Acceptance Criteria:**
- [x] Multi-stage `Dockerfile`; non-root user; image < 300 MB
- [x] `docker-compose.yml` starts API on port 8000 with data volume
- [x] `docker build` and `docker run --env-file .env` both succeed; `/health` returns 200
- [x] `docs/deployment.md` documents build, run, and compose commands

**Status:** `done`

---

### PO-013: API Rate Limiting, Cursor Pagination & Advanced Query Filtering

**Priority:** Must Have  
**Description:** Per-IP rate limiting (60 req/min), HTTP 429 with `Retry-After`,
rate-limit headers. Cursor-based pagination. Additional filters: `?provider` (fuzzy),
`?min_confidence`, `?location&radius_km`. All covered by integration tests.

**Acceptance Criteria:**
- [x] Rate limiting: 60 req/min per IP; HTTP 429 with `Retry-After` header
- [x] `X-RateLimit-Limit` and `X-RateLimit-Remaining` headers in responses
- [x] Cursor-based pagination with `?cursor` and `?limit` (max 100)
- [x] Filters: `?provider` (fuzzy), `?min_confidence`, `?location&radius_km`
- [x] All new filters covered by integration tests

**Status:** `done`

---

### PO-014: OpenAPI Documentation, Swagger UI & Developer Guide

**Priority:** Must Have  
**Description:** The success criterion states the API must be "stable, **documented**,
and usable for dashboards". FastAPI auto-generates the OpenAPI spec; this item enriches
it with descriptions, examples, and a written developer guide that makes openOrbit
consumable by external developers without reading source code.

**Why Must Have:** The success criteria is not met until documentation exists. Without
it, dashboard and analytics consumers cannot use the API effectively — the primary user
value proposition is blocked. This is the difference between "built" and "delivered".

**Acceptance Criteria:**
- [ ] Every endpoint has a `summary`, `description`, and tagged OpenAPI group
- [ ] Every query parameter has `description=` and a typed `example=` value in `Field()`
- [ ] Every response model field has `description=` in its Pydantic field definition
- [ ] `GET /docs` (Swagger UI) and `GET /redoc` are reachable and fully populated
      with no "missing description" gaps
- [ ] `GET /openapi.json` returns a valid OpenAPI 3.1 spec (validated with `openapi-spec-validator`)
- [ ] `docs/api.md` written with: overview, endpoint reference, example `curl` commands
      and full JSON responses for each endpoint
- [ ] `docs/api.md` includes a "Confidence Score" explainer and a "Launch Type" guide
- [ ] Snapshot test asserts `/openapi.json` schema does not regress between runs

**Status:** `pending`

---

### PO-015: Modular Source Plugin Interface & Registry

**Priority:** Must Have  
**Description:** The goal states the system "Must be modular to allow adding new data
sources over time." `scrapers/base.py` exists but has **0% test coverage** (8/8 statements
uncovered) and no registry or auto-discovery. Adding a new scraper today requires
editing core scheduler code — violating the modularity constraint.

**Why Must Have:** This is an explicit architectural constraint from `goal.md`. The
plugin interface is partially built but unverified and undocumented, making it
effectively non-functional as a contract. A developer following the goal cannot add
a fourth source without modifying core code.

**Acceptance Criteria:**
- [ ] `scrapers/base.py` `BaseScraper` abstract class is fully tested (100% coverage):
      all abstract methods, `ScrapeResult` dataclass, error handling path
- [ ] `ScraperRegistry` in `scrapers/registry.py` allows registering and discovering
      scrapers without modifying scheduler or pipeline code
- [ ] All three existing scrapers verified to conform to `BaseScraper` interface
      via a registry round-trip integration test
- [ ] Adding a `MockScraper` (implementing `BaseScraper`) in tests auto-registers
      and executes through the full pipeline without any core code changes
- [ ] `docs/adding-sources.md` written: step-by-step guide (implement → register → verify)
- [ ] Scheduler reads active scrapers from the registry, not a hardcoded list
- [ ] Existing scraper tests still pass after refactor (zero regressions)

**Status:** `pending`

---

### PO-023: Test Coverage Hardening — Critical Untested Paths

**Priority:** Must Have  
**Description:** Coverage analysis reveals three critical zero-or-near-zero zones
that make the system unreliable to operate in production:

- **`scrapers/notams.py`: 0% coverage** (105/105 statements uncovered) — a core scraper
  with zero test coverage means any regression in NOTAM parsing goes undetected
- **`scrapers/base.py`: 0% coverage** (8/8 statements) — plugin contract is untested
- **`main.py` ASGI lifecycle: 44% covered** (19/43 missing) — startup/shutdown
  error paths (DB init failure, scheduler crash) are dark; production incidents here
  are blind
- **`api/v1/sources.py`: 53% covered** (8/17 missing) — source listing error branches
  untested
- **`api/v1/launches.py`: 77% covered** (22/96 missing) — DB error paths, edge-case
  filter combinations, and cursor pagination error handling uncovered

**Why Must Have:** Zero coverage on a deployed scraper and an untested ASGI lifecycle
are production reliability risks, not cosmetic debt. A bug in NOTAM parsing or a
startup failure will go undetected. This must be resolved before the API is
considered production-ready.

**Acceptance Criteria:**
- [ ] `scrapers/notams.py` reaches ≥85% coverage via `respx`-mocked HTTP tests:
      - Happy path: valid NOTAM response parsed and persisted
      - Keyword match: `ROCKET`, `MISSILE`, `SPACE LAUNCH` each trigger correct `launch_type`
      - HTTP error (4xx/5xx): scraper logs error and returns empty result without raising
      - Network timeout: scraper catches `httpx.TimeoutException` and logs gracefully
- [ ] `scrapers/base.py` reaches 100% coverage:
      - Abstract method enforcement test (instantiating `BaseScraper` raises `TypeError`)
      - `ScrapeResult` fields and defaults tested
- [ ] `main.py` ASGI lifecycle reaches ≥85% coverage:
      - Lifespan startup success path: DB init called, scheduler started
      - Lifespan startup with DB init failure: exception propagated cleanly
      - Lifespan shutdown: `stop_scheduler()` and `close_db()` both called in order
      - `configure_logging()` dev mode vs production mode branches
- [ ] `api/v1/sources.py` reaches ≥85% coverage:
      - Empty sources list returns `{"data": []}`
      - Source with no attributions returns `event_count: 0`
      - Source with attributions returns correct `event_count`
      - DB error returns HTTP 500
- [ ] `api/v1/launches.py` reaches ≥90% coverage:
      - Cursor decode error on malformed `?cursor=` returns HTTP 422
      - DB error on list endpoint returns HTTP 500
      - `?min_confidence` boundary values (0.0, 1.0, out of range) tested
      - `?location&radius_km` with invalid lat/lon returns HTTP 422
- [ ] Overall project test coverage is ≥85% (currently below this for several modules)
- [ ] All new tests use `pytest-asyncio` + `respx` for HTTP mocking; no real network calls

**Status:** `pending`

---

### PO-024: API Key Authentication for Protected Endpoints

**Priority:** Must Have  
**Description:** Without any authentication, there is no mechanism to protect
administrative or write operations. The admin endpoints planned in PO-016 require auth.
More critically, exposing a completely open API to the public internet without any key
mechanism prevents usage tracking and makes abuse mitigation impossible beyond IP rate
limiting. Implement a lightweight, header-based API key system for protected routes.

**Why Must Have:** The API cannot be safely exposed publicly without a minimal auth
boundary. Admin operations (manual scrape triggers, source management) must be
protected. This is also a prerequisite for PO-016 (admin endpoints).

**Acceptance Criteria:**
- [ ] `config.py` gains `ADMIN_API_KEY` setting (required env var, no default — app
      refuses to start if unset and `REQUIRE_ADMIN_KEY=true`)
- [ ] `src/openorbit/middleware/auth.py` implements `require_api_key` FastAPI dependency:
      reads `X-API-Key` header; raises HTTP 401 with `{"error": "unauthorized"}` if missing
      or incorrect; accepts correct key and lets request proceed
- [ ] `GET /v1/admin/*` routes (future PO-016) are wired to `require_api_key` dependency
      (or a placeholder admin router is created now for future use)
- [ ] Public endpoints (`GET /v1/launches`, `GET /v1/launches/{id}`, `GET /v1/sources`,
      `GET /health`) remain open — no key required
- [ ] Invalid key returns HTTP 401; missing key returns HTTP 401; correct key allows access
- [ ] Key comparison uses `secrets.compare_digest()` to prevent timing attacks
- [ ] `docs/api.md` updated with an "Authentication" section explaining the header scheme
- [ ] Integration tests cover: missing key → 401, wrong key → 401, correct key → 200,
      public endpoint without key → 200

**Status:** `pending`

---

## Should Have

> Important for a production-quality service; deferred from Must Have but should land
> before the product is widely promoted.

---

### PO-016: Admin & Source Health Monitoring Endpoints

**Priority:** Should Have  
**Description:** Lightweight admin surface (protected by `X-API-Key` from PO-024) for
operators to inspect source health, trigger manual scrape runs, and view system
statistics — without needing SSH or database access.

**Depends on:** PO-024 (API key auth)

**Acceptance Criteria:**
- [ ] `GET /v1/admin/sources` lists all sources with last-run status, event counts,
      error rates (requires valid `X-API-Key`)
- [ ] `POST /v1/admin/sources/{id}/refresh` triggers immediate scrape of a single source
- [ ] `GET /v1/admin/stats` returns: total events, events per source, per launch type,
      average confidence score, last full refresh timestamp
- [ ] HTTP 401 when `X-API-Key` missing or wrong; HTTP 404 when source ID not found
- [ ] Admin routes tagged separately in OpenAPI ("Admin — key required")
- [ ] Integration tests: authenticated access, unauthenticated rejection, manual refresh,
      refresh of non-existent source returns 404

**Status:** `pending`

---

### PO-017: Fourth OSINT Source — News & OSINT Aggregator Scraper

**Priority:** Should Have  
**Description:** `goal.md` explicitly lists "News and OSINT aggregators" as a fourth
planned source alongside space agencies, commercial providers, and NOTAMs. Adding it
completes the original source plan, increases confidence scoring diversity, and
exercises the plugin interface from PO-015 as a real-world validation.

**Depends on:** PO-015 (plugin interface must be in place)

**Acceptance Criteria:**
- [ ] `src/openorbit/scrapers/news.py` implements `NewsAggregatorScraper` extending `BaseScraper`
- [ ] Scraper targets ≥2 public RSS feeds (e.g. SpaceFlightNow.com, NASASpaceflight.com)
- [ ] Parsed articles matched to existing events via fuzzy provider + date entity linking
- [ ] New source auto-registered via `ScraperRegistry`; scheduler picks it up without
      any changes to scheduler code
- [ ] Unit tests with mocked RSS/HTML responses; ≥2 sample payloads
- [ ] `osint_sources` table gains a row for each RSS feed; total sources in system ≥4
- [ ] `GET /v1/sources` correctly reflects the new source with its `last_scraped_at`

**Status:** `pending`

---

### PO-025: PostgreSQL Migration Path — Schema & Connection Abstraction

**Priority:** Should Have  
**Description:** `goal.md` states the database is "SQLite (initial) → optional
PostgreSQL later." The current `db.py` uses `aiosqlite` directly, with SQLite-specific
syntax in several queries. This item adds a connection abstraction that swaps backends
via `DATABASE_URL`, validates the schema is PostgreSQL-compatible, and provides a
migration guide — making the eventual move to PostgreSQL a configuration change, not a
rewrite.

**Acceptance Criteria:**
- [ ] `DATABASE_URL` env var (e.g. `sqlite+aiosqlite:///...` or `postgresql+asyncpg://...`)
      controls which backend `db.py` uses
- [ ] `schema.sql` reviewed and updated so all SQL is ANSI-compatible; any SQLite-specific
      syntax (e.g. `AUTOINCREMENT`) replaced with portable equivalents
- [ ] `db.py` uses an abstraction layer (e.g. `databases` library or thin adapter) that
      passes identical queries to both backends without duplication
- [ ] `docker-compose.yml` gains an optional `postgres` service profile; switching from
      SQLite to PostgreSQL requires only changing `DATABASE_URL`
- [ ] `docs/deployment.md` updated with PostgreSQL setup instructions
- [ ] Integration test suite runs against both SQLite (default) and PostgreSQL (via
      `pytest --db-backend=postgres` marker); all tests pass on both

**Status:** `pending`

---

### PO-026: CI/CD Pipeline — Automated Testing & Linting Gate

**Priority:** Should Have  
**Description:** There is currently no automated gate preventing broken code from
reaching `main`. For a production API that aggregates OSINT data on a schedule, an
undetected regression in a scraper or the API layer could silently corrupt data.
A CI pipeline running on every pull request is the minimum safety net needed before
wider promotion of the API.

**Acceptance Criteria:**
- [ ] `.github/workflows/ci.yml` (or equivalent) runs on every PR and push to `main`
- [ ] CI pipeline steps: `uv sync` → `ruff check` (lint) → `ruff format --check` →
      `mypy` (type check) → `pytest --cov=openorbit --cov-fail-under=85`
- [ ] Pipeline fails and blocks merge if any step fails or coverage drops below 85%
- [ ] Workflow caches `uv` dependencies for fast runs (< 3 min total target)
- [ ] `README.md` updated with a CI status badge
- [ ] `pyproject.toml` already defines `[tool.ruff]`, `[tool.mypy]`, and `[tool.pytest]`
      sections; CI uses these directly (no duplicated config)
- [ ] Docker build step (`docker build .`) included in CI to catch `Dockerfile` regressions

**Status:** `pending`

---

## Could Have

> Valuable analytics features deferred without product risk. Implement only if sprint
> capacity allows after all Must Have and Should Have items are complete.

---

### PO-018: Launch Event History & Status Change Tracking

**Priority:** Could Have  
**Description:** Track how launch events change over time (date slips, status changes,
vehicle swaps). Each significant change recorded in an `event_history` table.
`GET /v1/launches/{id}/history` exposes the change log. Valuable for analytics
dashboards tracking scheduling reliability trends.

**Acceptance Criteria:**
- [ ] `event_history` table: `(id, launch_event_id, field_changed, old_value, new_value, changed_at, source_id)`
- [ ] `upsert_launch_event()` writes history records when `launch_date`, `status`,
      `vehicle`, or `confidence_score` changes by more than a configurable threshold
- [ ] `GET /v1/launches/{id}/history` returns chronological list of changes
- [ ] History records are append-only (never deleted)
- [ ] Unit tests: history written on status change; no history written on no-op upsert

**Status:** `pending`

---

### PO-019: Webhook / Server-Sent Events for Launch Updates

**Priority:** Could Have  
**Description:** Allow API consumers to subscribe to near-real-time launch event
updates via SSE or configurable webhooks. Eliminates consumer polling. Webhook
delivery with exponential-backoff retry. Feature-flagged via `ENABLE_STREAMING`.

**Acceptance Criteria:**
- [ ] `GET /v1/launches/stream` returns SSE stream; events emitted on new/updated launches
- [ ] `POST /v1/webhooks` registers a URL; `DELETE /v1/webhooks/{id}` removes it
- [ ] Webhook delivers `POST` with launch event JSON; retries up to 3× on failure
- [ ] Feature flag `ENABLE_STREAMING=true` required; endpoints 404 when disabled
- [ ] Integration test: mock webhook receiver asserts payload delivery

**Status:** `pending`

---

## Won't Have (this release)

> Explicitly out of scope. Documented here to prevent scope creep.

---

### PO-020: Real-time Military Intelligence or Classified Data Sources

**Priority:** Won't Have  
**Description:** Integration with classified, restricted, or real-time tactical military
intelligence feeds. Out of scope per project constraints and ethical guidelines.
All launch type classification is based solely on publicly available OSINT.

**Status:** `pending`

---

### PO-021: Frontend Web Application or Dashboard

**Priority:** Won't Have  
**Description:** A web-based UI, map visualization, or analytics dashboard.
The project is API-first. Consumers build their own frontends against the REST API.

**Status:** `pending`

---

### PO-022: Weapon Targeting or Actionable Defense Applications

**Priority:** Won't Have  
**Description:** Any feature that supports weapon targeting, real-time defense decision
support, or actionable military intelligence. Explicitly prohibited by project constraints.

**Status:** `pending`

**Status:** `pending`

