# openOrbit

**OSINT platform for orbital launch intelligence**

openOrbit is a modern REST API service that aggregates and tracks orbital launch data from multiple open-source intelligence (OSINT) sources. Built with FastAPI and async SQLite, it provides real-time launch schedules, provider information, and historical launch data.

## Features

- 🔑 **API Key Authentication** — PBKDF2-SHA256 hashed keys with admin bootstrap via `OPENORBIT_ADMIN_KEY`
- ✅ **Health Check Endpoint** — `/health` returns service status and version
- 🗄️ **SQLite Database Layer** — 4-table schema with full-text search, multi-source attribution, and confidence scoring
- 📊 **13 Repository Functions** — Type-safe async database access with Pydantic models
- 🛰️ **Space Agency Launch Scraper** — Automated data collection from Launch Library 2 API with retry logic and attribution tracking
- 🚀 **Official SpaceX Source** — Direct ingestion from SpaceX API v4 for primary-source mission updates
- 🌍 **CelesTrak Public Feed** — Non-credentialed recent-launch ingest from CelesTrak GP dataset
- 🇪🇺 **ESA Official Adapter** — Public ESA feed connector for European launch-related updates
- 🇯🇵 **JAXA Official Adapter** — Public JAXA feed connector for Japanese launch-related updates
- 🇮🇳 **ISRO Official Adapter** — Public ISRO feed connector for Indian launch-related updates
- 🇪🇺 **Arianespace Adapter** — Public Arianespace feed connector for European commercial launch updates
- 🇨🇳 **CNSA Adapter** — Public CNSA feed connector for Chinese launch-related updates
- 🐦 **Twitter/X Adapter** — Twitter API v2 scraper for launch-related tweets from tracked accounts (requires bearer token)
- 🔄 **Data Normalization Pipeline** — Converts raw scraper dicts into canonical `LaunchEvent` models with provider alias resolution, pad geo-enrichment, and multi-format date parsing
- 🔄 **Async Architecture** — Non-blocking I/O for high-performance data collection
- 📝 **Structured Logging** — JSON logs for production, pretty console for dev
- 🐍 **Type-Safe** — Full type annotations with mypy strict mode
- 🧪 **Well-Tested** — ≥80% code coverage with pytest (87% overall, 93% scraper coverage)
- 🐳 **Docker-Ready** — Environment-first configuration (12-factor app)
- 🔍 **Full-Text Search** — FTS5 indexes on launch event names for fast queries

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd openOrbit/project

# Install dependencies
uv sync

# Copy environment template
cp .env.example .env

# Initialize database
python -m openorbit.cli.db init

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

For full details — including revoking keys and error codes — see [docs/auth.md](../docs/auth.md).

---

## API Overview

| Method | Endpoint | Auth Required | Description |
|--------|----------|:-------------:|-------------|
| `GET` | `/health` | ❌ | Service health and version |
| `GET` | `/v1/launches` | ❌ | List launch events (filterable, paginated) |
| `GET` | `/v1/launches/{slug}` | ❌ | Get a single launch event by slug |
| `GET` | `/v1/sources` | ❌ | List OSINT source registry with event counts |
| `POST` | `/v1/auth/keys` | ✅ Admin | Create a new API key |
| `DELETE` | `/v1/auth/keys/{key_id}` | ✅ Admin | Revoke an API key |

For the full API reference including query parameters and response schemas, see [docs/api-reference.md](../docs/api-reference.md).  
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
- **event_attributions** — Many-to-many linking events to scrape sources

### Database Features

- ✅ **13 Repository Functions** — Type-safe async database operations
- ✅ **FTS5 Full-Text Search** — Search events by name with relevance ranking
- ✅ **Confidence Scoring** — Auto-calculated based on source attribution count and date precision
- ✅ **Multi-Source Attribution** — Track which sources confirm each event
- ✅ **PostgreSQL-Compatible** — Migration path to PostgreSQL for production

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

For complete API documentation, see [Database API Reference](../docs/api/database.md).

## Project Structure

```
project/
├── src/openorbit/          # Main package
│   ├── main.py             # FastAPI app initialization
│   ├── config.py           # Environment-based configuration
│   ├── db.py               # 13 async repository functions
│   ├── schema.sql          # 4-table SQLite schema
│   ├── api/                # API route modules
│   │   └── health.py       # Health check endpoint
│   ├── pipeline/           # Data normalization pipeline
│   │   ├── normalizer.py   # normalize(raw, source) → LaunchEvent
│   │   ├── aliases.py      # Provider aliases & pad locations
│   │   └── exceptions.py   # NormalizationError
│   ├── scrapers/           # OSINT data scrapers
│   │   ├── base.py         # Abstract base scraper class
│   │   └── space_agency.py # Launch Library 2 API scraper
│   └── models/
│       ├── __init__.py
│       ├── db.py           # Pydantic models for DB entities
│       └── launch_event.py # Canonical LaunchEvent pipeline model
├── tests/                  # Test suite
│   ├── conftest.py         # Pytest fixtures & database setup
│   ├── test_health.py      # Health endpoint tests
│   ├── test_config.py      # Configuration tests
│   └── test_db.py          # Database repository tests
├── pyproject.toml          # Project configuration & dependencies
└── .env.example            # Environment variable template
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

1. Create route module in `src/openorbit/api/`
2. Define router and endpoints
3. Register router in `src/openorbit/main.py`
4. Add tests in `tests/`

### Running the Scraper

The Space Agency Launch Scraper collects upcoming launches from Launch Library 2 API:

```bash
cd project
uv run python -m openorbit.scrapers.space_agency
```

This is a one-shot command. It fetches data, upserts launch events, prints a summary, and exits.
If you run it again shortly after, you will usually see mostly "updated" events and few "new" events.

### What to Do After Scraping

1. Start the API server:

```bash
cd project
uv run uvicorn openorbit.main:app --reload
```

2. In another terminal, query the scraped events:

```bash
curl -s http://localhost:8000/v1/launches | python -m json.tool | head -n 60
```

3. Check source metadata and last scrape timestamp:

```bash
curl -s http://localhost:8000/v1/sources | python -m json.tool
```

4. (Optional) Verify event count directly in SQLite:

```bash
cd project
python - <<'PY'
import sqlite3

