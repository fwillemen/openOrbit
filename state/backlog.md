# openOrbit — Product Backlog

> **Product:** openOrbit — Global Launch Event Tracking & Analysis API  
> **Owner:** Product Owner Agent  
> **Source:** `state/goal.md` — OSINT-powered launch tracking API, modelled on RocketLaunch Live  
> **Last updated:** 2025-01-01

---

## Summary

| Priority     | Count | Done |
|--------------|-------|------|
| Must Have    | 11    | 0    |
| Should Have  | 5     | 0    |
| Could Have   | 3     | 0    |
| Won't Have   | 3     | —    |
| **Total**    | **22**| **0**|

---

## Backlog Story

The backlog is ordered to build from the ground up: **foundations first** (project
structure + database), then **data in** (scrapers + normalization), then **data out**
(REST API), then **multi-source aggregation** (deduplication + attribution + confidence),
then **scheduled automation** (refresh jobs), and finally the **inference layer**.
Should Have items extend and harden the MVP; Could Have items are stretch goals.

---

## Must Have

> Core functionality without which the product fails to meet its success criteria.

---

### PO-001: Project Bootstrap, Repository Structure & Configuration Management

**Priority:** Must Have  
**Description:** Establish the full project skeleton that every subsequent sprint item
builds on. This includes the Python package layout under `src/openorbit/`, dependency
management via `uv`, environment-variable–based configuration (making the app
Docker-compatible from day one), logging setup, and a minimal FastAPI application that
starts up and returns a `200 OK` health check. Without this foundation no other item
can be implemented.

**Acceptance Criteria:**
- [ ] `uv` project initialised; `pyproject.toml` defines `openorbit` package under `src/`
- [ ] Package layout: `src/openorbit/{main.py, config.py, db.py, api/, scrapers/, models/}`
- [ ] `config.py` reads all settings from environment variables with sensible defaults
      (e.g. `DATABASE_URL`, `LOG_LEVEL`, `REFRESH_INTERVAL_MINUTES`)
- [ ] `GET /health` endpoint returns `{"status": "ok", "version": "<semver>"}` with HTTP 200
- [ ] `uv run uvicorn openorbit.main:app --reload` starts the server with no errors
- [ ] `uv run pytest tests/` passes (at minimum the health-check smoke test)
- [ ] `.env.example` file documents all required environment variables
- [ ] `README.md` updated with local-dev quickstart (`uv sync && uv run uvicorn …`)

**Status:** `pending`

---

### PO-002: Core Database Schema & SQLite Persistence Layer

**Priority:** Must Have  
**Description:** Design and implement the SQLite database schema that stores all launch
events, OSINT sources, per-event source attributions, and raw scrape records. The schema
must be normalised enough to support multi-source deduplication and confidence scoring
in later sprints, while remaining simple enough to migrate to PostgreSQL without rewrites.
All DB access goes through a thin repository layer (no ORM required; raw `aiosqlite` or
`sqlite3` with typed helpers is fine).

**Acceptance Criteria:**
- [ ] `state/schema.sql` (project schema, separate from fleet schema) defines tables:
      `launch_events`, `osint_sources`, `event_attributions`, `raw_scrape_records`
- [ ] `launch_events` columns: `id`, `slug`, `name`, `launch_date`, `launch_date_precision`
      (`exact`/`day`/`week`/`month`), `provider`, `vehicle`, `location`, `pad`,
      `launch_type` (`civilian`/`military`/`public_report`/`unknown`),
      `status` (`scheduled`/`success`/`failure`/`unknown`),
      `confidence_score` (0.0–1.0), `created_at`, `updated_at`
- [ ] `osint_sources` columns: `id`, `name`, `url`, `scraper_class`, `enabled`, `last_scraped_at`
- [ ] `event_attributions` links events to sources with a `raw_scrape_record_id`
- [ ] `raw_scrape_records` stores the original HTML/JSON payload per scrape run (for audit)
- [ ] `db.py` exposes typed async helpers: `upsert_launch_event()`, `get_launch_events()`,
      `add_attribution()`, `log_scrape_run()`
- [ ] Database initialised by `uv run python -m openorbit.db init` (idempotent)
- [ ] All helpers covered by unit tests using an in-memory SQLite fixture

**Status:** `pending`

---

### PO-003: OSINT Scraper — Space Agency Launch Schedules (Source 1)

