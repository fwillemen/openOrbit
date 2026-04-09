# openOrbit

**OSINT platform for orbital launch intelligence**

openOrbit is a modern REST API service that aggregates and tracks orbital launch data from multiple open-source intelligence (OSINT) sources. Built with FastAPI and async SQLite, it provides real-time launch schedules, provider information, and historical launch data with a three-tier source model and a confidence-scored claim lifecycle.

## Features

- 🔑 **API Key Authentication** — PBKDF2-SHA256 hashed keys with admin bootstrap via `OPENORBIT_ADMIN_KEY`
- ✅ **Health Check Endpoint** — `/health` returns service status and version
- 🗄️ **SQLite Database Layer** — 4-table schema with full-text search, multi-source attribution, and confidence scoring
- 📊 **Async Repository Layer** — Type-safe async database access with Pydantic models
- 🛰️ **16 Pluggable Scrapers** — Auto-registered OSINT scrapers across all three tiers; new scrapers require no manual wiring
- 🚀 **Tier 1 Official Sources** — SpaceX API v4, Launch Library 2, ESA, JAXA, ISRO, Arianespace, CNSA
- 📡 **Tier 2 Operational Sources** — FAA NOTAMs, CelesTrak TLE feed, commercial provider feeds
- 🌐 **Tier 3 Social / Analytical Sources** — Bluesky (AT Protocol), Mastodon (public hashtag timelines), Reddit (unauthenticated JSON API), 4chan `/sci/` + `/k/`, SpaceflightNow + NASASpaceflight RSS, Twitter/X API v2 (bearer token required)
- 🔄 **Data Normalization Pipeline** — Converts raw scraper output into canonical `LaunchEvent` models with provider alias resolution, pad geo-enrichment, and multi-format date parsing
- 🖼️ **Image URL Capture** — Social scrapers (Bluesky, Mastodon, Reddit, 4chan) extract image URLs for downstream analysis
- 📋 **Claim Lifecycle Tracking** — `rumor → indicated → corroborated → confirmed | retracted` with per-source provenance
- 🏷️ **Result Tier Classification** — `verified`, `tracked`, `emerging` based on confidence and attribution count
- 🔍 **Full-Text Search** — FTS5 indexes on launch event names for fast `?q=` queries
- 🔄 **Background Scheduler** — Configurable periodic scrape runs via `scheduler.py`
- 📝 **Structured Logging** — JSON logs for production, pretty console for dev
- 🐍 **Type-Safe** — Full type annotations with mypy strict mode
- 🧪 **Well-Tested** — ≥80% code coverage with pytest (90%+ overall)
- 🐳 **Docker-Ready** — Environment-first configuration (12-factor app)

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd openOrbit

# Install dependencies
uv sync

# Copy environment template
cp .env.example .env

# Initialize database
uv run python -m openorbit.cli.db init

# (Optional) Edit .env to customize settings
```

### Run Development Server

```bash
# Start the FastAPI server with auto-reload
uv run uvicorn openorbit.main:app --reload
```

The API will be available at:
- **API:** http://localhost:8000
- **Interactive Docs (Swagger):** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### Run Tests

```bash
# Run all tests with coverage
uv run pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_health.py -v
```

### Code Quality

```bash
# Lint code
uv run ruff check src/ tests/

# Format code
uv run ruff format src/ tests/

# Type check
uv run mypy src/
```

## Authentication

openOrbit uses API key authentication for write operations. All GET endpoints are public.

### Bootstrap Admin Key

Set `OPENORBIT_ADMIN_KEY` in your environment (or `.env`) before starting the server:

```ini
OPENORBIT_ADMIN_KEY=your-strong-secret-here
```

### Create an API Key

```bash
curl -s -X POST http://localhost:8000/v1/auth/keys \
  -H "X-API-Key: your-strong-secret-here" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-key", "is_admin": false}'
```

### Use an API Key

```bash
curl http://localhost:8000/v1/launches \
  -H "X-API-Key: <your-key>"
