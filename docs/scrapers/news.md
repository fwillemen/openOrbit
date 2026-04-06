# Tier 3 News RSS Scrapers

## Overview

`NewsRSSScraper` (`openorbit.scrapers.news`) is an abstract base class that extends
`PublicFeedScraper` to ingest launch-related news articles from RSS/Atom feeds and
integrate them into the openOrbit OSINT pipeline as **Tier 3 (Analytical)** signals.

Two concrete scrapers are provided out of the box:

| Class | Source Name | Feed URL |
|-------|-------------|----------|
| `SpaceFlightNowScraper` | SpaceFlightNow RSS | https://spaceflightnow.com/feed/ |
| `NASASpaceflightScraper` | NASASpaceflight RSS | https://www.nasaspaceflight.com/feed/ |

Both scrapers are **auto-registered** via `ScraperRegistry` — no manual wiring required.

---

## Class Hierarchy

```
PublicFeedScraper
└── NewsRSSScraper          (abstract — source_tier=3, evidence_type='media')
    ├── SpaceFlightNowScraper
    └── NASASpaceflightScraper
```

---

## OSINT Classification

All events produced by `NewsRSSScraper` subclasses carry the following fixed metadata:

| Field | Value | Reason |
|-------|-------|--------|
| `source_tier` | `3` | Analytical/speculative — not official or regulatory |
| `evidence_type` | `media` | News articles as evidence |
| `claim_lifecycle` | `rumor` | Default for unverified news mentions |
| `event_kind` | `inferred` | Derived from article content, not direct operator data |

---

## Keyword Filtering

Articles are pre-screened with the following keywords before any parsing:

```
launch, liftoff, rocket, satellite, spacecraft, mission, orbit, countdown
```

Articles not containing at least one of these keywords are skipped.

---

## Fuzzy Entity Linking

Before creating a new event, each article is compared against existing events in the database
using a **provider + date ± 1 day** match strategy:

```
for each parsed article:
    if provider matches AND launch_date within ±1 day of existing event:
        → add attribution to existing event only (no new event)
    else:
        → upsert new launch event with claim_lifecycle='rumor'
        → add attribution linking article to the new event
```

This prevents duplicate events when the same launch is covered by multiple news outlets
or appears in both RSS feeds.

**Match criteria:**
- `provider` — case-insensitive equality
- `launch_date` — within `±1 day` (`timedelta(days=1)`)

---

## Usage

### Standalone (module)

```bash
cd project

# Run SpaceFlightNow scraper
uv run python -m openorbit.scrapers.news SpaceFlightNow

# Run NASASpaceflight scraper
uv run python -m openorbit.scrapers.news NASASpaceflight
```

Example output:
```
=== SpaceFlightNow RSS Scrape Summary ===
Total articles fetched: 18
New rumor events created: 4
Existing events linked: 14
=========================================
```

### Programmatic

```python
import asyncio
from openorbit.scrapers.news import SpaceFlightNowScraper, NASASpaceflightScraper
from openorbit.db import init_db

async def run() -> None:
    await init_db()
    for scraper_cls in (SpaceFlightNowScraper, NASASpaceflightScraper):
        scraper = scraper_cls()
        result = await scraper.scrape()
        print(result)

asyncio.run(run())
```

---

## Scrape Result Shape

`scrape()` returns a `dict[str, int]` summary:

| Key | Description |
|-----|-------------|
| `total_fetched` | Articles parsed from the RSS feed |
| `new_events` | New `claim_lifecycle='rumor'` events upserted |
| `updated_events` | Existing events that received a new attribution |

---

## Lifecycle Promotion

News RSS events start at `claim_lifecycle='rumor'`. Promotion to higher confidence states
requires corroboration from Tier 1 or Tier 2 sources:

```
rumor (Tier 3 only)
  → indicated   (single Tier 1/2 source added)
  → corroborated (multiple independent sources)
  → confirmed   (official operator confirmation)
```

---

## Configuration

Inherits all settings from `openorbit.config.Settings`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SCRAPER_TIMEOUT_SECONDS` | `30` | HTTP request timeout per attempt |
| `SCRAPER_MAX_RETRIES` | `3` | Maximum retry attempts with exponential backoff |
| `DATABASE_URL` | `sqlite+aiosqlite:///./openorbit.db` | Database connection string |

---

## Adding a New RSS Source

Subclass `NewsRSSScraper` and set the required class variables:

```python
from typing import ClassVar
from openorbit.scrapers.news import NewsRSSScraper

class MyNewsScraper(NewsRSSScraper):
    source_name: ClassVar[str] = "news_mysite"
    source_url: ClassVar[str] = "https://example.com/feed/"
    SOURCE_NAME: ClassVar[str] = "My News Site RSS"
    PROVIDER_NAME: ClassVar[str] = "My News Site"

    @classmethod
    def feed_region(cls) -> str:
        return "global"
```

The scraper is auto-registered and will be included in the next scheduled scrape cycle.