**Priority:** Must Have  
**Description:** Implement the first production OSINT scraper targeting publicly available
space agency launch schedules. Primary target: NASA's public launch schedule page and/or
the Launch Library 2 public API (api.thespacedevs.com — free tier, no auth required).
The scraper must extract structured launch data, map it to the canonical `LaunchEvent`
model, and persist it via the DB layer. This delivers the first real data into the system.

**Acceptance Criteria:**
- [ ] `src/openorbit/scrapers/space_agency.py` implements `SpaceAgencyScraper`
- [ ] Scraper fetches data from ≥1 public space-agency source (NASA schedule page or
      Launch Library 2 public API) using `httpx` with a configurable timeout and retries
- [ ] Scraper respects a `SCRAPER_DELAY_SECONDS` config var (default: 2s between requests)
- [ ] Raw response stored in `raw_scrape_records` before any parsing
- [ ] Parsed events upserted into `launch_events`; re-runs are idempotent (no duplicates)
- [ ] Scraper populates: `name`, `launch_date`, `launch_date_precision`, `provider`,
      `vehicle`, `location`, `status`; `launch_type` defaults to `civilian`
- [ ] `uv run python -m openorbit.scrapers.space_agency` runs the scraper and prints
      a summary (`Scraped N events, N new, N updated`)
- [ ] Unit tests mock the HTTP layer and assert correct parsing of ≥3 sample payloads

**Status:** `pending`

---

### PO-004: Data Normalization Pipeline & Canonical LaunchEvent Model

**Priority:** Must Have  
**Description:** Define the canonical Python dataclass / Pydantic model for a
`LaunchEvent` and build a normalization pipeline that every scraper feeds into.
The pipeline handles: date parsing (multiple formats → ISO 8601), provider name
deduplication (e.g. "SpaceX" vs "Space Exploration Technologies"), location
normalization (pad → lat/lon lookup table), and launch type coercion. This ensures
that all scrapers output a uniform structure regardless of source quirks.

**Acceptance Criteria:**
- [ ] `src/openorbit/models/launch_event.py` defines `LaunchEvent` as a Pydantic v2 model
      with field validators for `launch_date`, `confidence_score`, and `launch_type`
- [ ] `src/openorbit/pipeline/normalizer.py` implements `normalize(raw: dict, source: str) -> LaunchEvent`
- [ ] Normalizer handles ISO 8601, `YYYY-MM-DD`, `Month DD, YYYY`, and Unix timestamp inputs
      for `launch_date`; raises `NormalizationError` on unparseable input
- [ ] Provider name aliases defined in `src/openorbit/pipeline/aliases.py`
      (e.g. `{"Space Exploration Technologies": "SpaceX", …}`)
- [ ] Pad-to-location lookup table covers ≥10 common launch sites with lat/lon
- [ ] All normalizer branches covered by pytest unit tests (≥90% coverage on the module)
- [ ] `NormalizationError` is logged and the raw record is flagged `parse_error = 1` in DB
      so no data is silently dropped

**Status:** `pending`

---

### PO-005: REST API — Core Launch Listing & Detail Endpoints

**Priority:** Must Have  
**Description:** Expose the launch event data through a clean, developer-friendly JSON
REST API. This is the primary user-facing output of the system. The API must be
queryable by date range, provider, launch type, and status. Responses must include
full source attribution and confidence score so consumers can assess data quality.

**Acceptance Criteria:**
- [ ] `GET /v1/launches` returns a paginated list of launch events (default page size: 25)
      with query parameters: `?from=<ISO date>`, `?to=<ISO date>`, `?provider=<str>`,
      `?launch_type=civilian|military|public_report|unknown`, `?status=scheduled|success|failure`
- [ ] `GET /v1/launches/{id}` returns a single event with full detail including
      `sources` (list of source names + URLs) and `confidence_score`
- [ ] Response envelope: `{"data": […], "meta": {"total": N, "page": P, "per_page": 25}}`
- [ ] Each launch event in the response includes all fields from `LaunchEvent` model
- [ ] HTTP 404 returned with `{"error": "not_found"}` when event ID does not exist
- [ ] HTTP 422 returned for invalid query parameter types
- [ ] API router lives in `src/openorbit/api/v1/launches.py` and is mounted at `/v1`
- [ ] Integration tests cover: list (empty DB, populated DB), detail (found, not found),
      all filter combinations
- [ ] FastAPI auto-generates `/docs` (Swagger UI) and `/redoc` endpoints

**Status:** `pending`

---

### PO-006: OSINT Scraper — Commercial Launch Providers (Source 2)