```

For full details — including revoking keys and error codes — see [docs/auth.md](docs/auth.md).

---

## API Overview

| Method | Endpoint | Auth Required | Description |
|--------|----------|:-------------:|-------------|
| `GET` | `/health` | ❌ | Service health and version |
| `GET` | `/v1/launches` | ❌ | List launch events (filterable, paginated, FTS `?q=`) |
| `GET` | `/v1/launches/{slug}` | ❌ | Get a single launch event by slug |
| `GET` | `/v1/launches/{id}/evidence` | ❌ | List source attributions for a launch event |
| `GET` | `/v1/sources` | ❌ | List OSINT source registry with event counts |
| `GET` | `/v1/admin/stats` | ✅ Admin | Database statistics |
| `POST` | `/v1/admin/sources/{id}/refresh` | ✅ Admin | Trigger a manual scrape for a source |
| `POST` | `/v1/auth/keys` | ✅ Admin | Create a new API key |
| `DELETE` | `/v1/auth/keys/{key_id}` | ✅ Admin | Revoke an API key |

For the full API reference including query parameters and response schemas, see [docs/api-reference.md](docs/api-reference.md).  
Interactive docs (try-it-out): **http://localhost:8000/docs**

### Launch Result Tiers (Dashboard-Friendly)

`GET /v1/launches` and `GET /v1/launches/{slug}` now include fields that help dashboards segment results:

- `result_tier` — one of `emerging`, `tracked`, `verified`
- `evidence_count` — number of source attributions for that event
- `claim_lifecycle` — Epistemic state: `rumor` → `indicated` → `corroborated` → `confirmed` | `retracted`
- `event_kind` — `observed` | `inferred`

You can filter directly by tier or lifecycle state:

```bash
curl -s "http://localhost:8000/v1/launches?result_tier=verified" | python -m json.tool
curl -s "http://localhost:8000/v1/launches?claim_lifecycle=confirmed" | python -m json.tool
```

Tier logic:

- `verified`: confidence >= 80 and at least 2 independent attributions
- `tracked`: confidence >= 60
- `emerging`: lower-confidence early signal

---

## API Endpoints

### `GET /health`

Health check endpoint returning service status.

**Response:**
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

## Database

openOrbit uses SQLite with a 4-table schema:

- **osint_sources** — Registry of OSINT data sources and scrapers
- **raw_scrape_records** — Immutable audit trail of scrape attempts
- **launch_events** — Normalized, deduplicated launch records
- **event_attributions** — Many-to-many linking events to scrape sources with provenance

### Database Features

- ✅ **Async Repository Layer** — Type-safe async database operations
- ✅ **FTS5 Full-Text Search** — Search events by name with relevance ranking via `?q=`
- ✅ **Confidence Scoring** — Auto-calculated based on source attribution count and date precision
- ✅ **Multi-Source Attribution** — Track which sources confirm each event
- ✅ **OSINT Provenance Fields** — `source_url`, `observed_at`, `evidence_type`, `source_tier`, `confidence_score`, `confidence_rationale` on every attribution

### Initialize Database

```bash
python -m openorbit.cli.db init
```

### Use Repository Functions

```python
from openorbit.db import init_db, get_db, upsert_launch_event
from openorbit.models.db import LaunchEventCreate
from datetime import datetime, UTC

async def main():
    await init_db()
    
    async with get_db() as conn:
        event = LaunchEventCreate(
            name="Falcon 9 Launch",
            launch_date=datetime(2025, 1, 22, 14, 30, 0, tzinfo=UTC),
            launch_date_precision="hour",
            provider="SpaceX",
            status="scheduled"
        )
        slug = await upsert_launch_event(conn, event)
        print(f"Created event: {slug}")
