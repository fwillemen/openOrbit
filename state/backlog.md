# openOrbit — Product Backlog

> **Product:** openOrbit — Global Launch Event Tracking & OSINT Intelligence API
> **Owner:** Product Owner Agent
> **Source:** `state/goal.md` — OSINT-powered launch tracking API with rigorous intelligence methodology
> **Last updated:** 2026-04-06 (Sprint 4 ✅ complete — all 21 Must Have done; PO-038/039/040 added for Sprint 5)

---

## Summary

| Priority      | Count | Done |
|---------------|-------|------|
| Must Have     | 21    | 21   |
| Should Have   | 13    | 0    |
| Could Have    | 2     | 0    |
| Won't Have    | 4     | —    |
| **Total**     | **40**| **21**|

---

## Reassessment Notes

This backlog was comprehensively refreshed at Sprint 3 completion. The following
changes were made:

### Sprint 3 Completions

Four items originally pending are now **done**:
- **PO-014** (OpenAPI Documentation & Developer Guide) — `docs/api-reference.md`,
  `docs/quickstart.md`, and full endpoint annotation delivered
- **PO-015** (BaseScraper ABC + ScraperRegistry singleton) — modular plugin contract
  delivered; all scrapers conform to `BaseScraper`; scheduler reads from registry
- **PO-023** (Test Coverage Hardening) — 374 tests at 93% overall coverage; all
  critical zero-coverage paths resolved
- **PO-024** (API Key Authentication via PBKDF2-SHA256, `X-API-Key` header) —
  protected route dependency delivered; `secrets.compare_digest()` in use

### OSINT Intelligence Methodology — First-Class Architectural Constraint

The user has formally defined a rigorous intelligence methodology that now governs
the schema, scrapers, and confidence engine. This is not an enhancement — it is a
**foundational architectural constraint** that all remaining work must conform to.

**Three source tiers** replace the previous flat source model:
- **Tier 1** (Official/Regulatory): space agencies, operators, regulators — ground-truth
- **Tier 2** (Operational/Catalog): NOTAMs, maritime warnings, TLE anomalies,
  range scheduling — pre-event signals and post-event corroboration
- **Tier 3** (Analytical/Speculative): newsletters, expert observers, tracking
  communities, procurement signals — high-signal when curated; confidence-scored

**Claim lifecycle** replaces the binary verified/unverified model:
```
Rumor → Indicated → Corroborated → Confirmed → Retracted
```
Each transition requires multi-source, multi-tier corroboration. Every launch event
tracks whether it is an **observed** event (directly documented by Tier 1/2) or an
**inferred** event (assembled from multiple signals).

**Provenance schema** — every attribution must carry: `source_url`, `observed_at`,
`evidence_type` (enum: `official_schedule`, `notam`, `maritime_warning`,
`range_signal`, `tle_anomaly`, `contract_award`, `expert_analysis`, `media`,
`imagery`), `source_tier`, `confidence_score`, `confidence_rationale`.

### Carry-Forward Updates
- **PO-016** (admin endpoints): `depends on PO-024` — now unblocked, promote to sprint
- **PO-017** (news RSS scraper): `depends on PO-015` — now unblocked; reclassified as
  Tier 3 scraper; `evidence_type = 'media'`
- **PO-025** (PostgreSQL migration path): carry-forward unchanged
- **PO-026** (CI/CD pipeline): carry-forward unchanged

### New Items Added (PO-027 through PO-037)
- **PO-027** (Must Have): Fix critical `notams.py` SyntaxError on line 1
- **PO-028** (Must Have): Source tier & claim lifecycle schema migration
- **PO-029** (Must Have): Provenance API — per-event evidence chain endpoint
- **PO-030** (Should Have): TLE/catalog anomaly detector (Tier 2 signal)
- **PO-031** (Should Have): AIS maritime warning & range scheduling scraper (Tier 2)
- **PO-032** (Should Have): Multi-source corroboration engine
- **PO-033** (Should Have): Industrial & procurement signal scraper (Tier 3)
- **PO-034** (Should Have): Launch event full-text search (FTS5)
- **PO-035** (Should Have): Launch statistics & trend analytics endpoints
- **PO-036** (Should Have): Data export API with provenance
- **PO-037** (Should Have): Prometheus `/metrics` observability endpoint

---

## Must Have

> Core functionality without which the product fails to meet its success criteria.
> PO-001 through PO-013, PO-014, PO-015, PO-023, PO-024, and PO-027 are **done** (18 items).
> PO-016, PO-028, and PO-029 are the remaining pending Must Have items.

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

### PO-003: OSINT Scraper — Space Agency Launch Schedules (Tier 1, Source 1)

**Priority:** Must Have
**Description:** First production OSINT scraper. Targets NASA's public schedule /
Launch Library 2 public API. Extracts, normalises, and persists events. Idempotent
upsert. Respects `SCRAPER_DELAY_SECONDS`. Stores raw responses. Tier 1 — ground-truth
anchor source.

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

### PO-006: OSINT Scraper — Commercial Launch Providers (Tier 1, Source 2)

**Priority:** Must Have
**Description:** Second OSINT scraper. SpaceX press kit (SpaceX API v4) + Rocket Lab.
Feeds the same normalization pipeline. Idempotent, rate-limited, attribution-tagged.
Tier 1 — official operator sources.

