# openOrbit — Usage Examples

This guide shows practical OSINT workflows using the openOrbit API.
All examples use `curl` with [`jq`](https://jqlang.github.io/jq/) for formatting.
A Python section at the end shows how to use the API from code.

> **Prerequisites:** Server running at `http://localhost:8000`. See [Quick Start](quickstart.md).

---

## Table of Contents

1. [Browse upcoming launches](#1-browse-upcoming-launches)
2. [Filter by provider or vehicle](#2-filter-by-provider-or-vehicle)
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

All GET endpoints are public — no API key needed.

```bash
# All launches (first page, 25 results)
curl -s http://localhost:8000/v1/launches | jq .

# Launches from now until end of year
curl -s "http://localhost:8000/v1/launches?from=2026-01-01T00:00:00Z&to=2026-12-31T23:59:59Z" | jq .

# Only scheduled launches
curl -s "http://localhost:8000/v1/launches?status=scheduled" | jq '.data[] | {slug, name, provider, launch_date, confidence_score}'
```

**Sample response (abbreviated):**

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
      "evidence_url": "http://localhost:8000/v1/launches/falcon-9-starlink-6-32-2026-03-15/evidence"
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

## 2. Filter by Provider or Vehicle

```bash
# All SpaceX launches (case-insensitive substring match)
curl -s "http://localhost:8000/v1/launches?provider=SpaceX" | jq '.data[] | {name, status, launch_date}'

# Falcon 9 specifically (match on vehicle field via FTS)
curl -s "http://localhost:8000/v1/launches?q=Falcon+9" | jq '.data[] | {name, vehicle, provider}'

# All military launches
curl -s "http://localhost:8000/v1/launches?launch_type=military" | jq '.data[] | {name, provider, launch_type, result_tier}'

# Scheduled Arianespace launches this quarter
curl -s "http://localhost:8000/v1/launches?provider=Arianespace&status=scheduled" | jq '.meta.total'
```

---

## 3. Filter by Confidence and Result Tier

openOrbit classifies each event into one of three result tiers based on confidence score
and the number of corroborating sources:

| Tier | Meaning |
|------|---------|
| `verified` | confidence ≥ 80 and ≥ 2 independent attributions |
| `tracked` | confidence ≥ 60 |
| `emerging` | all others (early signals, single-source rumours) |

```bash
# Only high-confidence verified events
curl -s "http://localhost:8000/v1/launches?result_tier=verified" \
  | jq '.data[] | {name, confidence_score, evidence_count}'

# Events with at least 70% confidence
curl -s "http://localhost:8000/v1/launches?min_confidence=70" \
  | jq '.data[] | {name, confidence_score, result_tier}'

# Tracked events (good signal, not yet fully corroborated)
curl -s "http://localhost:8000/v1/launches?result_tier=tracked&status=scheduled" \
  | jq '.data[] | {name, claim_lifecycle, evidence_count}'

# Count events per tier
curl -s "http://localhost:8000/v1/launches?result_tier=verified" | jq '.meta.total'
curl -s "http://localhost:8000/v1/launches?result_tier=tracked" | jq '.meta.total'
curl -s "http://localhost:8000/v1/launches?result_tier=emerging" | jq '.meta.total'
```

---

## 4. Search with Full-Text Queries

The `q` parameter uses SQLite FTS5 with BM25 ranking across event `name`, `provider`,
`vehicle`, and `location` fields. Results are ordered by relevance.

```bash
# Simple keyword
curl -s "http://localhost:8000/v1/launches?q=Starlink" | jq '.data[] | {name, provider}'

# Exact phrase (URL-encode the quotes)
curl -s "http://localhost:8000/v1/launches?q=%22Falcon+Heavy%22" | jq '.data[] | {name, vehicle}'

# OR — either term
curl -s "http://localhost:8000/v1/launches?q=falcon+OR+atlas" | jq '.data[] | {name, vehicle}'

# NOT — exclude term (find Falcon launches that are not Starlink)
curl -s "http://localhost:8000/v1/launches?q=falcon+NOT+starlink" | jq '.data[] | {name}'

# Prefix wildcard (all "star*" matches: Starlink, Starliner, etc.)
curl -s "http://localhost:8000/v1/launches?q=star*" | jq '.data[] | {name}'

# Combine FTS with filters (Starlink launches, confirmed only)
curl -s "http://localhost:8000/v1/launches?q=Starlink&claim_lifecycle=confirmed" \
  | jq '.data[] | {name, confidence_score}'

# Search + tier filter
curl -s "http://localhost:8000/v1/launches?q=NROL&result_tier=verified" \
  | jq '.data[] | {name, launch_type, evidence_count}'
```

---

## 5. Filter by Claim Lifecycle

The claim lifecycle tracks the epistemic certainty of each event through corroboration stages:

```
rumor → indicated → corroborated → confirmed → retracted
```

- **rumor** — single Tier 3 source (social media post, blog mention)
- **indicated** — multiple Tier 3 signals or one Tier 2 signal
- **corroborated** — cross-tier corroboration (e.g. NOTAM + news)
- **confirmed** — at least one Tier 1 official source
- **retracted** — previously reported event that was cancelled or corrected

```bash
# Only confirmed launches (at least one official source)
curl -s "http://localhost:8000/v1/launches?claim_lifecycle=confirmed" \
  | jq '.data[] | {name, provider, claim_lifecycle, confidence_score}'

# Early signals — what's circulating on social media right now
curl -s "http://localhost:8000/v1/launches?claim_lifecycle=rumor" \
  | jq '.data[] | {name, evidence_count, confidence_score}'

# Corroborated but not yet officially confirmed
curl -s "http://localhost:8000/v1/launches?claim_lifecycle=corroborated" \
  | jq '.data[] | {name, event_kind}'

# Retracted events — historical record of cancelled launches
curl -s "http://localhost:8000/v1/launches?claim_lifecycle=retracted" \
  | jq '.data[] | {name, updated_at}'
```

---

## 6. Find Launches Near a Launch Site

Use `location` (lat,lon) and `radius_km` to find launches at or near a specific facility.

```bash
# Kennedy Space Center / Cape Canaveral (28.573, -80.649), 50 km radius
curl -s "http://localhost:8000/v1/launches?location=28.573,-80.649&radius_km=50" \
  | jq '.data[] | {name, pad, location}'

# Vandenberg Space Force Base (34.743, -120.572)
curl -s "http://localhost:8000/v1/launches?location=34.743,-120.572&radius_km=30" \
  | jq '.data[] | {name, provider, status}'

# Baikonur Cosmodrome (45.920, 63.342), 100 km radius
curl -s "http://localhost:8000/v1/launches?location=45.920,63.342&radius_km=100" \
  | jq '.data[] | {name, provider}'

# Scheduled launches near Kourou (5.239, -52.769) in the next 3 months
curl -s "http://localhost:8000/v1/launches?location=5.239,-52.769&radius_km=50&status=scheduled&from=2026-04-01T00:00:00Z&to=2026-07-01T00:00:00Z" \
  | jq '.data[] | {name, launch_date, provider}'
```

> **Tip:** Combine with `result_tier=verified` to limit proximity results to
> well-corroborated events only.

---

## 7. Retrieve Evidence and Provenance

Each event has an evidence chain showing every source that contributed to it,
along with confidence scores and evidence types.

```bash
# Get a single launch by slug
curl -s "http://localhost:8000/v1/launches/falcon-9-starlink-6-32-2026-03-15" | jq .

# Extract the evidence URL from a launch response
EVIDENCE_URL=$(curl -s "http://localhost:8000/v1/launches/falcon-9-starlink-6-32-2026-03-15" \
  | jq -r '.evidence_url')

# Fetch the full evidence chain
curl -s "$EVIDENCE_URL" | jq .
```

**Evidence response:**

```json
{
  "slug": "falcon-9-starlink-6-32-2026-03-15",
  "name": "Falcon 9 | Starlink Group 6-32",
  "confidence_score": 87.5,
  "claim_lifecycle": "confirmed",
  "event_kind": "observed",
  "evidence_count": 3,
  "tier_coverage": [1, 2, 3],
  "attributions": [
    {
      "source_name": "Launch Library 2",
      "source_tier": 1,
      "evidence_type": "official_schedule",
      "source_url": "https://ll.thespacedevs.com/2.2.0/launch/...",
      "observed_at": "2026-03-10T08:00:00Z",
      "confidence_score": 95.0,
      "confidence_rationale": "Official operator schedule"
    },
    {
      "source_name": "FAA NOTAMs",
      "source_tier": 2,
      "evidence_type": "notam",
      "source_url": "https://notams.aim.faa.gov/...",
      "observed_at": "2026-03-12T14:00:00Z",
      "confidence_score": 88.0,
      "confidence_rationale": "Active NOTAM for launch window"
    },
    {
      "source_name": "SpaceFlightNow",
      "source_tier": 3,
      "evidence_type": "media",
      "source_url": "https://spaceflightnow.com/...",
      "observed_at": "2026-03-11T10:30:00Z",
      "confidence_score": 70.0,
      "confidence_rationale": "News coverage of scheduled launch"
    }
  ]
}
```

```bash
# Count how many attributions each source tier contributes
curl -s "$EVIDENCE_URL" \
  | jq '[.attributions[] | .source_tier] | group_by(.) | map({tier: .[0], count: length})'

# Show only official (Tier 1) attributions
curl -s "$EVIDENCE_URL" \
  | jq '.attributions[] | select(.source_tier == 1) | {source_name, evidence_type, confidence_score}'
```

---

## 8. Paginate Through Large Result Sets

### Page-based pagination (simple)

```bash
# Page 1
curl -s "http://localhost:8000/v1/launches?page=1&per_page=10" | jq '{total: .meta.total, page: .meta.page}'

# Page 2
curl -s "http://localhost:8000/v1/launches?page=2&per_page=10" | jq '.data[] | .name'
```

### Cursor-based pagination (efficient for large datasets)

```bash
# First page — get next_cursor from response
CURSOR=$(curl -s "http://localhost:8000/v1/launches?limit=10" | jq -r '.meta.next_cursor')

# Next page using cursor
curl -s "http://localhost:8000/v1/launches?cursor=$CURSOR&limit=10" | jq '.data[] | .name'
```

> **Note:** Cursor pagination is not supported when `q` (full-text search) is active.
> Use `page`/`per_page` instead.

### Shell loop over all pages

```bash
#!/bin/bash
BASE="http://localhost:8000/v1/launches"
PAGE=1
TOTAL_PAGES=99  # will be updated after first request

while [ $PAGE -le $TOTAL_PAGES ]; do
  RESP=$(curl -s "$BASE?page=$PAGE&per_page=50&status=scheduled")
  TOTAL=$(echo "$RESP" | jq '.meta.total')
  TOTAL_PAGES=$(( (TOTAL + 49) / 50 ))
  echo "$RESP" | jq -r '.data[] | "\(.provider) — \(.name) — \(.launch_date)"'
  PAGE=$((PAGE + 1))
done
```

---

## 9. Check Active OSINT Sources

```bash
# List all registered OSINT sources
curl -s "http://localhost:8000/v1/sources" | jq '.[] | {name, tier: .source_tier, last_scraped: .last_scraped_at}'

# Show sources by tier
curl -s "http://localhost:8000/v1/sources" \
  | jq 'group_by(.source_tier) | map({tier: .[0].source_tier, sources: map(.name)})'
```

**Sample output:**

```json
[
  {"tier": 1, "sources": ["Launch Library 2", "SpaceX API", "ESA", "JAXA", "ISRO", "Arianespace", "CNSA"]},
  {"tier": 2, "sources": ["FAA NOTAMs", "CelesTrak TLE"]},
  {"tier": 3, "sources": ["SpaceFlightNow RSS", "NASASpaceflight RSS", "Bluesky", "Mastodon"]}
]
```

---

## 10. Admin: Stats and Manual Refresh

Admin endpoints require an `X-API-Key` header with an admin key.

```bash
ADMIN_KEY="your-admin-key-here"

# Overall system statistics
curl -s -H "X-API-Key: $ADMIN_KEY" http://localhost:8000/v1/admin/stats | jq .
```

```json
{
  "total_events": 312,
  "events_by_tier": {
    "verified": 87,
    "tracked": 143,
    "emerging": 82
  },
  "events_by_lifecycle": {
    "rumor": 65,
    "indicated": 54,
    "corroborated": 48,
    "confirmed": 143,
    "retracted": 2
  },
  "avg_confidence": 71.4,
  "last_refresh_at": "2026-04-06T18:00:00Z"
}
```

```bash
# List sources with health info
curl -s -H "X-API-Key: $ADMIN_KEY" http://localhost:8000/v1/admin/sources | jq .

# Manually trigger a scrape for a specific source (by source ID)
SOURCE_ID=$(curl -s "http://localhost:8000/v1/sources" | jq '[.[] | select(.name == "SpaceX API")] | .[0].id')
curl -s -X POST -H "X-API-Key: $ADMIN_KEY" \
  "http://localhost:8000/v1/admin/sources/$SOURCE_ID/refresh" | jq .
```

---

## 11. Python Examples

### Basic setup

```python
import httpx

BASE = "http://localhost:8000"

# All GET endpoints are public
with httpx.Client(base_url=BASE) as client:
    resp = client.get("/v1/launches", params={"status": "scheduled", "result_tier": "verified"})
    resp.raise_for_status()
    data = resp.json()
    for launch in data["data"]:
        print(f"{launch['name']} — {launch['launch_date']} — tier: {launch['result_tier']}")
```

### Async client with pagination

```python
import asyncio
import httpx

async def fetch_all_launches(base: str = "http://localhost:8000") -> list[dict]:
    """Fetch all scheduled launches across all pages."""
    results = []
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

launches = asyncio.run(fetch_all_launches())
print(f"Fetched {len(launches)} scheduled launches")
```

### OSINT triage: surface emerging signals

```python
import httpx
from datetime import datetime, timezone

BASE = "http://localhost:8000"

def triage_emerging_signals() -> None:
    """Print all emerging-tier events that entered as social media rumours."""
    with httpx.Client(base_url=BASE) as client:
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
            f"{ev['provider'][:14]:<15} "
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

evidence = get_evidence("falcon-9-starlink-6-32-2026-03-15")

print(f"Claim lifecycle : {evidence['claim_lifecycle']}")
print(f"Evidence count  : {evidence['evidence_count']}")
print(f"Tier coverage   : {evidence['tier_coverage']}")
print()
for attr in evidence["attributions"]:
    print(f"  [{attr['source_tier']}] {attr['source_name']}")
    print(f"      type       : {attr['evidence_type']}")
    print(f"      confidence : {attr['confidence_score']}")
    print(f"      url        : {attr['source_url']}")
```

### Full-text search with result processing

```python
import httpx

def search_launches(query: str, tier: str | None = None) -> list[dict]:
    params: dict = {"q": query, "per_page": 50}
    if tier:
        params["result_tier"] = tier

    with httpx.Client(base_url="http://localhost:8000") as client:
        resp = client.get("/v1/launches", params=params)
        resp.raise_for_status()
        return resp.json()["data"]

# Find all Starlink verified launches
starlink = search_launches("Starlink", tier="verified")
print(f"Found {len(starlink)} verified Starlink launches")

# Find anything related to lunar missions
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
