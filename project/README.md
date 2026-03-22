# openOrbit

**OSINT platform for orbital launch intelligence**

openOrbit is a modern REST API service that aggregates and tracks orbital launch data from multiple open-source intelligence (OSINT) sources. Built with FastAPI and async SQLite, it provides real-time launch schedules, provider information, and historical launch data.

## Features

- ✅ **Health Check Endpoint** — `/health` returns service status and version
- 🔄 **Async Architecture** — Non-blocking I/O for high-performance data collection
- 📝 **Structured Logging** — JSON logs for production, pretty console for dev
- 🐍 **Type-Safe** — Full type annotations with mypy strict mode
- 🧪 **Well-Tested** — ≥80% code coverage with pytest
- 🐳 **Docker-Ready** — Environment-first configuration (12-factor app)

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

## Project Structure

```
project/
├── src/openorbit/          # Main package
│   ├── main.py             # FastAPI app initialization
│   ├── config.py           # Environment-based configuration
│   ├── db.py               # Async SQLite connection management
│   ├── api/                # API route modules
│   │   └── health.py       # Health check endpoint
│   ├── scrapers/           # OSINT data scrapers (future)
│   └── models/             # Pydantic models & DB schemas (future)
├── tests/                  # Test suite
│   ├── conftest.py         # Pytest fixtures
│   ├── test_health.py      # Health endpoint tests
│   ├── test_config.py      # Configuration tests
│   └── test_db.py          # Database tests
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

## Development

### Adding a New API Endpoint

1. Create route module in `src/openorbit/api/`
2. Define router and endpoints
3. Register router in `src/openorbit/main.py`
4. Add tests in `tests/`

### Adding a New Scraper

1. Create module in `src/openorbit/scrapers/`
2. Implement `fetch()` method
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
