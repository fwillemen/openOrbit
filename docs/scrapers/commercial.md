# Commercial Launch Scraper

## Overview

`CommercialLaunchScraper` (`openorbit.scrapers.commercial`) fetches upcoming launch events for **SpaceX** and **Rocket Lab** from the [Launch Library 2 (LL2) public API](https://ll.thespacedevs.com/2.2.0/swagger/). Each provider is registered as a distinct OSINT source in the database so scrape provenance is fully traceable.

Events are normalised through the pipeline before upsertion, and the scraper is safe to run multiple times — duplicate events are upserted rather than duplicated.

## Providers Covered

| Provider | LL2 Filter (`lsp__name`) |
|----------|--------------------------|
| SpaceX | `SpaceX` |
| Rocket Lab | `Rocket Lab USA` |

## Configuration

All settings inherit from `openorbit.config.Settings` (set via environment variables or `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SCRAPER_DELAY_SECONDS` | `2` | Delay (seconds) between provider requests to avoid rate limiting |
| `SCRAPER_TIMEOUT_SECONDS` | `30` | HTTP request timeout per attempt |
| `SCRAPER_MAX_RETRIES` | `3` | Maximum retry attempts with exponential backoff on transient errors |
| `DATABASE_URL` | `sqlite+aiosqlite:///./openorbit.db` | Database connection string |

## How It Works

1. For each provider, the scraper builds an LL2 API URL filtered by `lsp__name`.
2. It fetches upcoming launches with retry/backoff logic.
3. Each raw LL2 launch dict is mapped to the pipeline format and passed through `normalize()`.
4. Valid events are upserted to `launch_events`; attributions link each event to the scrape record.
5. `SCRAPER_DELAY_SECONDS` is applied between providers (not after the last one).

### Status Mapping

| LL2 Status | openOrbit Status |
|------------|-----------------|
| `Go for Launch`, `Go`, `TBD`, `TBC`, `In Flight`, `Hold` | `scheduled` |
| `Success` | `launched` |
| `Failure`, `Partial Failure` | `failed` |

### Precision Mapping

| LL2 Net Precision | openOrbit Precision |
|-------------------|---------------------|
| `Second`, `Minute` | `second` |
| `Hour`, `Day` | `day` |
| `Week` | `day` |
| `Month`, `Year` | `month` |

## API Reference

### `CommercialLaunchScraper.scrape() -> list[dict]`

Scrapes all configured providers and returns a list of summary dicts:

```python
[
  {
    "provider": "SpaceX",
    "total_fetched": 12,
    "new_events": 3,
    "updated_events": 9
  },
  ...
]
```

### `CommercialLaunchScraper.parse(raw_data: str, source_name: str) -> list[LaunchEventCreate]`

Parses raw LL2 JSON into `LaunchEventCreate` models. Malformed events are logged and skipped — they do not abort the batch.

## Running Standalone

```bash
cd project

# Run the scraper as a module
uv run python -m openorbit.scrapers.commercial
```

Output:
```
=== Commercial Launch Providers Scrape Summary ===
  SpaceX: 12 fetched, 3 new, 9 updated
  Rocket Lab: 5 fetched, 1 new, 4 updated
==================================================
```

### Programmatic Usage

```python
import asyncio
from openorbit.scrapers.commercial import CommercialLaunchScraper
from openorbit.db import init_db

async def run():
    await init_db()
    scraper = CommercialLaunchScraper()
    summaries = await scraper.scrape()
    for s in summaries:
        print(s)

asyncio.run(run())
```