**Acceptance Criteria:**
- [x] `scrapers/commercial.py` implements `CommercialLaunchScraper`
- [x] Covers ≥2 commercial providers; respects rate limiting
- [x] Unit tests with mocked HTTP; ≥1 sample payload per provider

**Status:** `done`

---

### PO-007: OSINT Scraper — Public NOTAMs & Maritime Advisories (Tier 2, Source 3)

**Priority:** Must Have
**Description:** Third OSINT scraper. FAA NOTAM public endpoint. Keyword extraction
(`ROCKET`, `MISSILE`, `SPACE LAUNCH`, `RANGE CLOSURE`). Launch type inference from
keywords. Stored in `raw_scrape_records`. Tier 2 — operational airspace signals that
provide pre-event corroboration.

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
**Description:** Per-event `confidence_score` computed from number and quality of
sources. `launch_type` classification (orbital/suborbital/civil/military). Attribution
chain stored in `event_attributions`. `result_tier` (verified/tracked/emerging) derived
from confidence thresholds.

**Acceptance Criteria:**
- [x] `confidence_score` in [0.0, 1.0] stored per event and per attribution
- [x] `launch_type` classified for every event with a documented ruleset
- [x] `result_tier` assigned based on confidence thresholds
- [x] `event_attributions` table populated for every scrape
- [x] Unit tests cover confidence edge cases and classification rules

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

**Acceptance Criteria:**
- [x] Every endpoint has a `summary`, `description`, and tagged OpenAPI group
- [x] Every query parameter has `description=` and a typed `example=` value in `Field()`
- [x] Every response model field has `description=` in its Pydantic field definition
- [x] `GET /docs` (Swagger UI) and `GET /redoc` are reachable and fully populated
- [x] `GET /openapi.json` returns a valid OpenAPI 3.1 spec
- [x] `docs/api-reference.md` written with endpoint reference and example `curl` commands
- [x] `docs/quickstart.md` includes confidence score explainer and launch type guide
- [x] Snapshot test asserts `/openapi.json` schema does not regress between runs

**Status:** `done`

---

### PO-015: Modular Source Plugin Interface & ScraperRegistry

**Priority:** Must Have
**Description:** The goal states the system "Must be modular to allow adding new data
sources over time." `scrapers/base.py` defines `BaseScraper` ABC. `ScraperRegistry`
singleton enables auto-discovery without editing scheduler code. All existing scrapers
conform and register declaratively.

**Acceptance Criteria:**
- [x] `scrapers/base.py` `BaseScraper` abstract class fully tested (100% coverage)
- [x] `ScraperRegistry` in `scrapers/registry.py` allows registering and discovering
      scrapers without modifying scheduler or pipeline code
- [x] All existing scrapers verified to conform to `BaseScraper` interface via a
      registry round-trip integration test
- [x] Adding a `MockScraper` (implementing `BaseScraper`) in tests auto-registers
      and executes through the full pipeline without any core code changes
- [x] `docs/adding-sources.md` written: step-by-step guide (implement → register → verify)
- [x] Scheduler reads active scrapers from the registry, not a hardcoded list
- [x] Existing scraper tests still pass after refactor (zero regressions)

**Status:** `done`

---

### PO-023: Test Coverage Hardening — Critical Untested Paths

**Priority:** Must Have
**Description:** Coverage analysis revealed zero-or-near-zero coverage on critical
paths: `scrapers/notams.py` (0%), `scrapers/base.py` (0%), `main.py` ASGI lifecycle
(44%), `api/v1/sources.py` (53%), `api/v1/launches.py` (77%). All resolved to bring
overall coverage to 93% across 374 tests.

**Acceptance Criteria:**
- [x] `scrapers/notams.py` reaches ≥85% coverage via `respx`-mocked HTTP tests
      (happy path, keyword match for ROCKET/MISSILE/SPACE LAUNCH, HTTP error, timeout)
- [x] `scrapers/base.py` reaches 100% coverage (abstract method enforcement, `ScrapeResult` fields)
- [x] `main.py` ASGI lifecycle reaches ≥85% coverage (startup success, DB init failure,
      shutdown order, logging modes)
- [x] `api/v1/sources.py` reaches ≥85% coverage (empty list, zero attributions, DB error → 500)
- [x] `api/v1/launches.py` reaches ≥90% coverage (cursor decode error, DB error, boundary
      values for `min_confidence`, invalid lat/lon for `location`)
- [x] Overall project test coverage ≥85% (achieved: 93% at 374 tests)
- [x] All tests use `pytest-asyncio` + `respx` for HTTP mocking; no real network calls

**Status:** `done`

---

### PO-024: API Key Authentication for Protected Endpoints

**Priority:** Must Have
**Description:** Header-based API key authentication for protected routes using
PBKDF2-SHA256 key derivation. `X-API-Key` header required on admin routes.
`secrets.compare_digest()` prevents timing attacks. Public read endpoints remain open.

**Acceptance Criteria:**
- [x] `config.py` gains `ADMIN_API_KEY` setting; app refuses to start if unset and
      `REQUIRE_ADMIN_KEY=true`
