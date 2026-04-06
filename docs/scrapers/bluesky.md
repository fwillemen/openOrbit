# Bluesky Social Scraper

## Overview

`BlueskyScraper` (`openorbit.scrapers.bluesky`) queries the **public Bluesky AT Protocol API**
for launch-related posts and feeds from curated space accounts. No authentication or credentials
are required — all requests use Bluesky's unauthenticated public endpoints.

Posts are ingested as **Tier 3 (Analytical/Speculative)** signals and stored with
`claim_lifecycle='rumor'` until corroborated by higher-tier evidence.

---

## Class Hierarchy

```
BaseScraper
└── BlueskyScraper          (openorbit.scrapers.bluesky)
```

---

## Endpoints

| Purpose | URL |
|---------|-----|
| Keyword search | `https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q={term}&limit=25` |
| Account feed | `https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor={handle}&limit=25` |

Both endpoints are public and require no API key or login.

---

## Configuration

### Search Terms

The scraper searches for posts matching any of the following keywords:

```
launch, liftoff, rocket, satellite, spacecraft
```

Each term triggers a separate API request returning up to 25 posts.

### Tracked Accounts

In addition to keyword search, the scraper fetches the full recent feed
(up to 25 posts) for each of the following handles:

| Handle | Organisation |
|--------|-------------|
| `nasa.gov` | NASA |
| `spacex.com` | SpaceX |
| `nasaspaceflight.com` | NASASpaceflight (media) |
| `spaceflightnow.com` | Spaceflight Now (media) |
| `esa.int` | European Space Agency |

---

## Rate Limiting

A **3-second pause** is enforced between every HTTP request (both search and feed requests).
This prevents hitting Bluesky's public rate limits and keeps the scraper polite.

With 5 search terms + 5 tracked accounts = 10 requests total per scrape run,
a full scrape cycle takes approximately **30 seconds**.

The scraper is configured with a `refresh_interval_hours` of **2 hours**.

---

## OSINT Classification

All events produced by `BlueskyScraper` carry the following fixed metadata:

| Field | Value | Meaning |
|-------|-------|---------|
| `source_tier` | `3` | Analytical/speculative — social media, not official or regulatory |
| `evidence_type` | `media` | Social post as evidence |
| `claim_lifecycle` | `rumor` | Unverified social signal; requires corroboration to advance |
| `event_kind` | `inferred` | Assembled from social signals, not direct operator data |

To advance a `rumor` claim toward `indicated` or `confirmed`, it must be corroborated
by Tier 1 or Tier 2 sources (e.g., an official agency schedule or a NOTAM).

---

## How Posts Become Events

1. **Collect** — The scraper fetches posts matching each search term and each tracked account feed.
2. **Deduplicate** — Posts are deduplicated by their unique AT Protocol URI.
3. **Filter** — Only posts whose text contains at least one launch keyword are retained.
4. **Parse** — Each post is mapped to a `LaunchEventCreate` model:
   - `name` — first 120 characters of the post text
   - `launch_date` — post `createdAt` timestamp (falls back to `indexedAt`)
   - `launch_date_precision` — `"day"`
   - `provider` — author handle (e.g., `nasa.gov`)
   - `vehicle`, `location`, `pad` — `None` (not inferable from social posts)
   - `claim_lifecycle` — `"rumor"`
   - `event_kind` — `"inferred"`
5. **Upsert** — Events are written to `launch_events` and an attribution record is added
   to `event_attributions` linking back to the scrape run and source.

---

## Slug Generation

Each event is assigned a deterministic slug derived from its AT Protocol URI:

```
bluesky-<12-char SHA-1 hex of "bluesky|{uri}">
```

Re-scraping the same post always produces the same slug, enabling safe upserts.

---

## Usage

```bash
# Run the Bluesky scraper directly
uv run python -m openorbit scrape bluesky
```

The scraper is also invoked automatically when running all scrapers:

```bash
uv run python -m openorbit scrape all
```

---

## Limitations

- **No full-text context** — post text is short; vehicle and pad cannot be reliably extracted.
- **Tier 3 only** — social posts are speculative until corroborated by Tier 1/2 sources.
- **Public API rate limits** — aggressive polling may result in temporary throttling by Bluesky.
- **Account handle changes** — tracked handles may become stale if accounts migrate or rename.
