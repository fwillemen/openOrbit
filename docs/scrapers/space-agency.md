# Space Agency Launch Scraper

## Overview

The Space Agency Launch Scraper (`openorbit.scrapers.space_agency`) collects upcoming and recent orbital launch events from the [Launch Library 2 API](https://ll.thespacedevs.com/2.3.0/swagger/). This scraper forms the primary data source for openOrbit's launch intelligence platform.

## Features

- **Automatic retry logic** with exponential backoff for resilient data fetching
- **Idempotent scraping** — safe to run multiple times without data duplication
- **Full attribution tracking** — every launch event links back to its source scrape
- **Structured data normalization** — maps LL2 API responses to openOrbit schema
- **Configurable delays** to respect API rate limits

## Configuration

The scraper is configured via environment variables (see `openorbit.config.Settings`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SCRAPER_DELAY_SECONDS` | `2` | Delay between API requests to avoid rate limiting |
| `SCRAPER_TIMEOUT_SECONDS` | `30` | HTTP request timeout |
| `SCRAPER_MAX_RETRIES` | `3` | Maximum retry attempts on transient failures |
| `DATABASE_URL` | `sqlite+aiosqlite:///./openorbit.db` | Database connection string |

## Usage

### Command Line

Run the scraper as a standalone module:

```bash
cd project
uv run python -m openorbit.scrapers.space_agency
```

This will:
1. Connect to the database specified in `DATABASE_URL`
2. Fetch upcoming launches from Launch Library 2 API
3. Parse and normalize the response
4. Upsert launch events to the `launch_events` table
5. Create attribution records linking events to the scrape run

### Programmatic

```python
from openorbit.scrapers.space_agency import SpaceAgencyScraper
from openorbit.db import init_db, close_db

async def run_scrape():
    await init_db()
    scraper = SpaceAgencyScraper()
    await scraper.scrape()
    await close_db()
```

## API Reference

### `SpaceAgencyScraper`

Primary scraper class for Launch Library 2 API integration.

#### Methods

##### `async scrape() -> None`

Orchestrates the full scrape cycle:
1. Fetches data from Launch Library 2 API (with retries)
2. Logs the raw response payload to `scrape_runs` table
3. Parses and normalizes JSON response
4. Upserts launch events to `launch_events` table
5. Creates attribution records in `event_attributions` table

**Raises:**
- `httpx.HTTPError`: If all retry attempts fail

**Example:**
```python
scraper = SpaceAgencyScraper()
await scraper.scrape()
```

##### `async fetch_with_retry() -> str`

Fetches data from the API with exponential backoff retry logic.

**Returns:**
- Raw JSON response as string

**Retry behavior:**
- Retries on server errors (5xx) and timeout errors
- Does NOT retry on client errors (4xx) except 429 (rate limit)
- Exponential backoff: 1s, 2s, 4s between retries

##### `parse(raw_json: str) -> list[LaunchEventCreate]`

Parses and normalizes the Launch Library 2 API response.

**Args:**
- `raw_json`: Raw JSON string from the API

**Returns:**
- List of `LaunchEventCreate` objects ready for database insertion

**Normalization:**
- Maps LL2 status codes to openOrbit status enum
- Extracts mission name, launch provider, location
- Handles missing optional fields gracefully
- Converts timestamps to UTC

## Data Flow

```
┌─────────────────────┐
│ Launch Library 2 API│
│ (upstream source)   │
└──────────┬──────────┘
           │ HTTP GET
           ▼
┌─────────────────────┐
│ SpaceAgencyScraper  │
│ .fetch_with_retry() │
└──────────┬──────────┘
           │ Raw JSON
           ▼
┌─────────────────────┐
│ .parse()            │
│ Normalize to schema │
└──────────┬──────────┘
           │ LaunchEventCreate[]
           ▼
┌─────────────────────┐
│ Database            │
│ - scrape_runs       │ ← Log raw payload
│ - launch_events     │ ← Upsert normalized events
│ - event_attributions│ ← Link events to scrape
└─────────────────────┘
```

## Error Handling

- **Network errors:** Retried up to `SCRAPER_MAX_RETRIES` times
- **Parse errors:** Logged and raised (scrape aborted)
- **Duplicate events:** Handled via `upsert_launch_event` (updates existing records)
- **Missing fields:** Gracefully defaults to `None` for optional fields

## Testing

The scraper has 93% test coverage with 17 test cases covering:

- JSON parsing (valid, empty, malformed responses)
- Status and precision code mapping
- Retry logic (success, server errors, timeouts, rate limits)
- End-to-end scraping workflow
- Idempotency guarantees
- Attribution logging

Run tests:
```bash
cd project
uv run pytest tests/test_scrapers_space_agency.py -v --cov=openorbit.scrapers.space_agency
```

## Future Enhancements

- [ ] Support pagination for large result sets
- [ ] Add filtering by date range or launch provider
- [ ] Implement change detection (only upsert modified events)
- [ ] Add Prometheus metrics for scrape success/failure rates
- [ ] Support webhook notifications on new launches