**Priority:** Must Have  
**Description:** Implement the second production OSINT scraper targeting publicly
available commercial launch provider schedules. Primary targets: SpaceX's press kit
page / r/SpaceX manifest (publicly available), Rocket Lab's mission page, and/or
Arianespace's launch schedule. The scraper feeds through the same normalization
pipeline as Source 1 and sets `launch_type = civilian`.

**Acceptance Criteria:**
- [ ] `src/openorbit/scrapers/commercial.py` implements `CommercialLaunchScraper`
- [ ] Scraper covers ≥2 distinct commercial providers (e.g. SpaceX + Rocket Lab)
- [ ] Uses `httpx` + `BeautifulSoup` / `selectolax` for HTML parsing where needed
- [ ] Respects `SCRAPER_DELAY_SECONDS` between requests to each host
- [ ] Raw responses stored in `raw_scrape_records`; parsed events upserted idempotently
- [ ] Events tagged with `osint_source_id` linking back to the correct `osint_sources` row
- [ ] `uv run python -m openorbit.scrapers.commercial` runs standalone with summary output
- [ ] Unit tests mock HTTP layer; assert correct parsing of ≥2 sample HTML/JSON payloads
      (one per provider)

**Status:** `pending`

---

### PO-007: OSINT Scraper — Public NOTAMs & Maritime Advisories (Source 3)

**Priority:** Must Have  
**Description:** Implement the third OSINT scraper targeting publicly available Notice
to Airmen (NOTAM) data and maritime area warnings (NAVAREAs). These sources often
contain advance warning of rocket and missile test activity — both civilian and
publicly reported military. Primary targets: the FAA NOTAM Search API (public, no auth)
and/or the NOTAM parsing service at `notams.aim.faa.gov`. Maritime warnings from
NAVAREA broadcasts (publicly posted by maritime authorities) are a secondary target.

**Acceptance Criteria:**
- [ ] `src/openorbit/scrapers/notams.py` implements `NotamScraper`
- [ ] Scraper fetches NOTAMs from FAA public endpoint or equivalent public source
- [ ] NOTAM text parsed for launch-related keywords (`ROCKET`, `MISSILE`, `SPACE LAUNCH`,
      `RANGE CLOSURE`) using a regex/keyword filter in `pipeline/notam_parser.py`
- [ ] Matched NOTAMs converted to `LaunchEvent` candidates with `launch_type` inferred
      from keyword presence (`ROCKET`/`SPACE` → `civilian`; `MISSILE` → `public_report`)
- [ ] `launch_date_precision` set to `day` or `week` based on NOTAM validity window
- [ ] Raw NOTAM text stored in `raw_scrape_records`
- [ ] Unit tests assert keyword extraction from ≥3 sample NOTAM strings
- [ ] `uv run python -m openorbit.scrapers.notams` runs standalone

**Status:** `pending`

---

### PO-008: Multi-Source Aggregation, Deduplication & Entity Merging

**Priority:** Must Have  
**Description:** With three scrapers producing events independently, duplicates will
exist (e.g. the same SpaceX launch appearing in both the commercial scraper and a
NOTAM). Implement a deduplication and merging pass that runs after each scrape cycle:
events are clustered by similarity (provider + date window + location) and merged
into a single canonical record that retains all source attributions. The confidence
score is increased for events seen in multiple sources.

**Acceptance Criteria:**
- [ ] `src/openorbit/pipeline/deduplicator.py` implements `deduplicate_and_merge()`
- [ ] Two events are considered duplicates if: same provider (after alias resolution)
      AND launch dates within 3 days of each other AND same launch site (after normalization)
- [ ] Merged event retains the union of all `event_attributions` from both source records
- [ ] Confidence score formula: `min(0.3 * num_sources + base_score, 1.0)` where
      `base_score` is 0.4 for a single source
- [ ] Deduplication is idempotent: running twice produces the same result
- [ ] `GET /v1/launches` never returns duplicate events for the same real-world launch
- [ ] Unit tests cover: exact duplicate, near-duplicate (±2 days), non-duplicate (different provider)
- [ ] Deduplication run time logged per cycle; target < 500 ms for 1 000 events

**Status:** `pending`

---

### PO-009: Source Attribution, Confidence Scoring & Launch Type Classification

