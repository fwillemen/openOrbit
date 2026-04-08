# 4chan Imageboard Scraper

## Overview

`FourChanScraper` (`openorbit.scrapers.fourchan`) scans the **public 4chan JSON API**
for launch-related threads on curated boards (primarily `/sci/`). No authentication
or credentials are required — all requests use 4chan's public read-only API.

Threads are ingested as **Tier 3 (Analytical/Speculative)** signals and stored with
`claim_lifecycle='rumor'` until corroborated by higher-tier evidence.

Image URLs from thread opening posts (OPs) are captured in the `image_urls` field
using 4chan's CDN URL format (`https://i.4cdn.org/{board}/{tim}{ext}`).

---

## Class Hierarchy

```
BaseScraper
└── FourChanScraper          (openorbit.scrapers.fourchan)
```

---

## Endpoints

| Purpose | URL Pattern |
|---------|-------------|
| Board catalog | `https://a.4cdn.org/{board}/catalog.json` |

The catalog endpoint returns all active threads on a board, grouped by page.
See the [4chan API documentation](https://github.com/4chan/4chan-API) for details.

---

## Configuration

### Tracked Boards

| Board | Focus |
|-------|-------|
| `/sci/` | Science & Math — frequently has space launch discussion threads |

### Launch Keywords

Threads are filtered to those containing at least one keyword in their
subject (`sub`) or comment text (`com`):

```
launch, liftoff, rocket, satellite, spacecraft, mission, orbit,
spacex, nasa, starship, falcon
```

### Thread Limit

Up to **25 threads** are fetched per board (configurable via `MAX_THREADS_PER_BOARD`).

---

## Image URL Extraction

4chan is an imageboard — most threads have images attached to the opening post.
The scraper captures OP images using the 4chan CDN format:

```
https://i.4cdn.org/{board}/{tim}{ext}
```

Where `tim` is the Unix timestamp filename and `ext` is the file extension
(`.jpg`, `.png`, `.gif`, `.webp`).

Only the OP image is captured from the catalog; reply images require fetching
the full thread JSON, which is not done to minimize API load.

---

## OSINT Classification

All events produced by `FourChanScraper` carry the following fixed metadata:

| Field | Value | Meaning |
|-------|-------|---------|
| `source_tier` | `3` | Analytical/speculative — imageboard, not official or regulatory |
| `evidence_type` | `media` | Social post as evidence |
| `claim_lifecycle` | `rumor` | Unverified social signal; requires corroboration to advance |
| `event_kind` | `inferred` | Assembled from social signals, not direct operator data |

---

## How Threads Become Events

1. **Collect** — The scraper fetches the thread catalog for each tracked board.
2. **Deduplicate** — Threads are deduplicated by `/{board}/{thread_no}`.
3. **Filter** — Only threads whose subject + comment contains at least one launch keyword.
4. **Parse** — Each thread is mapped to a `LaunchEventCreate` model:
   - `name` — thread subject (falls back to first 120 chars of comment)
   - `launch_date` — thread creation timestamp (`time`)
   - `launch_date_precision` — `"day"`
   - `provider` — `4chan//{board}/` (e.g. `4chan//sci/`)
   - `image_urls` — OP image URL if present
   - `vehicle`, `location`, `pad` — `None`
   - `claim_lifecycle` — `"rumor"`
   - `event_kind` — `"inferred"`
5. **Upsert** — Events are written to `launch_events` and an attribution record is added.

---

## Slug Generation

Each event is assigned a deterministic slug derived from board + thread number:

```
4chan-<12-char SHA-1 hex of "4chan|/{board}/{thread_no}">
```

Re-scraping the same thread always produces the same slug, enabling safe upserts.

---

## Usage

```bash
# Run the 4chan scraper directly
uv run python -m openorbit scrape 4chan
```

The scraper is also invoked automatically when running all scrapers:

```bash
uv run python -m openorbit scrape all
```

---

## Applicability to 2chan / Other Imageboards

The 4chan scraper pattern can be adapted for other imageboards (2chan/futaba, 8kun, etc.)
with minimal changes:

- **2chan (futaba channel)** — Similar thread/catalog structure but different API format.
  Would require a new parser but the same `BaseScraper` plugin pattern applies.
- **Other imageboards** — Any board with a JSON API can be scraped by subclassing
  `BaseScraper` and implementing `scrape()` and `parse()`.

---

## Limitations

- **OP-only images** — Only the opening post image is captured from the catalog.
  Reply images require a full thread fetch.
- **Ephemeral content** — 4chan threads expire and are pruned. The `refresh_interval_hours`
  of 2 ensures timely capture but very short-lived threads may be missed.
- **Tier 3 only** — Imageboard posts are speculative until corroborated.
- **Single board** — Only `/sci/` is tracked by default. Additional boards can be added
  to the `BOARDS` tuple but may introduce noise.
- **No authentication** — 4chan's API is fully public. Rate limiting is server-side.
- **HTML content** — Thread comments contain HTML markup (greentext, quote links, etc.)
  which is stripped to plain text for keyword matching.
