# Mastodon Social Scraper

## Overview

`MastodonScraper` (`openorbit.scrapers.mastodon`) queries **public Mastodon hashtag timeline
endpoints** for launch-related posts. No authentication or credentials are required — all
requests use Mastodon's unauthenticated public API.

Posts are ingested as **Tier 3 (Analytical/Speculative)** signals and stored with
`claim_lifecycle='rumor'` until corroborated by higher-tier evidence.

---

## Class Hierarchy

```
BaseScraper
└── MastodonScraper          (openorbit.scrapers.mastodon)
```

---

## Endpoint

| Purpose | URL |
|---------|-----|
| Hashtag timeline | `https://{instance}/api/v1/timelines/tag/{hashtag}?limit=40` |

The endpoint is public and requires no API key or login. The instance hostname is
[configurable via environment variable](#configuration).

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MASTODON_INSTANCE` | `mastodon.social` | Mastodon instance hostname to query |

Override the instance at runtime:

```bash
MASTODON_INSTANCE=fosstodon.org uv run python -m openorbit scrape mastodon
```

### Hashtags Monitored

The scraper fetches the timeline for each of the following hashtags:

| Hashtag | Purpose |
|---------|---------|
| `#spacelaunch` | General launch discussion |
| `#spacex` | SpaceX missions and updates |
| `#nasa` | NASA missions and announcements |
| `#rocket` | Broad rocket discussion |
| `#satellite` | Satellite deployment discussion |

Each hashtag triggers independent timeline requests (with pagination).

---

## Pagination

The scraper follows Mastodon's standard **Link-header pagination**:

- Each request fetches **40 statuses** (`limit=40`).
- After each successful page, the `Link: <url>; rel="next"` header is parsed to
  obtain the next page URL.
- A maximum of **2 pages per hashtag** is fetched per scrape run.
- If no `rel="next"` link is present, pagination stops early.

Maximum statuses retrieved per run: `5 hashtags × 2 pages × 40 posts = 400 statuses`
(before deduplication and keyword filtering).

---

## OSINT Classification

All events produced by `MastodonScraper` carry the following fixed metadata:

| Field | Value | Meaning |
|-------|-------|---------|
| `source_tier` | `3` | Analytical/speculative — social media, not official or regulatory |
| `evidence_type` | `media` | Social post as evidence |
| `claim_lifecycle` | `rumor` | Unverified social signal; requires corroboration to advance |
| `event_kind` | `inferred` | Assembled from social signals, not direct operator data |
| `refresh_interval_hours` | `2` | How often the scraper should be re-run |

To advance a `rumor` claim toward `indicated` or `confirmed`, it must be corroborated
by Tier 1 or Tier 2 sources (e.g., an official agency schedule or a NOTAM).

---

## Launch-Relevance Filtering

After deduplication by status URL, posts are filtered to those whose plain-text content
contains at least one of the following keywords (case-insensitive):

```
launch, liftoff, rocket, satellite, spacecraft, mission, orbit
```

Posts that do not match any keyword are discarded before database ingestion.

---

## How Posts Become Events

1. **Collect** — Fetches up to 2 pages of 40 statuses per hashtag from the configured instance.
2. **Deduplicate** — Posts are deduplicated by their unique status URL.
3. **Filter** — Only posts whose text contains at least one launch keyword are retained.
4. **Parse** — Each post is mapped to a `LaunchEventCreate` model:
   - `name` — first 120 characters of the post plain text (HTML stripped)
   - `launch_date` — post `created_at` timestamp (falls back to current time)
   - `launch_date_precision` — `"day"`
   - `provider` — author account handle (e.g., `nasaspaceflight@mastodon.social`)
   - `vehicle`, `location`, `pad` — `None` (not reliably inferable from social posts)
   - `claim_lifecycle` — `"rumor"`
   - `event_kind` — `"inferred"`
5. **Upsert** — Events are written to `launch_events` and an attribution record is added
   to `event_attributions` linking back to the scrape run and source.

---

## Slug Generation

Each event is assigned a deterministic slug derived from its Mastodon status URL:

```
mastodon-<12-char SHA-1 hex of "mastodon|{url}">
```

Re-scraping the same post always produces the same slug, enabling safe upserts.

---

## Usage

```bash
# Run the Mastodon scraper directly
uv run python -m openorbit scrape mastodon
```

The scraper is also invoked automatically when running all scrapers:

```bash
uv run python -m openorbit scrape all
```

---

## Limitations

- **No full-text context** — post text is short; vehicle and pad cannot be reliably extracted.
- **Tier 3 only** — social posts are speculative until corroborated by Tier 1/2 sources.
- **Instance-specific** — only one Mastodon instance is queried per run; posts on other instances
  are not collected unless `MASTODON_INSTANCE` is changed.
- **Federated reach** — federated timelines vary by instance; the same hashtag may surface
  different posts depending on which instance is queried.
- **No authentication** — private or followers-only posts are never visible.
