# openOrbit — Usage Examples

Practical OSINT workflows using the openOrbit API.
All examples use `curl` with [`jq`](https://jqlang.github.io/jq/) for output formatting.
A Python section at the end shows how to use the API from code.

> **Prerequisites:** Server running at `http://localhost:8000`. See [Quick Start](quickstart.md).
>
> **Note:** All GET endpoints are public — no API key needed. The database is seeded by the
> background scheduler on first startup (scrapers run automatically every 6 hours). You can also
> trigger a manual refresh with `POST /v1/admin/sources/{id}/refresh` (requires admin key).
>
> **Data notes for current single-source setup:**
> - With only Launch Library 2 seeded, events have `claim_lifecycle: "indicated"` and
>   `result_tier: "tracked"` or `"emerging"` (no `verified` tier yet — that needs ≥2 attributions).
> - Proximity search (`location=lat,lon`) only matches events that store coordinates in their
>   `location` field. Launch Library 2 stores text names, not coordinates, so proximity returns
>   empty results until multi-source scrapers populate geo-tagged events.

---

## Table of Contents

1. [Browse upcoming launches](#1-browse-upcoming-launches)
2. [Filter by provider or type](#2-filter-by-provider-or-type)
3. [Filter by confidence and result tier](#3-filter-by-confidence-and-result-tier)
4. [Search with full-text queries](#4-search-with-full-text-queries)
5. [Filter by claim lifecycle](#5-filter-by-claim-lifecycle)
6. [Find launches near a launch site](#6-find-launches-near-a-launch-site)
7. [Retrieve evidence and provenance](#7-retrieve-evidence-and-provenance)
8. [Paginate through large result sets](#8-paginate-through-large-result-sets)
9. [Check active OSINT sources](#9-check-active-osint-sources)
10. [Admin: stats and manual refresh](#10-admin-stats-and-manual-refresh)
11. [Python examples](#11-python-examples)

---

## 1. Browse Upcoming Launches

```bash
# All launches (first page, 25 results)
curl -s http://localhost:8000/v1/launches | jq .

# Launches in a date range
curl -s "http://localhost:8000/v1/launches?from=2026-01-01T00:00:00Z&to=2026-12-31T23:59:59Z" | jq .

# Only scheduled launches — print name, provider, date
curl -s "http://localhost:8000/v1/launches?status=scheduled" \
  | jq '.data[] | {slug, name, provider, launch_date, confidence_score}'
```

**Response shape:**

```json
{
  "data": [
    {
      "id": 42,
      "slug": "falcon-9-starlink-6-32-2026-03-15",
      "name": "Falcon 9 | Starlink Group 6-32",
      "launch_date": "2026-03-15T14:30:00Z",
      "launch_date_precision": "hour",
      "provider": "SpaceX",
      "vehicle": "Falcon 9",
      "location": "28.573,-80.649",
      "pad": "LC-39A, Kennedy Space Center",
      "status": "scheduled",
      "launch_type": "civilian",
      "confidence_score": 87.5,
      "result_tier": "verified",
      "evidence_count": 3,
      "claim_lifecycle": "confirmed",
      "event_kind": "observed",
      "inference_flags": [],
      "sources": [
        {
          "name": "space_agency",
          "url": "https://ll.thespacedevs.com/...",
          "scraped_at": "2026-03-10T08:00:00Z"
        }
      ],
      "evidence_url": "http://localhost:8000/v1/launches/falcon-9-starlink-6-32-2026-03-15/evidence",
      "created_at": "2026-03-10T08:00:00Z",
      "updated_at": "2026-03-12T14:00:00Z"
    }
  ],
  "meta": {
    "total": 84,
    "page": 1,
    "per_page": 25,
    "next_cursor": null
  }
}
```

---

## 2. Filter by Provider or Type

```bash
# All SpaceX launches (case-insensitive substring match on provider field)
curl -s "http://localhost:8000/v1/launches?provider=SpaceX" \
  | jq '.data[] | {name, status, launch_date}'

# Military launches only
curl -s "http://localhost:8000/v1/launches?launch_type=military" \
  | jq '.data[] | {name, provider, launch_type, result_tier}'

# Scheduled SpaceX launches — combine filters
curl -s "http://localhost:8000/v1/launches?provider=SpaceX&status=scheduled" \
  | jq '.meta.total'

# Count by status — run four quick queries
for STATUS in scheduled delayed launched failed cancelled; do
  COUNT=$(curl -s "http://localhost:8000/v1/launches?status=$STATUS" | jq '.meta.total')
  echo "$STATUS: $COUNT"
done
```

---

## 3. Filter by Confidence and Result Tier

Each event is classified into one of three result tiers:

| Tier | Condition |
|------|-----------|
| `verified` | confidence ≥ 80 **and** ≥ 2 attributions |
| `tracked` | confidence ≥ 60 |
| `emerging` | everything else |

```bash
# Only well-corroborated, high-confidence events
# (requires ≥2 attributions from different sources — may be empty with single-source setup)
curl -s "http://localhost:8000/v1/launches?result_tier=verified" \
  | jq '.data[] | {name, confidence_score, evidence_count}'

# Events with at least 70% confidence (tracked tier or above)
curl -s "http://localhost:8000/v1/launches?min_confidence=70" \
  | jq '.data[] | {name, confidence_score, result_tier}'

# Tracked tier — solid signal from at least one Tier 1/2 source
curl -s "http://localhost:8000/v1/launches?result_tier=tracked&status=scheduled" \
  | jq '.data[] | {name, claim_lifecycle, evidence_count}'

# Emerging tier — early signals, lower confidence
curl -s "http://localhost:8000/v1/launches?result_tier=emerging" \
  | jq '.data[] | {name, confidence_score}'

# Count events per tier
for TIER in verified tracked emerging; do
  COUNT=$(curl -s "http://localhost:8000/v1/launches?result_tier=$TIER" | jq '.meta.total')
  echo "$TIER: $COUNT"
done
```

---

## 4. Search with Full-Text Queries

The `q` parameter uses SQLite FTS5 with BM25 ranking across `name`, `provider`,
`vehicle`, and `location` fields. Results are ordered by relevance.

```bash
# Simple keyword
curl -s "http://localhost:8000/v1/launches?q=Starlink" | jq '.data[] | {name, provider}'

# Exact phrase (URL-encode the quotes)
curl -s "http://localhost:8000/v1/launches?q=%22Falcon+Heavy%22" | jq '.data[] | {name, vehicle}'

# OR — match either term
curl -s "http://localhost:8000/v1/launches?q=falcon+OR+atlas" | jq '.data[] | {name, vehicle}'

# NOT — exclude a term
curl -s "http://localhost:8000/v1/launches?q=falcon+NOT+starlink" | jq '.data[] | {name}'

# Prefix wildcard — matches Starlink, Starliner, etc.
curl -s "http://localhost:8000/v1/launches?q=star*" | jq '.data[] | {name}'

# Combine FTS with a filter (only confirmed Starlink launches)
curl -s "http://localhost:8000/v1/launches?q=Starlink&claim_lifecycle=confirmed" \
  | jq '.data[] | {name, confidence_score}'

# Search + tier filter
curl -s "http://localhost:8000/v1/launches?q=NROL&result_tier=tracked" \
  | jq '.data[] | {name, launch_type, evidence_count}'
```

> **Note:** When `q` is active, cursor-based pagination (`cursor=`) is not supported.
> Use `page`/`per_page` instead.

---

## 5. Filter by Claim Lifecycle

The claim lifecycle tracks epistemic certainty through corroboration stages:

```
rumor → indicated → corroborated → confirmed → retracted
```

| Stage | Meaning |
|-------|---------|
| `rumor` | Single Tier 3 source (social post, blog mention) |
| `indicated` | Multiple Tier 3 signals or one Tier 2 signal |
| `corroborated` | Cross-tier corroboration (e.g. NOTAM + news article) |
| `confirmed` | At least one Tier 1 official source |
| `retracted` | Previously reported event that was corrected or cancelled |

```bash
# Only officially confirmed launches
curl -s "http://localhost:8000/v1/launches?claim_lifecycle=confirmed" \
  | jq '.data[] | {name, provider, confidence_score}'

# Early signals — social media rumours only
curl -s "http://localhost:8000/v1/launches?claim_lifecycle=rumor" \
  | jq '.data[] | {name, evidence_count, confidence_score}'

# Corroborated but not yet officially confirmed
curl -s "http://localhost:8000/v1/launches?claim_lifecycle=corroborated" \
  | jq '.data[] | {name, event_kind}'

# Retracted events — historical record
curl -s "http://localhost:8000/v1/launches?claim_lifecycle=retracted" \
  | jq '.data[] | {name, updated_at}'
```

---

## 6. Find Launches Near a Launch Site

Use `location=lat,lon` and `radius_km` to find launches at or near a facility.

> **Note:** Proximity filtering requires that the event's `location` field stores coordinates
> in `lat,lon` format. Events from Launch Library 2 store text names (e.g.,
> `"Cape Canaveral SFS, FL, USA"`), so proximity filtering returns empty results for those.
> This feature is most useful once geo-tagged sources (e.g., NOTAMs, maritime warnings) are active.

```bash
# Kennedy Space Center / Cape Canaveral (28.573, -80.649), 50 km radius
curl -s "http://localhost:8000/v1/launches?location=28.573,-80.649&radius_km=50" \
  | jq '.data[] | {name, pad, location}'

# Vandenberg Space Force Base (34.743, -120.572)
curl -s "http://localhost:8000/v1/launches?location=34.743,-120.572&radius_km=30" \
  | jq '.data[] | {name, provider, status}'

# Baikonur Cosmodrome (45.920, 63.342)
curl -s "http://localhost:8000/v1/launches?location=45.920,63.342&radius_km=100" \
  | jq '.data[] | {name, provider}'

# Kourou (5.239, -52.769) — scheduled launches, next 3 months
curl -s "http://localhost:8000/v1/launches?location=5.239,-52.769&radius_km=50&status=scheduled&from=2026-04-01T00:00:00Z&to=2026-07-01T00:00:00Z" \
  | jq '.data[] | {name, launch_date, provider}'
```

---

## 7. Retrieve Evidence and Provenance

Each launch event has a full evidence chain showing every source attribution.

```bash
# First, find a slug you want to investigate
curl -s "http://localhost:8000/v1/launches?q=Starlink&limit=1" \
  | jq '.data[0] | {slug, name, evidence_count}'

# Get full launch detail by slug
curl -s "http://localhost:8000/v1/launches/ll2-387aadc6-68ca-4090-9be7-d57603ad7c79" | jq .

# Get the evidence chain
curl -s "http://localhost:8000/v1/launches/ll2-387aadc6-68ca-4090-9be7-d57603ad7c79/evidence" | jq .
```

**Evidence response shape** (with multi-source data):

```json
{
  "launch_id": "ll2-387aadc6-68ca-4090-9be7-d57603ad7c79",
  "claim_lifecycle": "indicated",
  "event_kind": "observed",
  "evidence_count": 1,
  "tier_coverage": [],
  "attributions": [
    {
      "source_name": "Launch Library 2",
      "source_tier": null,
      "evidence_type": null,
      "source_url": null,
      "observed_at": null,
      "confidence_score": null,
      "confidence_rationale": null
    }
  ]
}
```

> **Note:** Attribution fields (`source_tier`, `evidence_type`, `source_url`) are populated
> by multi-source scrapers (NOTAMs, news RSS, social). With a single source the fields are
> null. Once additional sources run, the `tier_coverage` array will show which tiers contributed.

```bash
# Filter attributions to Tier 1 only
curl -s "http://localhost:8000/v1/launches/my-launch-slug/evidence" \
  | jq '.attributions[] | select(.source_tier == 1) | {source_name, evidence_type, confidence_score}'

# List distinct tiers contributing evidence
curl -s "http://localhost:8000/v1/launches/my-launch-slug/evidence" \
  | jq '.tier_coverage'

# Extract the evidence URL from a launch response, then fetch it
curl -s "http://localhost:8000/v1/launches/my-launch-slug" \
  | jq -r '.evidence_url' \
  | xargs curl -s | jq '.attributions[] | {source_name, source_tier, evidence_type}'
```

---

## 8. Paginate Through Large Result Sets

### Page-based pagination

```bash
# Page 1
curl -s "http://localhost:8000/v1/launches?page=1&per_page=10" \
  | jq '{total: .meta.total, page: .meta.page}'

# Page 2
curl -s "http://localhost:8000/v1/launches?page=2&per_page=10" \
  | jq '.data[] | .name'
```

### Cursor-based pagination (efficient for large datasets)

```bash
# First page — capture the cursor
CURSOR=$(curl -s "http://localhost:8000/v1/launches?limit=10" | jq -r '.meta.next_cursor')

# Next page using cursor (null means no more pages)
if [ "$CURSOR" != "null" ]; then
  curl -s "http://localhost:8000/v1/launches?cursor=$CURSOR&limit=10" | jq '.data[] | .name'
fi
```

> Cursor pagination is not supported when `q=` (full-text search) is active — use
> `page`/`per_page` in that case.

### Shell script: iterate all pages

```bash
#!/bin/bash
BASE="http://localhost:8000/v1/launches"
PAGE=1
PER_PAGE=50

while true; do
  RESP=$(curl -s "$BASE?page=$PAGE&per_page=$PER_PAGE&status=scheduled")
  TOTAL=$(echo "$RESP" | jq '.meta.total')
  echo "$RESP" | jq -r '.data[] | "\(.provider) — \(.name) — \(.launch_date)"'
  RETURNED=$(echo "$RESP" | jq '.data | length')
  if [ "$((PAGE * PER_PAGE))" -ge "$TOTAL" ] || [ "$RETURNED" -eq 0 ]; then break; fi
  PAGE=$((PAGE + 1))
done
```

---

## 9. Check Active OSINT Sources

```bash
# List all registered OSINT sources
curl -s "http://localhost:8000/v1/sources" | jq '.data[] | {name, url, enabled, last_scraped_at, event_count}'

# Show only sources that have been scraped
curl -s "http://localhost:8000/v1/sources" \
  | jq '.data[] | select(.last_scraped_at != null) | {name, event_count}'

# Sources with errors
curl -s "http://localhost:8000/v1/sources" \
  | jq '.data[] | select(.last_error != null) | {name, last_error}'
```

**Registered source names** (the `name` field):

| Name | Type |
|------|------|
| `space_agency` | Launch Library 2 (Tier 1) |
| `spacex_official` | SpaceX API v4 (Tier 1) |
| `commercial` | Commercial provider aggregator (Tier 1) |
| `esa_official` | ESA RSS (Tier 1) |
| `jaxa_official` | JAXA RSS (Tier 1) |
| `isro_official` | ISRO RSS (Tier 1) |
| `arianespace_official` | Arianespace RSS (Tier 1) |
| `cnsa_official` | CNSA RSS (Tier 1) |
| `notams` | FAA NOTAMs (Tier 2) |
| `celestrak_recent` | CelesTrak TLE feed (Tier 2) |
| `news_spaceflightnow` | SpaceFlightNow RSS (Tier 3) |
| `news_nasaspaceflight` | NASASpaceflight RSS (Tier 3) |
| `bluesky` | Bluesky public API (Tier 3) |
| `mastodon` | Mastodon public API (Tier 3) |

---

## 10. Admin: Stats and Manual Refresh

Admin endpoints require an `X-API-Key` header. Bootstrap the first key with the
`OPENORBIT_ADMIN_KEY` env var set at server startup.

```bash
# Set bootstrap key when starting the server
OPENORBIT_ADMIN_KEY=my-secret uv run uvicorn openorbit.main:app

# Create a stored admin API key
curl -s -X POST http://localhost:8000/v1/auth/keys \
  -H "X-API-Key: my-secret" \
  -H "Content-Type: application/json" \
  -d '{"name": "ops-key", "is_admin": true}'
# → {"id": 1, "name": "ops-key", "key": "aBcDe...", "is_admin": true, "created_at": "..."}
# Save the returned `key` value — shown only once.
```

```bash
ADMIN_KEY="aBcDe..."

# System statistics
curl -s -H "X-API-Key: $ADMIN_KEY" http://localhost:8000/v1/admin/stats | jq .
```

**Stats response shape:**

```json
{
  "total_events": 312,
  "events_by_source": {
    "space_agency": 180,
    "spacex_official": 52,
    "notams": 40,
    "news_spaceflightnow": 30,
    "bluesky": 10
  },
  "events_by_type": {
    "civilian": 270,
    "military": 38,
    "unknown": 4
  },
  "events_by_lifecycle": {
    "confirmed": 143,
    "corroborated": 48,
    "indicated": 54,
    "rumor": 65,
    "retracted": 2
  },
  "avg_confidence": 71.4,
  "last_refresh_at": "2026-04-06T18:00:00Z"
}
```

```bash
# List sources with health metadata
curl -s -H "X-API-Key: $ADMIN_KEY" http://localhost:8000/v1/admin/sources | jq .

# Manually trigger a scrape for a source (get ID from /v1/sources first)
SOURCE_ID=$(curl -s http://localhost:8000/v1/sources \
  | jq '[.data[] | select(.name == "space_agency")] | .[0].id')

curl -s -X POST \
  -H "X-API-Key: $ADMIN_KEY" \
  "http://localhost:8000/v1/admin/sources/$SOURCE_ID/refresh" | jq .
```

---

## 11. Python Examples

### Basic setup

```python
import httpx

BASE = "http://localhost:8000"

with httpx.Client(base_url=BASE) as client:
    resp = client.get("/v1/launches", params={"status": "scheduled", "result_tier": "tracked"})
    resp.raise_for_status()
    body = resp.json()
    for launch in body["data"]:
        print(f"{launch['name']} — {launch['launch_date']} — tier: {launch['result_tier']}")
```

### Async client with pagination

```python
import asyncio
import httpx

async def fetch_all_scheduled(base: str = "http://localhost:8000") -> list[dict]:
    """Fetch all scheduled launches across all pages."""
    results: list[dict] = []
    page = 1

    async with httpx.AsyncClient(base_url=base) as client:
        while True:
            resp = await client.get(
                "/v1/launches",
                params={"status": "scheduled", "page": page, "per_page": 100},
            )
            resp.raise_for_status()
            body = resp.json()
            results.extend(body["data"])
            if page * 100 >= body["meta"]["total"]:
                break
            page += 1

    return results

launches = asyncio.run(fetch_all_scheduled())
print(f"Fetched {len(launches)} scheduled launches")
```

### OSINT triage: surface emerging signals

```python
import httpx

def triage_emerging_signals(base: str = "http://localhost:8000") -> None:
    """Print all emerging-tier rumour events."""
    with httpx.Client(base_url=base) as client:
        resp = client.get("/v1/launches", params={
            "result_tier": "emerging",
            "claim_lifecycle": "rumor",
            "per_page": 50,
        })
        resp.raise_for_status()
        events = resp.json()["data"]

    print(f"{'Name':<45} {'Provider':<15} {'Confidence':>10} {'Sources':>7}")
    print("-" * 82)
    for ev in events:
        print(
            f"{ev['name'][:44]:<45} "
            f"{(ev['provider'] or '')[:14]:<15} "
            f"{ev['confidence_score']:>10.1f} "
            f"{ev['evidence_count']:>7}"
        )

triage_emerging_signals()
```

### Fetch full evidence chain for a launch

```python
import httpx

def get_evidence(slug: str, base: str = "http://localhost:8000") -> dict:
    with httpx.Client(base_url=base) as client:
        resp = client.get(f"/v1/launches/{slug}/evidence")
        resp.raise_for_status()
        return resp.json()

evidence = get_evidence("ll2-387aadc6-68ca-4090-9be7-d57603ad7c79")

print(f"Lifecycle  : {evidence['claim_lifecycle']}")
print(f"Event kind : {evidence['event_kind']}")
print(f"Sources    : {evidence['evidence_count']} (tiers: {evidence['tier_coverage']})")
print()
for attr in evidence["attributions"]:
    print(f"  [{attr['source_tier']}] {attr['source_name']}")
    print(f"      type       : {attr['evidence_type']}")
    print(f"      confidence : {attr['confidence_score']}")
    print(f"      url        : {attr['source_url']}")
```

### Full-text search

```python
import httpx

def search_launches(query: str, tier: str | None = None) -> list[dict]:
    params: dict[str, str | int] = {"q": query, "per_page": 50}
    if tier:
        params["result_tier"] = tier

    with httpx.Client(base_url="http://localhost:8000") as client:
        resp = client.get("/v1/launches", params=params)
        resp.raise_for_status()
        return resp.json()["data"]

# Tracked Starlink launches (verified requires multi-source; tracked is more common with single source)
starlink = search_launches("Starlink", tier="tracked")
print(f"Found {len(starlink)} tracked Starlink launches")

# Lunar/Artemis coverage across all tiers
lunar = search_launches("lunar OR moon OR artemis")
for ev in lunar:
    print(f"  {ev['name']} ({ev['claim_lifecycle']}, confidence: {ev['confidence_score']})")
```

---

## See Also

- [API Reference](api-reference.md) — complete parameter and response field documentation
- [Quick Start](quickstart.md) — installation and first-run guide
- [Authentication](auth.md) — managing API keys for write operations
- [Scrapers](scrapers/) — documentation for each OSINT source