**Priority:** Must Have  
**Description:** Every launch event exposed by the API must carry: (1) a list of the
OSINT sources it was derived from, including source name and URL; (2) a `confidence_score`
between 0.0 and 1.0 reflecting data quality and source corroboration; and (3) a
`launch_type` classification (`civilian`, `military`, `public_report`, `unknown`).
This satisfies the core success criterion: *"Launch events include metadata such as
confidence level and source attribution."*

**Acceptance Criteria:**
- [ ] `GET /v1/launches` and `GET /v1/launches/{id}` responses include `sources` array:
      `[{"name": "NASA Launch Schedule", "url": "https://…", "scraped_at": "…"}]`
- [ ] `confidence_score` is stored in DB and updated by `deduplicator.py` after each merge
- [ ] `launch_type` classifier in `pipeline/classifier.py` assigns type based on:
      source identity (NOTAM with MISSILE keyword → `public_report`),
      provider name (known military programs → `military`), default → `civilian`
- [ ] Known military launch programs list maintained in `pipeline/military_programs.py`
      (populated from publicly reported programs only — no classified data)
- [ ] `GET /v1/launches?launch_type=public_report` correctly filters events
- [ ] Unit tests: classifier assigns correct type for ≥5 distinct input scenarios
- [ ] `confidence_score` range validated; values outside [0.0, 1.0] raise `ValueError`

**Status:** `pending`

---

### PO-010: APScheduler Background Refresh Jobs & Respectful Scraping

**Priority:** Must Have  
**Description:** Automate the data refresh cycle so the API stays current without
manual intervention. APScheduler runs inside the FastAPI process and triggers each
scraper on a configurable interval (default: every 6 hours). The scheduler enforces
per-host rate limiting so no external site is hit more than once per `SCRAPER_DELAY_SECONDS`.
A `GET /v1/sources` endpoint exposes the health of each scraper (last run time, event count,
error status).

**Acceptance Criteria:**
- [ ] `src/openorbit/scheduler.py` sets up APScheduler with `AsyncIOScheduler`
- [ ] Each scraper registered as a separate job with its own `cron` or `interval` trigger
- [ ] Refresh interval configurable per-source via `osint_sources.refresh_interval_hours` column
- [ ] Per-host rate limiting: `httpx` client configured with `limits` and per-request delay
- [ ] Failed scrape run logs error to `raw_scrape_records` with `status = error` and
      `error_message`; scheduler does not crash on scraper failure
- [ ] `GET /v1/sources` returns list of sources with `last_scraped_at`, `event_count`,
      `last_error` (null if last run succeeded)
- [ ] Scheduler starts on app startup (`lifespan` event) and shuts down cleanly on stop
- [ ] Integration test: trigger scraper job manually via scheduler API, assert DB updated

**Status:** `pending`

---

### PO-011: Basic Inference & Multi-Source Correlation Layer

**Priority:** Must Have  
**Description:** Implement a lightweight inference layer that applies pattern-based
rules and multi-source correlation to improve event quality beyond raw scraping.
This layer runs as a post-processing step after deduplication. It detects: (a) launches
that appear in ≥2 independent source categories (agency + NOTAM), elevating confidence;
(b) launches whose date/location matches a known historical pad activity pattern;
(c) suspicious clustering of NOTAMs near known launch sites (a signal of activity).
Results annotate events with `inference_flags` (JSON array of applied rule names).

**Acceptance Criteria:**
- [ ] `src/openorbit/pipeline/inference.py` implements `InferenceEngine` with ≥3 rules:
      `multi_source_corroboration`, `historical_pad_pattern`, `notam_cluster_signal`
- [ ] `launch_events` table gains `inference_flags` column (JSON text, nullable)
- [ ] `multi_source_corroboration`: event seen in ≥2 source categories → confidence += 0.2
- [ ] `historical_pad_pattern`: launch date within 30 days of a previous launch from same pad
      → `inference_flags` includes `"pad_reuse_pattern"`
- [ ] `notam_cluster_signal`: ≥2 NOTAMs within 100 km and 7 days → flags nearby events
      with `"notam_cluster"`
- [ ] `GET /v1/launches/{id}` response includes `inference_flags` array
- [ ] `GET /v1/launches?has_inference_flag=notam_cluster` filters by flag
- [ ] Unit tests: ≥1 test per inference rule covering the positive and negative case
- [ ] Inference engine documented in `docs/inference.md` with rule descriptions

**Status:** `pending`

---

## Should Have

> Important for a production-quality service but not required for the MVP to function.

---

### PO-012: Docker Deployment — Dockerfile & docker-compose