- [x] `middleware/auth.py` implements `require_api_key` FastAPI dependency: reads
      `X-API-Key` header; raises HTTP 401 with `{"error": "unauthorized"}` if missing
      or incorrect
- [x] Admin routes wired to `require_api_key` dependency
- [x] Public endpoints (`GET /v1/launches`, `/v1/launches/{id}`, `/v1/sources`,
      `/health`) remain open — no key required
- [x] Key comparison uses PBKDF2-SHA256 + `secrets.compare_digest()` (no timing leaks)
- [x] Integration tests: missing key → 401, wrong key → 401, correct key → 200,
      public endpoint without key → 200

**Status:** `done`

---

### PO-027: Fix `notams.py` Critical SyntaxError (Line 1)

**Priority:** Must Have
**Description:** `src/openorbit/scrapers/notams.py` line 1 reads
`Update """FAA NOTAM scraper...` — the word `Update` was prepended to the module
docstring, causing a `SyntaxError` that crashes Python import of the entire scrapers
package at startup and kills all NOTAM-related tests. This is a production-breaking
defect that must be resolved before any further work on the scraper layer proceeds.

**Acceptance Criteria:**
- [x] Line 1 of `src/openorbit/scrapers/notams.py` is corrected to a valid Python
      module docstring: `"""FAA NOTAM scraper...` (the stray `Update` prefix is removed)
- [x] `python -c "from openorbit.scrapers.notams import NotamScraper"` exits with code 0
- [x] `uv run pytest tests/` completes with 0 collection errors and 0 import errors
- [x] All previously-passing NOTAM tests continue to pass after the fix
- [x] No other files modified — this is a single-line surgical fix
- [x] CI gate (or local `ruff check`) passes on the corrected file

**Status:** `done`

---

### PO-028: Source Tier System & Claim Lifecycle Schema Migration

**Priority:** Must Have
**Description:** The OSINT intelligence methodology requires the database schema to
model source tiers, claim lifecycle states, and per-attribution provenance. This item
extends three tables with new columns and writes an idempotent migration so existing
data is preserved. All existing scrapers are updated to populate the new fields. API
response models are updated to expose them. The existing `result_tier`
(verified/tracked/emerging) is retained and computed from `claim_lifecycle` + confidence.

**Depends on:** PO-027 (notams.py must be importable before scraper updates run)

**Acceptance Criteria:**
- [ ] Idempotent migration adds `source_tier INTEGER CHECK(source_tier IN (1,2,3))` to
      `osint_sources` table; existing rows default to appropriate tier value
- [ ] Idempotent migration adds to `event_attributions`:
      - `evidence_type TEXT CHECK(evidence_type IN ('official_schedule','notam',
        'maritime_warning','range_signal','tle_anomaly','contract_award',
        'expert_analysis','media','imagery'))` (nullable for legacy rows)
      - `source_tier INTEGER` (nullable for legacy rows)
      - `confidence_rationale TEXT` (nullable)
- [ ] Idempotent migration adds to `launch_events`:
      - `claim_lifecycle TEXT CHECK(claim_lifecycle IN ('rumor','indicated',
        'corroborated','confirmed','retracted'))` with default `'indicated'`
      - `event_kind TEXT CHECK(event_kind IN ('observed','inferred'))` with
        default `'inferred'`
- [ ] Migration script is runnable with `uv run python -m openorbit.db migrate`
      and is a no-op if columns already exist (idempotent)
- [ ] `state/schema.sql` updated to reflect the complete post-migration schema
- [ ] All existing scrapers updated to set `source_tier` and `evidence_type` when
      calling `add_attribution()`:
      - `space_agency.py` → `source_tier=1`, `evidence_type='official_schedule'`
      - `spacex_official.py` → `source_tier=1`, `evidence_type='official_schedule'`
      - `celestrak.py` → `source_tier=2`, `evidence_type='tle_anomaly'`
      - `commercial.py` → `source_tier=1`, `evidence_type='official_schedule'`
      - `notams.py` → `source_tier=2`, `evidence_type='notam'`
      - Regional adapters (ESA, JAXA, ISRO, Arianespace, CNSA) → `source_tier=1`,
        `evidence_type='official_schedule'`
- [ ] Pydantic response models (`LaunchEventResponse`, `AttributionResponse`) updated
      to expose `claim_lifecycle`, `event_kind`, `source_tier`, `evidence_type`,
      `confidence_rationale` — all nullable for backward compatibility
- [ ] `GET /v1/launches` and `GET /v1/launches/{id}` responses include the new fields
- [ ] `GET /v1/launches?claim_lifecycle=confirmed` filter added and documented
- [ ] All existing tests pass after migration; ≥5 new tests cover migration idempotency
      and the updated scraper field population

**Status:** `pending`

---

### PO-029: Provenance API — Per-Event Evidence Chain Endpoint

**Priority:** Must Have
**Description:** Makes confidence scores explainable and auditable. A new endpoint
returns the complete provenance chain for any launch event: every attribution with its
tier, evidence type, URL, timestamp, score, and rationale. The top-level summary
exposes the claim lifecycle state, event kind, and which tiers have contributed
evidence. This is the primary transparency mechanism for the OSINT methodology.

**Depends on:** PO-028 (provenance schema must exist)

