# Copilot Instructions — openOrbit

## Project Overview
openOrbit is a **Python OSINT launch-tracking API** that aggregates space launch intelligence
from multiple official, operational, and analytical sources. It exposes a FastAPI REST service
backed by SQLite with FTS5 full-text search, a three-tier source model, and a claim lifecycle
for tracking corroboration confidence.

## Repository Layout

```
openOrbit/
├── src/openorbit/          # Main package
│   ├── main.py             # FastAPI app factory
│   ├── config.py           # Pydantic settings (env vars)
│   ├── db.py               # SQLite access layer + migrations
│   ├── schema.sql          # Canonical schema (4 tables + FTS5)
│   ├── tiering.py          # Result tier classification
│   ├── scheduler.py        # Background scrape scheduler
│   ├── auth.py             # API key management
│   ├── api/v1/             # Versioned REST endpoints
│   │   ├── launches.py     # GET /v1/launches (+ ?q= FTS search)
│   │   ├── sources.py      # GET /v1/sources
│   │   ├── evidence.py     # GET /v1/launches/{id}/evidence
│   │   ├── admin.py        # Admin: stats, source refresh
│   │   └── auth.py         # API key CRUD
│   ├── scrapers/           # Pluggable OSINT scrapers
│   │   ├── base.py         # BaseScraper ABC + auto-registry hook
│   │   ├── public_feed.py  # Shared RSS/Atom adapter
│   │   ├── space_agency.py # Launch Library 2
│   │   ├── spacex_official.py
│   │   ├── celestrak.py    # CelesTrak TLE feed
│   │   ├── notams.py       # FAA NOTAM scraper
│   │   ├── news.py         # SpaceflightNow + NASASpaceflight RSS
│   │   ├── bluesky.py      # Bluesky public AT Protocol API
│   │   ├── mastodon.py     # Mastodon public API
│   │   └── *_official.py   # ESA, JAXA, ISRO, Arianespace, CNSA
│   ├── pipeline/           # Normalisation, deduplication, inference
│   └── models/             # Pydantic API + DB models
├── tests/                  # pytest test suite (553 tests, 90% coverage)
├── docs/                   # Developer documentation
├── pyproject.toml          # Single config: uv, ruff, mypy, pytest
├── Dockerfile              # Multi-stage build (builder + runtime)
└── docker-compose.yml
```

## OSINT Three-Tier Source Model

All scrapers, schema fields, and API responses must conform to this model:

### Source Tiers (`osint_sources.source_tier`)
- **Tier 1** — Official/Regulatory: space agencies, operators, regulators (ground-truth)
- **Tier 2** — Operational/Catalog: NOTAMs, TLE anomalies, maritime warnings, range scheduling
- **Tier 3** — Analytical/Social: news RSS, Bluesky, Mastodon, expert analysis

### Claim Lifecycle (`launch_events.claim_lifecycle`)
```
rumor → indicated → corroborated → confirmed → retracted
```
Social/news posts always enter as `claim_lifecycle='rumor'`, `event_kind='inferred'`.
Tier 1 sources enter as `claim_lifecycle='confirmed'`, `event_kind='observed'`.

### Event Kind (`launch_events.event_kind`)
- `observed` — directly documented by Tier 1/2 sources
- `inferred` — assembled from multiple signals

### Evidence Types (`event_attributions.evidence_type`)
`official_schedule` | `notam` | `maritime_warning` | `range_signal` | `tle_anomaly` |
`contract_award` | `expert_analysis` | `media` | `imagery`

### Provenance Fields on `event_attributions`
Every attribution must carry: `source_url`, `observed_at`, `evidence_type`, `source_tier`,
`confidence_score`, `confidence_rationale`.

## Result Tiering Strategy

Launch events are classified into three result tiers for API consumers:

| Tier | Condition |
|------|-----------|
| `verified` | `confidence >= 80` AND `attribution_count >= 2` |
| `tracked` | `confidence >= 60` |
| `emerging` | all others |