**Priority:** Should Have  
**Description:** Package the application as a Docker image so it can be deployed
consistently across environments. Provide a `docker-compose.yml` for local development
that starts the API and (optionally) a volume-mounted SQLite database. The image should
be minimal (Python slim base), non-root, and configurable entirely via environment variables.

**Acceptance Criteria:**
- [ ] `Dockerfile` uses `python:3.12-slim`; multi-stage build (builder + runtime stages)
- [ ] Image runs as a non-root user (`appuser`)
- [ ] `docker-compose.yml` starts the API on `localhost:8000` with a volume for `data/`
- [ ] `docker build -t openorbit:latest .` succeeds with no errors
- [ ] `docker run --env-file .env openorbit:latest` starts the server and `/health` returns 200
- [ ] Image size < 300 MB
- [ ] `docs/deployment.md` documents Docker build, run, and compose commands
- [ ] `.dockerignore` excludes `state/`, `.git/`, `__pycache__/`, test fixtures

**Status:** `pending`

---

### PO-013: API Rate Limiting, Pagination & Advanced Query Filtering

**Priority:** Should Have  
**Description:** Harden the public API with per-IP rate limiting (to prevent abuse),
cursor-based pagination (to support large result sets efficiently), and additional
filter parameters (provider name search, location proximity, confidence threshold).
These features are needed for the API to be "usable for dashboards and analytics" at scale.

**Acceptance Criteria:**
- [ ] Rate limiting: 60 requests/minute per IP using `slowapi` or equivalent middleware
- [ ] HTTP 429 returned with `Retry-After` header when rate limit exceeded
- [ ] Cursor-based pagination: `?cursor=<opaque_token>` and `?limit=N` (max 100)
      alongside existing page-based pagination