**Acceptance Criteria:**
- [ ] `GET /v1/launches/{id}/evidence` endpoint implemented in
      `src/openorbit/api/v1/evidence.py`
- [ ] Returns HTTP 404 if launch event `{id}` does not exist
- [ ] Response body conforms to:
      ```json
      {
        "launch_id": "...",
        "claim_lifecycle": "corroborated",
        "event_kind": "observed",
        "evidence_count": 3,
        "tier_coverage": [1, 2],
        "attributions": [
          {
            "source_name": "...",
            "source_tier": 1,
            "evidence_type": "official_schedule",
            "source_url": "https://...",
            "observed_at": "2026-03-20T14:00:00Z",
            "confidence_score": 0.85,
            "confidence_rationale": "Tier 1 official schedule; confirmed launch window"
          }
        ]
      }
      ```
- [ ] `tier_coverage` lists the distinct `source_tier` values present in the attribution list
- [ ] Attributions ordered by `observed_at` descending (most recent first)
- [ ] Endpoint tagged `"Evidence"` in OpenAPI; fully documented with request/response examples
- [ ] `docs/api-reference.md` updated with the new endpoint and a "Reading Provenance" guide
- [ ] Integration tests: event with attributions returns full chain; event with no
      attributions returns `evidence_count: 0` and empty `attributions: []`; missing
      event returns 404
- [ ] `GET /v1/launches/{id}` response gains a top-level `evidence_url` field pointing
      to the evidence endpoint for convenience

**Status:** `pending`

---

### PO-016: Admin & Source Health Monitoring Endpoints

**Priority:** Must Have
**Description:** Lightweight admin surface (protected by `X-API-Key` from PO-024) for
operators to inspect source health, trigger manual scrape runs, and view system
statistics — without needing SSH or database access.

**Depends on:** PO-024 ✅ (done)

**Acceptance Criteria:**
- [ ] `GET /v1/admin/sources` lists all sources with last-run status, event counts,
      and error rates; requires valid `X-API-Key` header
- [ ] `POST /v1/admin/sources/{id}/refresh` triggers immediate scrape of a single source;
      returns `{"status": "triggered", "source_id": "..."}` with HTTP 202
- [ ] `GET /v1/admin/stats` returns: total events, events per source, per launch type,
      events per claim_lifecycle state, average confidence score, last full refresh timestamp
- [ ] HTTP 401 when `X-API-Key` missing or wrong; HTTP 404 when source ID not found
- [ ] Admin routes tagged separately in OpenAPI ("Admin — key required")
- [ ] Integration tests: authenticated access succeeds; unauthenticated access returns 401;
      manual refresh returns 202; refresh of non-existent source returns 404

**Status:** `pending`

---

## Should Have

> Important for a production-quality service and the OSINT methodology implementation.
> Deferred from Must Have but should land before the product is widely promoted.
> All items below are pending.

---

### PO-017: Tier 3 News RSS Scraper — Media & OSINT Aggregators

