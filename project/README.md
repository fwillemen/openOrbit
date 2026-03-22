# openOrbit

**OSINT platform for orbital launch intelligence**

openOrbit is a modern REST API service that aggregates and tracks orbital launch data from multiple open-source intelligence (OSINT) sources. Built with FastAPI and async SQLite, it provides real-time launch schedules, provider information, and historical launch data.

## Features

- ✅ **Health Check Endpoint** — `/health` returns service status and version
- 🗄️ **SQLite Database Layer** — 4-table schema with full-text search, multi-source attribution, and confidence scoring
- 📊 **13 Repository Functions** — Type-safe async database access with Pydantic models
- 🛰️ **Space Agency Launch Scraper** — Automated data collection from Launch Library 2 API with retry logic and attribution tracking
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
│   ├── scrapers/           # OSINT data scrapers
│   │   ├── base.py         # Abstract base scraper class
│   │   └── space_agency.py # Launch Library 2 API scraper
│   └── models/
│       ├── __init__.py
│       └── db.py           # Pydantic models for DB entities
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

See [docs/scrapers/space-agency.md](../docs/scrapers/space-agency.md) for configuration and detailed documentation.

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

For detailed architecture decisions, see `state/decisions.md` in the parent repository.

## License

[Add license information]

## Contributing

[Add contribution guidelines]
