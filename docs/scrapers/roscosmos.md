# Roscosmos Official Feed Scraper

## Overview

The `RoscosmosOfficialScraper` ingests launch announcements and mission
updates from the **Roscosmos** (Russian Federal Space Agency) English-language
public RSS feed.

| Property | Value |
|---|---|
| Source name | `roscosmos_official` |
| Feed URL | `https://www.roscosmos.ru/eng/rss.xml` |
| Source tier | **1** (Official / Regulatory) |
| Evidence type | `official_schedule` |
| Claim lifecycle | `confirmed` |
| Event kind | `observed` |

## Data Source

Roscosmos publishes mission news and launch campaign updates through an
official English-language RSS feed.  Items include launch windows, rocket
readiness reports, spacecraft separations, and docking events.

## Vehicle Normalisation

| Feed keyword | Normalised vehicle name |
|---|---|
| `soyuz-2.1b` | `Soyuz-2.1b` |
| `soyuz-2.1a` | `Soyuz-2.1a` |
| `soyuz-2` | `Soyuz-2` |
| `soyuz` | `Soyuz` |
| `angara-a5` | `Angara-A5` |
| `angara` | `Angara` |
| `proton-m` | `Proton-M` |
| `proton` | `Proton` |

## Location Normalisation

| Feed keyword | Normalised location |
|---|---|
| `baikonur` | `Baikonur Cosmodrome, Kazakhstan` |
| `plesetsk` | `Plesetsk Cosmodrome, Russia` |
| `vostochny` | `Vostochny Cosmodrome, Russia` |
| `vostochni` | `Vostochny Cosmodrome, Russia` |

## Keyword Filtering

Items are included when at least one of the following keywords appears in the
title or description (case-insensitive):

`launch`, `soyuz`, `proton`, `angara`, `rocket`, `satellite`, `spacecraft`,
`liftoff`, `cosmodrome`

Standard exclusion keywords (`internship`, `conference`, `workshop`, etc.) are
applied by the `PublicFeedScraper` base class.

## Implementation Notes

- Extends `PublicFeedScraper` — no credentials required.
- Reuses the standard RSS/Atom XML parser; supports both RSS 2.0 and Atom 1.0.
- Slug is deterministically derived from `source_name + feed_link + title`,
  ensuring idempotent upserts on repeated scrapes.

## Running Manually

```bash
python -m openorbit.scrapers.roscosmos_official
```