```

For complete API documentation, see [Database API Reference](docs/api/database.md).

## Project Structure

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
│   ├── cli_db.py           # DB CLI (init command)
│   ├── middleware/
│   │   └── rate_limiter.py # Sliding-window IP rate limiter
│   ├── api/v1/             # Versioned REST endpoints
│   │   ├── launches.py     # GET /v1/launches (+ ?q= FTS search)
│   │   ├── sources.py      # GET /v1/sources
│   │   ├── evidence.py     # GET /v1/launches/{id}/evidence
│   │   ├── admin.py        # Admin: stats, source refresh
│   │   └── auth.py         # API key CRUD
│   ├── scrapers/           # Pluggable OSINT scrapers (auto-registered)
│   │   ├── base.py         # BaseScraper ABC + __init_subclass__ registry hook
│   │   ├── registry.py     # ScraperRegistry
│   │   ├── public_feed.py  # Shared RSS/Atom adapter
│   │   ├── space_agency.py # Launch Library 2
│   │   ├── spacex_official.py
│   │   ├── celestrak.py    # CelesTrak TLE feed
│   │   ├── notams.py       # FAA NOTAM scraper
│   │   ├── news.py         # SpaceflightNow + NASASpaceflight RSS
│   │   ├── commercial.py   # Commercial launch provider feeds
│   │   ├── bluesky.py      # Bluesky public AT Protocol API
│   │   ├── mastodon.py     # Mastodon public API
│   │   ├── reddit.py       # Reddit public JSON API
│   │   ├── fourchan.py     # 4chan /sci/ + /k/ board scraper
│   │   ├── twitter.py      # Twitter/X API v2 (bearer token required)
│   │   └── *_official.py   # ESA, JAXA, ISRO, Arianespace, CNSA
│   ├── pipeline/           # Normalisation, deduplication, inference
│   └── models/             # Pydantic API + DB models
├── tests/                  # pytest test suite (≥80% coverage)
├── docs/                   # Developer documentation
├── pyproject.toml          # Single config: uv, ruff, mypy, pytest
├── Dockerfile              # Multi-stage build (builder + runtime)
└── docker-compose.yml
```

## Configuration

All configuration is managed via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `VERSION` | `0.1.0` | Application version |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `DATABASE_URL` | `sqlite+aiosqlite:///./openorbit.db` | Database connection string |
| `SCRAPER_DELAY_SECONDS` | `2` | Delay between API requests (rate limiting) |
| `SCRAPER_TIMEOUT_SECONDS` | `30` | HTTP request timeout for scrapers |
| `SCRAPER_MAX_RETRIES` | `3` | Maximum retry attempts on transient failures |
| `SCRAPER_SSL_VERIFY` | `true` | Set to `false` in corporate/proxy environments with SSL inspection (e.g. Capgemini) |
| `TWITTER_BEARER_TOKEN` | _(unset)_ | Twitter/X API v2 Bearer token; leave unset to disable the Twitter scraper |

## Development

### Adding a New API Endpoint

1. Create route module in `src/openorbit/api/v1/`
2. Define router and endpoints
3. Register router in `src/openorbit/main.py`
4. Add tests in `tests/`

### Running Individual Scrapers

All scrapers can be run as one-shot commands. Each fetches data, upserts launch events, prints a summary, and exits.

**Tier 1 — Official sources:**

```bash
uv run python -m openorbit.scrapers.space_agency
uv run python -m openorbit.scrapers.spacex_official
uv run python -m openorbit.scrapers.esa_official
uv run python -m openorbit.scrapers.jaxa_official
uv run python -m openorbit.scrapers.isro_official
uv run python -m openorbit.scrapers.arianespace_official
uv run python -m openorbit.scrapers.cnsa_official
```

**Tier 2 — Operational / corroboration sources:**

```bash
uv run python -m openorbit.scrapers.celestrak
uv run python -m openorbit.scrapers.notams
uv run python -m openorbit.scrapers.commercial
```

**Tier 3 — Social / analytical sources:**

```bash
uv run python -m openorbit.scrapers.news
uv run python -m openorbit.scrapers.bluesky
uv run python -m openorbit.scrapers.mastodon
uv run python -m openorbit.scrapers.reddit
uv run python -m openorbit.scrapers.fourchan
```

**Twitter/X (requires bearer token):**

Set `TWITTER_BEARER_TOKEN` in `.env` first. Without it the scraper exits silently.
Free-tier rate limiting (180 requests / 15 min) is respected automatically.

```bash
uv run python -m openorbit.scrapers.twitter
```

### What to Do After Scraping

1. Start the API server:

```bash
uv run uvicorn openorbit.main:app --reload
```

2. In another terminal, query the scraped events:

```bash
curl -s http://localhost:8000/v1/launches | python -m json.tool | head -n 60
```

3. Full-text search:

```bash
curl -s "http://localhost:8000/v1/launches?q=falcon" | python -m json.tool
```

4. Filter by result tier or claim lifecycle:

