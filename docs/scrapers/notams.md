# FAA NOTAM Scraper

## Overview

`NotamScraper` (`openorbit.scrapers.notams`) fetches airspace Notices to Air Missions (NOTAMs) from the [FAA public NOTAM API](https://external-api.faa.gov/notamapi/v1/notams) and filters them for launch-related content using `notam_parser`. Matched NOTAMs are converted to `LaunchEventCreate` models and upserted into the database under the source name **"FAA NOTAM Database"**.

The scraper currently targets the Jacksonville ARTCC (`KZJX`) — an area encompassing Florida's Space Coast — and is designed to be extended to additional ARTCC regions.

## `notam_parser.py` — Keyword Classification

`openorbit.pipeline.notam_parser` is a pure-Python, side-effect-free module that classifies NOTAM text and extracts structured fields.

### Keyword Classification Rules

Classification follows a **priority-ordered** list of rules — the first matching keyword wins:

| Priority | Keyword | Matched Type |
|----------|---------|--------------|
| 1 (highest) | `MISSILE` | `military` |
| 2 | `SPACE LAUNCH` | `civilian` |
| 3 | `ROCKET` | `civilian` |
| 4 | `RANGE CLOSURE` | `unknown` |
| 5 | `SPACE VEHICLE` | `civilian` |
| 6 | `JATO` | `civilian` |

**MISSILE takes highest priority**: a NOTAM containing both `ROCKET` and `MISSILE` is classified as `military`.

All keywords are matched case-insensitively with word-boundary anchors (`\b`).

### `parse_notam(text: str) -> NotamMatch`

```python
from openorbit.pipeline.notam_parser import parse_notam

result = parse_notam("ROCKET LAUNCH AREA ACTIVE 2200-0200Z")
# result.is_launch_related == True
# result.launch_type == "civilian"
# result.matched_keywords == ["ROCKET"]
```

`NotamMatch` fields:

| Field | Type | Description |
|-------|------|-------------|
| `is_launch_related` | bool | `True` if any launch keyword matched |
| `launch_type` | `civilian` \| `military` \| `unknown` | Determined by highest-priority keyword |
| `matched_keywords` | list[str] | All keywords found in the text (uppercased) |
| `raw_text` | str | Original NOTAM text passed to the parser |

### Launch Type Inference Logic

```
NOTAM text
    │
    ▼  (scan in priority order)
    ├─ contains MISSILE?        → military
    ├─ contains SPACE LAUNCH?   → civilian
    ├─ contains ROCKET?         → civilian
    ├─ contains RANGE CLOSURE?  → unknown
    ├─ contains SPACE VEHICLE?  → civilian
    └─ contains JATO?           → civilian
         └─ no match            → not launch-related (skipped)
```

### Coordinate & Validity Parsing

| Function | Description |
|----------|-------------|
| `parse_q_line(q_line)` | Extracts `lat`/`lon` floats from a NOTAM Q-line (format: `3030N08145W`) |
| `parse_validity(b_line, c_line)` | Parses `YYMMDDHHMM` validity window; handles `PERM` end date |
| `extract_launch_candidates(notams)` | Runs full pipeline on a list of FAA API NOTAM dicts; returns `LaunchEventCreate` list |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SCRAPER_DELAY_SECONDS` | `2` | Delay before the first fetch (respects shared rate-limit budget) |
| `SCRAPER_TIMEOUT_SECONDS` | `30` | HTTP request timeout |
| `SCRAPER_MAX_RETRIES` | `3` | Retry attempts with exponential backoff |

> **Note:** The FAA NOTAM API returns `401`/`403` when credentials are required. If you receive these codes, set the `FAA_API_KEY` environment variable and pass it in the `Authorization` header. The scraper logs a clear warning and exits without retrying on auth errors.

## Running Standalone

```bash
cd project

# Run the NOTAM scraper as a module
uv run python -m openorbit.scrapers.notams
```

Output:
```
=== FAA NOTAM Scrape Summary ===
Total launch events found: 4
New events created: 2
Existing events updated: 2
===================================
```

### Programmatic Usage

```python
import asyncio
from openorbit.scrapers.notams import NotamScraper
from openorbit.db import init_db

async def run():
    await init_db()
    scraper = NotamScraper()
    result = await scraper.scrape()
    print(result)
    # {'total_fetched': 4, 'new_events': 2, 'updated_events': 2}

asyncio.run(run())
```

### Using the Parser Directly

```python
from openorbit.pipeline.notam_parser import parse_notam, extract_launch_candidates

# Single NOTAM classification
match = parse_notam("MISSILE LAUNCH AREA ACTIVE 1800Z-2200Z")
assert match.launch_type == "military"

# Batch processing of raw FAA API items
events = extract_launch_candidates(faa_notam_items)
```