**Key files:**
- `src/openorbit/tiering.py` — tier classification logic
- `src/openorbit/models/api.py` — `result_tier` and `evidence_count` response fields
- `src/openorbit/api/v1/launches.py` — tier filtering via `?tier=` query param
- `src/openorbit/db.py` — SQL-level tier filtering

When changing tier/confidence behaviour:
- Keep SQL filtering and Python classification in sync
- Preserve `result_tier` and `evidence_count` response fields
- Update `tests/test_api_launches.py` and `tests/test_tiering.py`

## Scraper Plugin Pattern

All scrapers extend `BaseScraper` and are **auto-registered** at import time via
`__init_subclass__` into `ScraperRegistry`. No manual registration needed.

```python
class MyScraper(BaseScraper):
    source_name: ClassVar[str] = "my_source"
    source_url: ClassVar[str] = "https://example.com/feed"
    source_tier: ClassVar[int] = 1   # 1 / 2 / 3
    evidence_type: ClassVar[str] = "official_schedule"

    async def scrape(self) -> dict[str, int]: ...
    def parse(self, raw_data: str) -> list[LaunchEventCreate]: ...
```

For RSS/Atom sources, extend `PublicFeedScraper` (which extends `BaseScraper`) instead.
Note: `PublicFeedScraper.parse()` is sync despite the base class — use `# type: ignore[override]`.

When adding a new scraper:
1. Implement in `src/openorbit/scrapers/<name>.py`
2. Import in `src/openorbit/scrapers/__init__.py` to trigger registration
3. Add tests in `tests/test_scrapers_<name>.py`
4. Add documentation in `docs/scrapers/<name>.md`

## Adding a New Source

Prefer **non-credentialed official/public endpoints** first. Reuse `public_feed.py` for RSS/Atom.
Keep status, vehicle, and location normalisation source-specific and tested.
Update `README.md` and `docs/scrapers/` in the same change.

## Python Stack

| Concern | Tool |
|---------|------|
| Package management | `uv` (never `pip` directly) |
| Testing | `pytest` + `pytest-cov` (minimum 80% coverage) |
| Linting / formatting | `ruff check` and `ruff format` |
| Type checking | `mypy` (strict mode) |
| Docstrings | Google style |
| Python version | 3.12+ |
| Async mode | `asyncio_mode = "auto"` in pyproject.toml |

### Common commands

```bash
uv sync                                           # install deps
uv run pytest --cov=src -q                        # run tests
uv run ruff check src/ tests/ --fix               # lint
uv run ruff format src/ tests/                    # format
uv run mypy src/                                  # type check
uv run uvicorn openorbit.main:app --reload        # dev server
uv run python -m openorbit.db migrate             # apply schema migrations
```

## Database Access Pattern

- No standalone `sqlite3` binary assumed — use `python3 -c "import sqlite3; ..."` for ad-hoc queries
- All DB functions are `async` and use `aiosqlite.Connection` dependency injection via `get_db()`
- Schema migrations live in `db.py`'s `migrate()` function — idempotent, safe to re-run
- FTS5 rebuild guard uses column-count check (`< 6`) to detect old schema

## CI/CD

GitHub Actions CI (`.github/workflows/ci.yml`) runs on every push to `main` and all PRs:
- `lint` — ruff check + format check
- `typecheck` — mypy strict
- `test` — pytest with `--cov-fail-under=80`

All three jobs run in parallel on `ubuntu-latest` / Python 3.12 / `uv`.

## Commit Style (Conventional Commits)

```
feat(<scope>): add social media scraper for Bluesky
fix(<scope>): handle empty NOTAM response gracefully
test(<scope>): add edge cases for tiering logic
docs(<scope>): update API reference with evidence endpoint
chore: update dependencies
refactor(<scope>): extract claim lifecycle validator
```

Always include the Co-authored-by trailer:
```
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```