```bash
curl -s "http://localhost:8000/v1/launches?result_tier=verified" | python -m json.tool
curl -s "http://localhost:8000/v1/launches?claim_lifecycle=confirmed" | python -m json.tool
```

5. Check source metadata and last scrape timestamps:

```bash
curl -s http://localhost:8000/v1/sources | python -m json.tool
```

See [docs/scrapers/space-agency.md](docs/scrapers/space-agency.md) for configuration and detailed documentation.

### Inspecting the Database Directly

All commands below use the built-in `sqlite3` Python module against the local `openorbit.db` file.

**Schema — show all table definitions:**
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('openorbit.db')
for row in conn.execute(\"SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name\"):
    print(row[0])
    print()
conn.close()
"
```

**Row counts per table:**
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('openorbit.db')
for table in ['osint_sources', 'raw_scrape_records', 'launch_events', 'event_attributions']:
    count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    print(f'{table}: {count}')
conn.close()
"
```

**Browse launch events (slug, name, provider, status, confidence, lifecycle):**
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('openorbit.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT slug, name, provider, status, confidence_score, claim_lifecycle FROM launch_events LIMIT 20').fetchall()
for r in rows:
    print(dict(r))
conn.close()
"
```

**Browse sources and last scrape timestamps:**
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('openorbit.db')
conn.row_factory = sqlite3.Row
for r in conn.execute('SELECT id, name, source_tier, last_scraped_at FROM osint_sources'):
    print(dict(r))
conn.close()
"
```

Alternatively, open `openorbit.db` in [DB Browser for SQLite](https://sqlitebrowser.org/) for a full visual schema and table browser.

### Understanding `/v1/sources` Output

The `/v1/sources` endpoint currently merges two source views:

1. **DB-backed source rows**
  - Have a numeric `id`
  - Have real `event_count` / `last_scraped_at`

2. **Registry placeholder rows**
  - Have `id: null`
  - Represent available scraper modules that may not have been registered in DB yet
  - Typically show `event_count: 0`

This means you may see both a human-readable DB source name (for example
`SpaceX API v4`) and a module-style registry name (for example
`spacex_official`) in the same response.

### Connector Coverage Profile

The table below summarizes what each current connector contributes.

| Connector | Tier | Primary Signal | Time Horizon | Trust | Limitations |
|----------|------|----------------|--------------|-------|-------------|
| `space_agency` (Launch Library 2) | 1 | Aggregated launch schedule API | Upcoming + near-term | High | Aggregator — not always first-party official |
| `spacex_official` (SpaceX API v4) | 1 | Official operator launch data | Upcoming + mission updates | High | SpaceX-only scope |
| `esa_official` | 1 | Official agency publication feed | Announcement-driven | High | RSS text requires inference, less structured |
| `jaxa_official` | 1 | Official agency publication feed | Announcement-driven | High | RSS text requires inference, less structured |
| `isro_official` | 1 | Official agency publication feed | Announcement-driven | High | RSS text requires inference, less structured |
| `arianespace_official` | 1 | Official operator publication feed | Announcement-driven | High | Feed granularity varies |
| `cnsa_official` | 1 | Official/state publication feed | Announcement-driven | Medium–High | Feed consistency and structure can vary |
| `celestrak` (last-30-days GP) | 2 | Post-launch object catalog activity | Recent launches (~30 days) | Medium–High | Not a future launch schedule feed |
| `notams` (FAA) | 2 | Airspace/regulatory launch indicators | Pre-launch + operational windows | Medium | Region/format constraints; indirect launch metadata |
| `commercial` (Launch Library 2) | 2 | Commercial provider schedule feed | Upcoming launches | Medium–High | SpaceX + Rocket Lab only |
| `news` (RSS) | 3 | SpaceflightNow + NASASpaceflight RSS | Announcement-driven | Medium | Fuzzy entity linking; rumor-level by default |
| `bluesky` | 3 | Public AT Protocol keyword search | Real-time | Low–Medium | Community posts; rumor-level by default |
| `mastodon` | 3 | Public hashtag timelines | Real-time | Low–Medium | Community posts; rumor-level by default |
| `reddit` | 3 | Curated space subreddits (public JSON) | Real-time | Low–Medium | Community posts; image gallery capture |
| `fourchan` | 3 | /sci/ + /k/ boards | Real-time | Low | Highly speculative; signal-in-noise trade-off |
| `twitter` | 3 | Twitter/X API v2 recent search | Real-time | Low–Medium | Requires bearer token; free tier is rate-limited |

Practical takeaway: combine structured APIs (`space_agency`, `spacex_official`) with
corroboration feeds (`celestrak`, `notams`, regional official feeds) and social/news
sources for the best balance between coverage, trust, and timeliness.

### Intelligence Collection Blueprint

If your goal is broad launch intelligence (including low-visibility activity), use a
layered model instead of relying on a single feed type.

#### Signal Tiers

| Tier | Signal Type | Example Sources | Typical Value |
|------|-------------|-----------------|---------------|
| Tier 1 | Official / operator / regulator | SpaceX API, agency official feeds, FAA notices | High-trust baseline facts |
| Tier 2 | Operational corroboration | CelesTrak post-launch objects, range/airspace indicators | Confirms or challenges Tier 1 |
| Tier 3 | Analyst/speculation channels | Reputable expert commentary and specialist media | Early weak signals, hypothesis generation |

#### Claim Lifecycle

Track event confidence as a lifecycle, not a boolean:

1. `rumor` — single weak-signal mention
2. `indicated` — one operational signal or multiple independent mentions
3. `corroborated` — at least two independent source classes agree
4. `confirmed` — direct official/operator or strong post-event evidence
5. `retracted` — contradicted by stronger evidence

#### Confidence Rules (Practical)

1. Never mark `confirmed` from one speculative source.
2. Require cross-class corroboration for escalation (for example: feed + NOTAM, or
  feed + CelesTrak).
3. Keep attribution and timestamps for every assertion (who said what, when).
4. Preserve contradictory claims instead of overwriting history.

#### What This Enables

With this approach, openOrbit can support:

- Detection of not-yet-prominent launch activity
- Separation of facts from hypotheses
- Progressive confidence updates as new evidence arrives
- Explainable outputs backed by source provenance

### Adding a New Scraper

Scrapers are auto-registered at import time via `__init_subclass__` — no manual wiring needed.

1. Create module in `src/openorbit/scrapers/<name>.py` extending `BaseScraper` (or `PublicFeedScraper` for RSS/Atom)
2. Import it in `src/openorbit/scrapers/__init__.py` to trigger registration
3. Add tests in `tests/test_scrapers_<name>.py`
4. Add documentation in `docs/scrapers/<name>.md`

```python
class MyScraper(BaseScraper):
    source_name: ClassVar[str] = "my_source"
    source_url: ClassVar[str] = "https://example.com/feed"
    source_tier: ClassVar[int] = 1   # 1 / 2 / 3
    evidence_type: ClassVar[str] = "official_schedule"

    async def scrape(self) -> dict[str, int]: ...
    def parse(self, raw_data: str) -> list[LaunchEventCreate]: ...
```

See [docs/scrapers/plugin-interface.md](docs/scrapers/plugin-interface.md) for the full plugin contract.

## Architecture

openOrbit follows modern Python best practices:

- **src/ Layout** — Clean separation of source and tests
- **Async-First** — Non-blocking I/O with aiosqlite and FastAPI
- **Environment-First Config** — 12-factor app principles via Pydantic Settings
- **Type-Safe** — Full type annotations with mypy strict mode
- **Scraper Plugin Pattern** — `BaseScraper.__init_subclass__` auto-registers scrapers; no manual wiring
- **Three-Tier Source Model** — Tier 1 (official), Tier 2 (operational), Tier 3 (social/analytical)
- **Claim Lifecycle** — `rumor → indicated → corroborated → confirmed | retracted`
- **Result Tiers** — `verified` (confidence ≥ 80 + ≥2 attributions), `tracked` (≥ 60), `emerging` (all others)
- **Normalization Pipeline** — Raw scraper output flows through `openorbit.pipeline.normalize()` which resolves provider aliases, enriches pad coordinates, and validates data via Pydantic v2 before it reaches the database. See [docs/normalization.md](docs/normalization.md) for full reference.

## License

[Add license information]

## Contributing

[Add contribution guidelines]
