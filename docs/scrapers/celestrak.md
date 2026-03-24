# CelesTrak Scraper

## Overview

`CelesTrakScraper` (`openorbit.scrapers.celestrak`) ingests public, non-credentialed launch-related object data from CelesTrak:

- Endpoint: `https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=json`
- Access: no API key required
- Focus: recently launched catalog objects (last 30 days)

The scraper groups object-level rows into launch-level events using `OBJECT_ID` launch designators (e.g., `2026-001A` + `2026-001B` -> launch `2026-001`).

## Why This Source

- Officially recognized space situational awareness ecosystem source
- Publicly reachable without credentials
- Useful corroboration layer for recently completed launches

## Data Handling

1. Fetch JSON list from CelesTrak GP endpoint
2. Parse object rows (`OBJECT_ID`, `OBJECT_NAME`, `LAUNCH_DATE`, `OWNER`, `SITE`)
3. Aggregate rows to launch-level keys
4. Upsert launch events and add attribution links

## Mapping to openOrbit Model

| CelesTrak Field | openOrbit Field |
|-----------------|-----------------|
| `OBJECT_ID` launch core | `slug` (prefixed `celestrak-`) |
| `LAUNCH_DATE` | `launch_date` (`day` precision) |
| `OWNER` | `provider` |
| `SITE` | `location` |
| object count per launch | included in event `name` |

Default classification:
- `launch_type = "unknown"`
- `status = "launched"`

## Usage

```bash
cd project
uv run python -m openorbit.scrapers.celestrak
```

Example output:

```text
=== CelesTrak Scrape Summary ===
Total events fetched: 6
New events created: 2
Existing events updated: 4
=================================
```

## Notes

- This feed is launch-object oriented and recent-window scoped (last 30 days).
- It complements upcoming-schedule feeds (e.g., official mission calendars, SpaceX API).