**Priority:** Should Have
**Description:** Completes the original source plan from `goal.md` ("News and OSINT
aggregators"). Classified as a Tier 3 source — high-signal when curated, but
confidence-scored and treated as speculative until corroborated by Tier 1/2 evidence.
Exercises the `ScraperRegistry` plugin interface (PO-015) as a real-world validation.
Parsed article matches feed into the claim lifecycle as Tier 3 signals that can elevate
a `Rumor` to `Indicated` when ≥2 agree.

**Depends on:** PO-015 ✅ (done), PO-028 (claim lifecycle schema)

**Acceptance Criteria:**
- [ ] `src/openorbit/scrapers/news.py` implements `NewsRSSScraper` extending `BaseScraper`
- [ ] Scraper targets ≥2 public RSS feeds (e.g. SpaceFlightNow.com, NASASpaceflight.com)
- [ ] Each attribution persisted with `source_tier=3` and `evidence_type='media'`
- [ ] Parsed articles matched to existing events via fuzzy provider + date entity linking;
      unmatched articles create new events with `claim_lifecycle='rumor'`
- [ ] New source auto-registered via `ScraperRegistry`; scheduler picks it up without
      any changes to scheduler or pipeline code
- [ ] Unit tests with mocked RSS responses; ≥2 sample payloads per feed
- [ ] `osint_sources` table gains a row for each RSS feed; `GET /v1/sources` reflects
      new sources with `source_tier=3` and `last_scraped_at`
- [ ] Scraper respects `SCRAPER_DELAY_SECONDS`; no real HTTP calls in tests

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
- [ ] `schema.sql` reviewed and updated so all SQL is ANSI-compatible; SQLite-specific
      syntax (e.g. `AUTOINCREMENT`) replaced with portable equivalents
- [ ] `db.py` uses an abstraction layer (e.g. `databases` library or thin adapter) that
      passes identical queries to both backends without duplication
- [ ] `docker-compose.yml` gains an optional `postgres` service profile; switching from
      SQLite to PostgreSQL requires only changing `DATABASE_URL`
- [ ] `docs/deployment.md` updated with PostgreSQL setup instructions
- [ ] Integration test suite runs against both SQLite (default) and PostgreSQL (via
      `pytest --db-backend=postgres` marker); all tests pass on both backends

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
- [ ] `.github/workflows/ci.yml` runs on every PR and push to `main`
- [ ] CI pipeline steps in order: `uv sync` → `ruff check` (lint) → `ruff format --check`
      → `mypy` (type check) → `pytest --cov=openorbit --cov-fail-under=85`
- [ ] Pipeline fails and blocks merge if any step fails or coverage drops below 85%
- [ ] Workflow caches `uv` dependencies for fast runs (< 3 min total target)
- [ ] `README.md` updated with a CI status badge pointing to the workflow
- [ ] `pyproject.toml` defines `[tool.ruff]`, `[tool.mypy]`, and `[tool.pytest]`
      sections; CI uses these directly (no duplicated config in workflow file)
- [ ] Docker build step (`docker build .`) included in CI to catch `Dockerfile` regressions

**Status:** `pending`

---

### PO-030: Orbital/Catalog Anomaly Detector — Tier 2 TLE Signal

**Priority:** Should Have
**Description:** The CelesTrak GP feed (already scraped) is a Tier 2 source. This item
adds active monitoring logic: detect new object designations and unexpected TLE updates
that appear near known launch windows, and flag them as `evidence_type='tle_anomaly'`
Tier 2 corroboration signals. Feeds the claim lifecycle promotion logic — a TLE anomaly
coinciding with an `indicated` event is sufficient to promote it to `corroborated`.

**Depends on:** PO-028 (claim lifecycle schema + evidence_type field)

**Acceptance Criteria:**
- [ ] `pipeline/tle_monitor.py` implements `TLEAnomalyDetector` that:
      - Reads the latest CelesTrak GP batch from `raw_scrape_records`
      - Compares object counts and epoch timestamps against the previous batch
      - Flags new designations or epoch deltas > configurable threshold as anomalies
- [ ] Each detected anomaly creates an `event_attributions` record with
      `source_tier=2`, `evidence_type='tle_anomaly'`, and a descriptive
      `confidence_rationale` (e.g. "New object YYYY-NNNX appeared 6h after
      indicated launch window")
- [ ] When a TLE anomaly is associated with an event whose `claim_lifecycle='indicated'`,
      the lifecycle is automatically promoted to `'corroborated'` by the corroboration
      engine (or a stub until PO-032 is delivered)
- [ ] `GET /v1/launches?evidence_type=tle_anomaly` filter returns events corroborated
      by TLE anomalies
- [ ] Unit tests: new object detection, epoch delta detection, no-anomaly baseline,
      lifecycle promotion from indicated → corroborated
- [ ] `celestrak.py` scraper updated to tag its attributions with `source_tier=2`
      and `evidence_type='tle_anomaly'` (may duplicate PO-028 work — coordinate)

**Status:** `pending`

---

### PO-031: AIS Maritime Warning & Range Scheduling Scraper — Tier 2

**Priority:** Should Have
**Description:** Extends operational signals beyond FAA NOTAMs. Scrape public
NAVAREA/HYDROLANT maritime warning bulletins from official sources (NGA Maritime
Safety Information public portal). Maritime hazard notices near known launch ranges
are strong Tier 2 pre-event corroboration signals. Register via ScraperRegistry.

**Depends on:** PO-015 ✅ (done), PO-028 (evidence_type schema)

**Acceptance Criteria:**
- [ ] `src/openorbit/scrapers/maritime.py` implements `MaritimeWarningScraper`
      extending `BaseScraper`
- [ ] Scraper fetches NAVAREA/HYDROLANT bulletins from ≥1 public official source
      (e.g. NGA MSI public portal or equivalent GMDSS public feed)
- [ ] Keyword filter identifies launch-range-relevant warnings (area overlap with
      known launch range coordinates: Cape Canaveral, Vandenberg, Baikonur, Jiuquan,
      Sriharikota, Kourou)
- [ ] Each matched warning stored as `evidence_type='maritime_warning'`, `source_tier=2`
- [ ] Matched warnings linked to existing events within ±5-day temporal window and
      configurable range proximity (default 200 km)
- [ ] Auto-registered via `ScraperRegistry`; no scheduler code changes required
- [ ] Unit tests with mocked HTTP responses; ≥3 sample bulletin payloads covering
      match and non-match cases
- [ ] `GET /v1/launches?evidence_type=maritime_warning` filter returns relevant events

**Status:** `pending`

---

### PO-032: Multi-Source Corroboration Engine

**Priority:** Should Have
**Description:** Formalises the claim lifecycle transition rules into a configurable,
testable rule engine. Replaces ad-hoc confidence arithmetic with principled
tier-weighted scoring. The engine re-evaluates `claim_lifecycle` whenever a new
attribution is added, applying configurable thresholds per transition. The result is
a fully auditable, deterministic path from raw signals to lifecycle state.

**Depends on:** PO-028 (lifecycle schema), PO-029 (provenance chain as input)

**Acceptance Criteria:**
- [ ] `pipeline/corroboration.py` implements `CorroborationEngine` with explicit rules:
      - `Rumor → Indicated`: 1× Tier 2 signal **OR** ≥2 independent Tier 3 signals
      - `Indicated → Corroborated`: signals from ≥2 different source tiers agree on
        provider + date window
      - `Corroborated → Confirmed`: ≥1 Tier 1 source directly documents the event
      - Any state `→ Retracted`: Tier 1 source explicitly negates the event
- [ ] Transition thresholds (min tier diversity, min attribution count) are configurable
      via `config.py` environment variables with documented defaults
- [ ] Engine is called automatically after every `add_attribution()` call; `claim_lifecycle`
      updated in-place atomically
- [ ] `confidence_score` recalculated using tier-weighted formula:
      `score = Σ(tier_weight[t] × source_confidence) / normalizer` where
      `tier_weight = {1: 1.0, 2: 0.7, 3: 0.4}`
- [ ] Rule engine is fully unit-tested with parametrized pytest cases covering:
      every valid transition, every invalid transition (no promotion without threshold),
      retraction from each state, idempotent re-evaluation
- [ ] `GET /v1/launches/{id}` response includes `corroboration_summary` object:
      `{"tier_diversity": 2, "attribution_count": 4, "lifecycle_transitions": [...]}`
- [ ] Existing `result_tier` (verified/tracked/emerging) is computed from
      `claim_lifecycle` per documented mapping:
      `confirmed → verified`, `corroborated → tracked`, `indicated/rumor → emerging`

**Status:** `pending`

---

### PO-033: Industrial & Procurement Signal Scraper — Tier 3

**Priority:** Should Have
**Description:** Public contract award databases and satellite filing/ITU coordination
notices are early indicators of planned launches — sometimes weeks or months ahead of
official announcements. This scraper targets SAM.gov open data (public federal contract
awards), ESA procurement portal public notices, and ITU filing summaries. Classified
as Tier 3 — speculative until corroborated. Register via ScraperRegistry.

**Depends on:** PO-015 ✅ (done), PO-028 (evidence_type schema)

**Acceptance Criteria:**
- [ ] `src/openorbit/scrapers/procurement.py` implements `ProcurementSignalScraper`
      extending `BaseScraper`
- [ ] Scraper targets ≥2 of: SAM.gov open data API (public, no auth required),
      ESA EMITS public notice feed, ITU Space Network Systems public filing database
- [ ] Keyword filter identifies launch-relevant awards (e.g. "launch services",
      "payload integration", "range safety", "trajectory analysis")
- [ ] Each matched record stored with `source_tier=3`, `evidence_type='contract_award'`,
      and a `confidence_rationale` explaining the keyword match
- [ ] Unmatched awards discarded; no false-positive flood to event table
- [ ] Auto-registered via `ScraperRegistry`; no scheduler code changes required
- [ ] `osint_sources` table gains a row per data source (SAM.gov, ESA, ITU)
- [ ] Unit tests with mocked API/HTML responses; ≥2 sample payloads (match + non-match)
- [ ] `GET /v1/launches?evidence_type=contract_award` returns relevant events

**Status:** `pending`

---

### PO-034: Launch Event Full-Text Search

**Priority:** Should Have
**Description:** Dashboard and analytics consumers need to search across event names,
providers, locations, notes, and confidence rationale text — not just filter by
structured fields. Implement SQLite FTS5 virtual table for ranked full-text search.
Return results ordered by FTS5 relevance rank. Document in API reference.

**Depends on:** PO-028 (confidence_rationale field must exist to be searchable)

**Acceptance Criteria:**
- [ ] SQLite FTS5 virtual table `launch_events_fts` created over columns:
      `event_name`, `provider`, `location`, `notes`, `confidence_rationale`
- [ ] FTS5 table kept in sync with `launch_events` via triggers (insert, update, delete)
- [ ] `GET /v1/launches?q=falcon+heavy` keyword search implemented; results ordered
      by FTS5 BM25 rank score (most relevant first)
- [ ] `?q=` is combinable with all existing filters (`?provider`, `?min_confidence`,
      `?claim_lifecycle`, date range, etc.)
- [ ] Empty `?q=` or absent `?q=` parameter falls back to standard listing (no regression)
- [ ] `GET /v1/launches` response includes `search_rank` field (null when no query)
- [ ] `docs/api-reference.md` updated with full-text search documentation and examples
- [ ] Integration tests: single-term match, multi-term match, no results, combined
      with filters, special characters are safely escaped

**Status:** `pending`

---

### PO-035: Launch Statistics & Trend Analytics Endpoints

**Priority:** Should Have
**Description:** Dashboard-consumer-oriented endpoints that expose aggregated
statistics and time-series trend data without requiring consumers to make dozens of
individual event queries. Both endpoints are cached with a short TTL to ensure fast
response times under repeated dashboard polling.

**Acceptance Criteria:**
- [ ] `GET /v1/stats` returns JSON object:
      - `total_events` (int)
      - `events_by_launch_type` (object: launch_type → count)
      - `events_by_result_tier` (object: verified/tracked/emerging → count)
      - `events_by_claim_lifecycle` (object: rumor/indicated/corroborated/confirmed/retracted → count)
      - `events_by_source_tier` (object: 1/2/3 → count)
      - `sources` (list of: source_name, source_tier, last_scraped_at, event_count)
      - `last_full_refresh_at` (ISO 8601 timestamp of most recent scraper run)
- [ ] `GET /v1/analytics/trends?period=7d&group_by=claim_lifecycle` returns:
      - Time-series data: array of `{date, counts_by_group}` over the requested period
      - Supported `period` values: `1d`, `7d`, `30d`, `90d`
      - Supported `group_by` values: `claim_lifecycle`, `launch_type`, `source_tier`
      - HTTP 422 for unsupported period or group_by values
- [ ] Both endpoints cached in-memory with a 60-second TTL (configurable via
      `STATS_CACHE_TTL_SECONDS` env var)
- [ ] Both endpoints are unauthenticated (public read)
- [ ] Tagged `"Analytics"` in OpenAPI with full parameter and response documentation
- [ ] Integration tests: populated DB returns correct counts; empty DB returns zeros;
      cache is hit on second identical request within TTL; trends span correct date range

**Status:** `pending`

---

### PO-036: Data Export API with Provenance

**Priority:** Should Have
**Description:** Analytics and GIS tool consumers need raw data exports that include
provenance columns — not just the event itself. This endpoint streams the full launch
event dataset in CSV or GeoJSON format including `source_tier`, `evidence_type`,
`claim_lifecycle`, and `evidence_count`. Uses streaming response to handle large
datasets without memory pressure.

**Acceptance Criteria:**
- [ ] `GET /v1/launches/export?format=csv` returns a streaming `text/csv` response
- [ ] `GET /v1/launches/export?format=geojson` returns a streaming `application/geo+json`
      response (GeoJSON FeatureCollection; events without coordinates included with
      `geometry: null`)
- [ ] CSV columns include: `id`, `event_name`, `provider`, `launch_date`, `location`,
      `latitude`, `longitude`, `launch_type`, `result_tier`, `claim_lifecycle`,
      `event_kind`, `confidence_score`, `evidence_count`, `tier_coverage`, `inference_flags`
- [ ] GeoJSON properties match CSV columns; geometry is `Point [lon, lat]`
- [ ] Export respects all standard `GET /v1/launches` filters (`?provider`,
      `?min_confidence`, `?claim_lifecycle`, date range, `?q=`) — filtered export
- [ ] Response uses FastAPI `StreamingResponse` to avoid loading full dataset into memory
- [ ] `Content-Disposition: attachment; filename="openorbit-export.csv"` header set
- [ ] HTTP 400 returned for unsupported `format=` values with descriptive error message
- [ ] Endpoint is unauthenticated (public data export)
- [ ] Integration tests: CSV round-trip (export → parse → assert row count and columns);
      GeoJSON schema validation; empty dataset returns valid empty structure

**Status:** `pending`

---

### PO-037: Prometheus `/metrics` Observability Endpoint

**Priority:** Should Have
**Description:** Operators need visibility into API health and scraper performance
without SSH access to the container. A Prometheus-compatible `/metrics` endpoint
exposes HTTP request counts and durations, scraper run statistics, event ingestion
rates, and claim lifecycle transition counts. Required for production operator visibility.

**Acceptance Criteria:**
- [ ] `/metrics` endpoint returns Prometheus text format (content-type
      `text/plain; version=0.0.4; charset=utf-8`)
- [ ] Exposed metrics include:
      - `openorbit_http_requests_total{method, endpoint, status_code}` (counter)
      - `openorbit_http_request_duration_seconds{method, endpoint}` (histogram)
      - `openorbit_scraper_runs_total{scraper_name, status}` (counter; status=success|failure)
      - `openorbit_scraper_duration_seconds{scraper_name}` (histogram)
      - `openorbit_events_ingested_total{source_tier}` (counter)
      - `openorbit_claim_lifecycle_transitions_total{from_state, to_state}` (counter)
      - `openorbit_launch_events_total{claim_lifecycle}` (gauge; current count per state)
- [ ] Metrics collected via `prometheus-client` library using the default process
      collector + custom collectors
- [ ] `/metrics` endpoint is excluded from rate limiting middleware
- [ ] `/metrics` endpoint access can be IP-restricted via `METRICS_ALLOWED_CIDR` env var
      (default: unrestricted); returns HTTP 403 if caller IP not in allowed range
- [ ] `docker-compose.yml` updated with an optional Prometheus scrape config comment
      showing the correct `scrape_configs` target
- [ ] `docs/deployment.md` updated with Prometheus integration guide
- [ ] Integration tests: response content-type is correct; all expected metric families
      are present in the response body; at least one counter increments after a request

**Status:** `pending`

---

### PO-038: Bluesky Social Scraper — Tier 3 AT Protocol Signal

**Priority:** Should Have
**Description:** Monitor the Bluesky social network (AT Protocol) for space launch
signals using anonymous public search — no API key or credentials required. Posts from
curated official accounts and keyword searches are ingested as Tier 3 attributions
(`evidence_type='media'`). Unmatched posts create new events with
`claim_lifecycle='rumor'`; existing events gain corroboration weight. This is the first
Tier 3 social scraper and exercises the full `BaseScraper` + `ScraperRegistry` plugin
interface with a new signal category.

**Depends on:** PO-015 ✅ (plugin interface), PO-028 ✅ (evidence_type/claim_lifecycle schema)

**Acceptance Criteria:**
- [ ] `src/openorbit/scrapers/bluesky.py` implements `BlueskyScraper` extending `BaseScraper`
- [ ] Uses `atproto` Python SDK (`uv add atproto`) for anonymous public search
      — no API key, no user credentials, no Bluesky account required
- [ ] Searches keywords: `"launch"`, `"liftoff"`, `"rocket"`, `"satellite"`, `"spacecraft"`
      (configurable via ClassVar `SEARCH_TERMS`)
- [ ] Fetches recent posts from curated account list (ClassVar `TRACKED_ACCOUNTS`):
      NASA, SpaceX, NASASpaceflight, SpaceFlightNow, ESA — at minimum 5 accounts
- [ ] Each matched post persisted with `source_tier=3`, `evidence_type='media'`,
      `confidence_rationale` stating "Tier 3 social signal — Bluesky"
- [ ] Unmatched posts create new `LaunchEventCreate` with `claim_lifecycle='rumor'`,
      `event_kind='inferred'`; matched posts update existing event's attribution list
- [ ] Respects rate limiting: polite 1 req/3s (well within ~20 req/min public limit)
- [ ] Auto-registered via `ScraperRegistry`; scheduler picks it up without code changes
- [ ] Unit tests with mocked `atproto` responses; ≥2 sample payloads
- [ ] Integration tests: DB attribution insert, dedup on second run
- [ ] `osint_sources` row seeded for Bluesky with `source_tier=3`

**Status:** `pending`

---

### PO-039: Mastodon Social Scraper — Tier 3 Fediverse Signal

**Priority:** Should Have
**Description:** Monitor public Mastodon hashtag timelines for space launch signals.
The Mastodon REST API is fully open — no authentication required for public hashtag
timelines. The target instance is configurable via `MASTODON_INSTANCE` environment
variable (default: `mastodon.social`), allowing operators to point at any Mastodon
instance or self-hosted server. Posts ingested as Tier 3 attributions.

**Depends on:** PO-015 ✅ (plugin interface), PO-028 ✅ (evidence_type/claim_lifecycle schema)

**Acceptance Criteria:**
- [ ] `src/openorbit/scrapers/mastodon.py` implements `MastodonScraper` extending `BaseScraper`
- [ ] Target instance read from `MASTODON_INSTANCE` env var (default: `mastodon.social`)
- [ ] Polls hashtag timelines: `GET https://{instance}/api/v1/timelines/tag/{hashtag}?limit=40`
- [ ] Monitored hashtags (ClassVar `HASHTAGS`): `spacelaunch`, `spacex`, `nasa`,
      `rocket`, `satellite` — at minimum 5 hashtags
- [ ] Each post persisted with `source_tier=3`, `evidence_type='media'`
- [ ] Posts deduplicated by Mastodon status URL across hashtag queries in same run
- [ ] Respects `Link` header pagination but limits to 2 pages per hashtag per run
- [ ] Auto-registered via `ScraperRegistry`; configurable `refresh_interval_hours` (default 2)
- [ ] Unit tests with mocked httpx responses; tests cover instance config override
- [ ] Integration tests: DB attribution insert, multi-hashtag dedup
- [ ] `osint_sources` row seeded with `source_tier=3` and configurable instance URL

**Status:** `pending`

---

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
      `vehicle`, `confidence_score`, or `claim_lifecycle` changes by more than a
      configurable threshold
- [ ] `GET /v1/launches/{id}/history` returns chronological list of changes
- [ ] History records are append-only (never deleted)
- [ ] Unit tests: history written on status change; no history written on no-op upsert;
      claim_lifecycle transition recorded as a history entry

**Status:** `pending`

---

### PO-019: Webhook / Server-Sent Events for Launch Updates

**Priority:** Could Have
**Description:** Allow API consumers to subscribe to near-real-time launch event
updates via SSE or configurable webhooks. Eliminates consumer polling. Webhook
delivery with exponential-backoff retry. Feature-flagged via `ENABLE_STREAMING`.
Particularly valuable for claim lifecycle transitions (e.g. `indicated → confirmed`).

**Acceptance Criteria:**
- [ ] `GET /v1/launches/stream` returns SSE stream; events emitted on new/updated
      launches and on every claim lifecycle transition
- [ ] `POST /v1/webhooks` registers a URL; `DELETE /v1/webhooks/{id}` removes it
- [ ] Webhook delivers `POST` with launch event JSON including `claim_lifecycle` and
      `event_kind`; retries up to 3× with exponential backoff on failure
- [ ] Feature flag `ENABLE_STREAMING=true` required; endpoints return HTTP 404 when disabled
- [ ] Integration test: mock webhook receiver asserts payload delivery and lifecycle
      transition event payload structure

**Status:** `pending`

---

## Won't Have (this release)

> Explicitly out of scope. Documented here to prevent scope creep.

---

### PO-040: Twitter/X Social Scraper

**Priority:** Won't Have
**Description:** Integration with Twitter/X for social launch signals. **Not implemented
due to cost and ToS barriers.** The free API tier provides 1 request/15 minutes with
no search capability whatsoever. Meaningful read access requires Basic ($100/month),
Pro ($5,000/month), or Enterprise ($42,000+/year). Scraping is explicitly against
Twitter/X's updated Terms of Service and requires constant maintenance against
anti-scraping defenses. This violates the project constraint of "strictly publicly
available (free) OSINT data sources."

Can be revisited if the project ever has a budget for API access.

**Status:** `pending`

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