conn = sqlite3.connect("openorbit.db")
count = conn.execute("SELECT COUNT(*) FROM launch_events").fetchone()[0]
print(f"launch_events rows: {count}")
conn.close()
PY
```

See [docs/scrapers/space-agency.md](../docs/scrapers/space-agency.md) for configuration and detailed documentation.

### Running Official SpaceX Source

For a primary-source feed, run the SpaceX official API scraper:

```bash
cd project
uv run python -m openorbit.scrapers.spacex_official
```

Then verify source coverage:

```bash
curl -s http://localhost:8000/v1/sources | python -m json.tool
```

### Running CelesTrak Public Source

For a non-credentialed corroboration source of recently launched objects:

```bash
cd project
uv run python -m openorbit.scrapers.celestrak
```

This uses CelesTrak's public `last-30-days` GP feed and aggregates payload records
into launch-level events before upserting.

### Running EU and Asia Feed Adapters

All of the following are non-credentialed connectors:

```bash
cd project

uv run python -m openorbit.scrapers.esa_official
uv run python -m openorbit.scrapers.jaxa_official
uv run python -m openorbit.scrapers.isro_official
uv run python -m openorbit.scrapers.arianespace_official
uv run python -m openorbit.scrapers.cnsa_official
```

Each adapter ingests RSS/Atom-like public feed entries and maps launch-related items
into canonical launch events.

### Running Twitter/X Scraper

The Twitter scraper requires an API v2 Bearer token. Set it in `.env` first:

```ini
TWITTER_BEARER_TOKEN=your-bearer-token-here
```

Then run:

```bash
cd project
uv run python -m openorbit.scrapers.twitter
```

Without a bearer token the scraper exits silently with `total_fetched: 0` — it will not fail.
Free-tier rate limiting (180 requests / 15 min) is respected automatically.

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

| Connector | Primary Signal | Time Horizon | Structured Quality | Strengths | Limitations |
|----------|----------------|--------------|--------------------|-----------|-------------|
| `space_agency` (Launch Library 2) | Aggregated launch schedule API | Upcoming + near-term updates | High | Broad global coverage, rich launch metadata | Aggregator (not always first-party official) |
| `spacex_official` (SpaceX API v4) | Official operator launch data | Upcoming + mission updates | High | First-party for SpaceX launches, strong timeliness | SpaceX-only scope |
| `celestrak` (last-30-days GP) | Post-launch object catalog activity | Recent launches (last ~30 days) | Medium-High | Strong corroboration of recent launched activity | Not a future launch schedule feed |
| `notams` (FAA) | Airspace/regulatory launch indicators | Pre-launch + operational windows | Medium | Useful corroboration and launch window signals | Region/format constraints; indirect launch metadata |
| `esa_official` | Official agency publication feed | Announcement-driven | Medium | High trust source for ESA-related missions | RSS/news text requires inference, less structured |
| `jaxa_official` | Official agency publication feed | Announcement-driven | Medium | High trust source for JAXA-related missions | RSS/news text requires inference, less structured |
| `isro_official` | Official agency publication feed | Announcement-driven | Medium | High trust source for ISRO-related missions | RSS/news text requires inference, less structured |
| `arianespace_official` | Official operator publication feed | Announcement-driven | Medium | High trust for Arianespace mission updates | Feed granularity varies; less structured launch fields |
| `cnsa_official` | Official/state publication feed | Announcement-driven | Medium-Low to Medium | Geographic coverage expansion for China missions | Feed consistency and structure can vary over time |
| `twitter` | Twitter/X API v2 recent search | Real-time / recent | Low-Medium | Fast signal for breaking launch events; tracked account feeds | Requires paid bearer token; free tier is heavily rate-limited |

Practical takeaway: combine structured APIs (`space_agency`, `spacex_official`) with
corroboration feeds (`celestrak`, `notams`, regional official feeds) for the best
balance between coverage, trust, and timeliness.

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

1. Create module in `src/openorbit/scrapers/`
2. Implement `fetch()` method following the pattern in `space_agency.py`
3. Add tests with mocked HTTP responses

## Architecture

openOrbit follows modern Python best practices:

- **src/ Layout** — Clean separation of source and tests
- **Async-First** — Non-blocking I/O with aiosqlite and FastAPI
- **Environment-First Config** — 12-factor app principles
- **Type-Safe** — Full type annotations with mypy
- **Modular Design** — Clear separation of API, data, and scraping concerns
- **Normalization Pipeline** — Raw scraper output flows through `openorbit.pipeline.normalize()` which resolves provider aliases, enriches pad coordinates, and validates data via Pydantic v2 before it reaches the database. See [docs/normalization.md](../docs/normalization.md) for full reference.

For detailed architecture decisions, see `state/decisions.md` in the parent repository.

## License

[Add license information]

## Contributing

[Add contribution guidelines]