- [ ] Additional filter: `?provider=<fuzzy_string>` (case-insensitive substring match)
- [ ] Additional filter: `?min_confidence=<float>` filters events below threshold
- [ ] Additional filter: `?location=<lat,lon>&radius_km=<int>` for proximity search
- [ ] All new filters covered by integration tests
- [ ] Rate limit headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`) included in responses

**Status:** `pending`

---

### PO-014: OpenAPI Documentation, Swagger UI & Developer Guide

**Priority:** Should Have  
**Description:** Produce complete, accurate API documentation that makes openOrbit
usable for external developers building dashboards and analytics tools. FastAPI
auto-generates the OpenAPI spec; this item enriches it with examples, descriptions,
and a written developer guide in `docs/api.md`.

**Acceptance Criteria:**
- [ ] Every endpoint, query parameter, and response field has a docstring or `Field(description=…)`
- [ ] `GET /docs` (Swagger UI) and `GET /redoc` are reachable and fully populated
- [ ] `GET /openapi.json` returns a valid OpenAPI 3.1 spec
- [ ] `docs/api.md` written with: overview, authentication (none for now), endpoint reference,
      example `curl` requests and responses for each endpoint
- [ ] `docs/api.md` includes a "Confidence Score" explainer section
- [ ] `docs/api.md` includes a "Launch Type Classification" explainer section
- [ ] Example response payloads in Swagger match actual API output (tested with snapshot test)

**Status:** `pending`

---

### PO-015: Modular Source Plugin Interface

**Priority:** Should Have  
**Description:** Refactor the scraper layer into a formal plugin interface so that
new OSINT sources can be added by implementing a single abstract class and registering
in `osint_sources` without touching core pipeline code. This fulfils the architectural
constraint: *"Must be modular to allow adding new data sources over time."*

**Acceptance Criteria:**
- [ ] `src/openorbit/scrapers/base.py` defines `BaseScraper` abstract class with methods:
      `async def fetch() -> list[RawRecord]` and `async def run() -> ScrapeResult`
- [ ] All three existing scrapers (PO-003, PO-006, PO-007) refactored to extend `BaseScraper`
- [ ] `ScraperRegistry` in `scrapers/registry.py` auto-discovers scrapers via entry points
      or explicit registration; no core code changes needed to add a new source
- [ ] `docs/adding-sources.md` written: step-by-step guide to adding a new OSINT scraper
      (implement `BaseScraper`, add to `osint_sources`, register)
- [ ] Adding a new mock scraper in tests requires only implementing `BaseScraper` — verified
      by a test that registers a `MockScraper` and runs the full pipeline
- [ ] Existing tests still pass after refactor (no regressions)

**Status:** `pending`

---

### PO-016: Admin & Source Health Monitoring Endpoints

**Priority:** Should Have  
**Description:** Provide a lightweight admin surface (protected by a static API key)
for operators to inspect source health, trigger manual scrape runs, and view system
statistics without database access. This makes the running service observable and
operable without SSH access.

**Acceptance Criteria:**
- [ ] `GET /v1/admin/sources` lists all sources with last-run status, event counts,
      error rates (protected by `X-Admin-Key` header; key set via env var)
- [ ] `POST /v1/admin/sources/{id}/refresh` triggers an immediate scrape of a single source
- [ ] `GET /v1/admin/stats` returns: total events, events per source, events per launch type,
      average confidence score, last full refresh timestamp
- [ ] HTTP 401 returned when `X-Admin-Key` is missing or incorrect
- [ ] Admin endpoints excluded from public `/docs` (use `include_in_schema=False`) or
      guarded by a separate OpenAPI tag labelled "Admin (key required)"
- [ ] Integration tests cover: authenticated access, unauthenticated rejection, manual refresh

**Status:** `pending`

---

## Could Have

> Valuable enhancements if sprint capacity allows; deferred without product risk.

---

### PO-017: Fourth+ OSINT Source — News & Open-Source Intel Aggregators

**Priority:** Could Have  
**Description:** Add a fourth scraper targeting publicly available news and OSINT
aggregator sources such as SpaceFlightNow.com, NASASpaceflight.com, or public RSS
feeds from space news outlets. This increases source diversity and improves confidence
scoring for civilian launches. Feeds through the same `BaseScraper` plugin interface.

**Acceptance Criteria:**
- [ ] `src/openorbit/scrapers/news.py` implements `NewsAggregatorScraper`
- [ ] Scraper targets ≥2 public RSS feeds or news pages
- [ ] Parsed articles matched to existing events via entity linking (provider + date fuzzy match)
- [ ] New source registered in `osint_sources`; scheduler picks it up automatically
- [ ] Unit tests with mocked RSS/HTML responses
- [ ] Total OSINT sources in system reaches ≥4

**Status:** `pending`

---

### PO-018: Launch Event History & Status Change Tracking

**Priority:** Could Have  
**Description:** Track how launch events change over time (date slips, status changes,
vehicle swaps). Each significant change is recorded in an `event_history` table, and
the API exposes a `GET /v1/launches/{id}/history` endpoint showing the change log.
This is valuable for analytics dashboards tracking launch reliability and scheduling trends.

**Acceptance Criteria:**
- [ ] `event_history` table: `(id, launch_event_id, field_changed, old_value, new_value, changed_at, source_id)`
- [ ] `upsert_launch_event()` writes history records whenever `launch_date`, `status`,
      `vehicle`, or `confidence_score` changes by more than a configurable threshold
- [ ] `GET /v1/launches/{id}/history` returns chronological list of changes
- [ ] History records are append-only (never deleted)
- [ ] Unit tests assert history written on status change but not on no-op upsert

**Status:** `pending`

---

### PO-019: Webhook / Server-Sent Events for Launch Updates

**Priority:** Could Have  
**Description:** Allow API consumers to subscribe to real-time (near-real-time) launch
event updates via Server-Sent Events (SSE) or configurable webhooks. When the scheduler
detects a new or changed event, subscribers are notified. This enables dashboard
consumers to avoid polling.

**Acceptance Criteria:**
- [ ] `GET /v1/launches/stream` returns an SSE stream; new/updated events emitted as
      `data: <JSON>\n\n` when detected by the refresh cycle
- [ ] `POST /v1/webhooks` registers a webhook URL; `DELETE /v1/webhooks/{id}` removes it
- [ ] Webhook delivers `POST` to registered URL with launch event JSON payload on change
- [ ] Webhook retries up to 3 times on delivery failure with exponential backoff
- [ ] SSE and webhook features behind a feature flag (`ENABLE_STREAMING=true`)
- [ ] Integration test: mock webhook receiver asserts payload delivery

**Status:** `pending`

---

## Won't Have (this release)

> Explicitly out of scope. Documenting these prevents scope creep.

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
**Description:** A web-based user interface, map visualization, or analytics dashboard.
The project is API-first. Consumers build their own frontends against the REST API.

**Status:** `pending`

---

### PO-022: Weapon Targeting or Actionable Defense Applications

**Priority:** Won't Have  
**Description:** Any feature that supports weapon targeting, real-time defense decision
support, or actionable military intelligence. Explicitly prohibited by project constraints.

**Status:** `pending`

