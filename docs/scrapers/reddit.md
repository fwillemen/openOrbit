# Reddit Scraper

## Overview

`RedditScraper` (`openorbit.scrapers.reddit`) queries the **public Reddit JSON API**
for launch-related posts from curated space subreddits. No authentication or credentials
are required — all requests use Reddit's unauthenticated `.json` endpoint suffix.

Posts are ingested as **Tier 3 (Analytical/Speculative)** signals and stored with
`claim_lifecycle='rumor'` until corroborated by higher-tier evidence.

Image URLs from direct image links, Reddit galleries, and preview images are captured
in the `image_urls` field for downstream analysis.

---

## Class Hierarchy

```
BaseScraper
└── RedditScraper          (openorbit.scrapers.reddit)
```

---

## Endpoints

| Purpose | URL Pattern |
|---------|-------------|
| Subreddit new posts | `https://www.reddit.com/r/{subreddit}/new.json?limit=25&raw_json=1` |

All endpoints are public and require no API key or login.

---

## Configuration

### Tracked Subreddits

The scraper fetches recent posts from the following subreddits:

| Subreddit | Focus |
|-----------|-------|
| `r/spacex` | SpaceX launches and operations |
| `r/spaceflight` | General spaceflight discussion |
| `r/ula` | United Launch Alliance |
| `r/rocketlab` | Rocket Lab launches |
| `r/nasa` | NASA missions and launches |
| `r/space` | General space discussion |

### Launch Keywords

Posts are filtered to those containing at least one keyword:

```
launch, liftoff, rocket, satellite, spacecraft, mission, orbit
```

---

## Image URL Extraction

Reddit posts may contain images in several formats. The scraper extracts image URLs from:

1. **Direct image links** — URLs ending in `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`
   (e.g., `https://i.redd.it/abc123.jpg`)
2. **Post hint** — Posts with `post_hint: "image"` and a direct URL
3. **Reddit galleries** — `media_metadata` dict with `status: "valid"` entries
4. **Preview images** — `preview.images[].source.url` from Reddit's image proxy

All extracted URLs are stored in the `image_urls` field of the `LaunchEventCreate` model
and persisted in the `launch_events.image_urls` column as a JSON array.

---

## OSINT Classification

All events produced by `RedditScraper` carry the following fixed metadata:

| Field | Value | Meaning |
|-------|-------|---------|
| `source_tier` | `3` | Analytical/speculative — social media, not official or regulatory |
| `evidence_type` | `media` | Social post as evidence |
| `claim_lifecycle` | `rumor` | Unverified social signal; requires corroboration to advance |
| `event_kind` | `inferred` | Assembled from social signals, not direct operator data |

---

## How Posts Become Events

1. **Collect** — The scraper fetches recent posts from each tracked subreddit.
2. **Deduplicate** — Posts are deduplicated by their permalink.
3. **Filter** — Only posts whose title + selftext contains at least one launch keyword are retained.
4. **Parse** — Each post is mapped to a `LaunchEventCreate` model:
   - `name` — first 120 characters of the post title (Markdown stripped)
   - `launch_date` — post `created_utc` timestamp
   - `launch_date_precision` — `"day"`
   - `provider` — `u/{author}` (Reddit username)
   - `image_urls` — extracted from post URL, gallery, or preview
   - `vehicle`, `location`, `pad` — `None` (not reliably inferable from social posts)
   - `claim_lifecycle` — `"rumor"`
   - `event_kind` — `"inferred"`
5. **Upsert** — Events are written to `launch_events` and an attribution record is added.

---

## Slug Generation

Each event is assigned a deterministic slug derived from its permalink:

```
reddit-<12-char SHA-1 hex of "reddit|{permalink}">
```

Re-scraping the same post always produces the same slug, enabling safe upserts.

---

## Usage

```bash
# Run the Reddit scraper directly
uv run python -m openorbit scrape reddit
```

The scraper is also invoked automatically when running all scrapers:

```bash
uv run python -m openorbit scrape all
```

---

## Limitations

- **No authentication** — Uses Reddit's public JSON API which has stricter rate limits than
  the authenticated OAuth2 API. The `User-Agent` header is set to identify the scraper.
- **Tier 3 only** — Reddit posts are speculative until corroborated by Tier 1/2 sources.
- **Title-only filtering** — Only post titles and selftext are checked for launch keywords;
  comments are not scraped.
- **No comment threads** — Only top-level posts are fetched, not threaded discussions.
- **Subreddit-level** — Individual user monitoring is possible by adding subreddits or
  extending the scraper to use Reddit's user endpoint (`/user/{name}/submitted.json`).
