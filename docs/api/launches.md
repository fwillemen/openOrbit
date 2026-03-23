# Launch Events API

The launches endpoints provide paginated listing and slug-based detail retrieval for orbital and airspace launch events aggregated by openOrbit.

## Endpoints

### `GET /v1/launches`

Returns a paginated list of launch events with optional filtering.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `from` | ISO 8601 datetime | — | Filter events on or after this datetime |
| `to` | ISO 8601 datetime | — | Filter events on or before this datetime |
| `provider` | string | — | Filter by launch provider name (e.g. `SpaceX`) |
| `launch_type` | `civilian` \| `military` \| `unknown` | — | Filter by launch type |
| `status` | `scheduled` \| `delayed` \| `launched` \| `failed` \| `cancelled` | — | Filter by event status |
| `page` | integer ≥ 1 | `1` | Page number (1-indexed) |
| `per_page` | integer 1–100 | `25` | Results per page |

#### Response Envelope

```json
{
  "data": [ ...LaunchEvent ],
  "meta": {
    "total": 143,
    "page": 1,
    "per_page": 25
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `data` | array | Array of launch event objects |
| `meta.total` | integer | Total number of events matching the filter |
| `meta.page` | integer | Current page number |
| `meta.per_page` | integer | Page size |

#### Launch Event Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Internal DB identifier |
| `slug` | string | URL-safe unique event identifier |
| `name` | string | Human-readable event name |
| `launch_date` | ISO 8601 datetime | Scheduled launch date/time |
| `launch_date_precision` | string | Date precision: `second`, `minute`, `hour`, `day`, `month`, `year`, `quarter` |
| `provider` | string | Launch service provider |
| `vehicle` | string \| null | Rocket/vehicle name |
| `location` | string \| null | Launch site location |
| `pad` | string \| null | Launch pad name |
| `launch_type` | `civilian` \| `military` \| `unknown` | Launch type classification |
| `status` | string | Event status |
| `confidence_score` | float | Source confidence 0.0–1.0 |
| `created_at` | ISO 8601 datetime | Record creation timestamp |
| `updated_at` | ISO 8601 datetime | Record last-update timestamp |
| `sources` | array | Attribution sources (only on detail endpoint) |

#### Example Request

```bash
# All upcoming SpaceX civilian launches
curl "http://localhost:8000/v1/launches?provider=SpaceX&launch_type=civilian&status=scheduled&per_page=10"

# Launches in a date window
curl "http://localhost:8000/v1/launches?from=2025-01-01T00:00:00Z&to=2025-06-30T23:59:59Z"
```

#### Example Response

```json
{
  "data": [
    {
      "id": 42,
      "slug": "ll2-abc123",
      "name": "SpaceX Falcon 9 | Starlink Group 11-4",
      "launch_date": "2025-07-15T03:30:00Z",
      "launch_date_precision": "second",
      "provider": "SpaceX",
      "vehicle": "Falcon 9",
      "location": "Cape Canaveral, FL, USA",
      "pad": "SLC-40",
      "launch_type": "civilian",
      "status": "scheduled",
      "confidence_score": 0.7,
      "created_at": "2025-06-01T12:00:00Z",
      "updated_at": "2025-06-10T08:45:00Z",
      "sources": []
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "per_page": 10
  }
}
```

---

### `GET /v1/launches/{slug}`

Returns a single launch event by its unique slug, including full source attribution.

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `slug` | string | URL-safe event identifier (e.g. `ll2-abc123`, `notam-1-2345`) |

#### Example Request

```bash
curl "http://localhost:8000/v1/launches/ll2-abc123"
```

#### Example Response

```json
{
  "id": 42,
  "slug": "ll2-abc123",
  "name": "SpaceX Falcon 9 | Starlink Group 11-4",
  "launch_date": "2025-07-15T03:30:00Z",
  "launch_date_precision": "second",
  "provider": "SpaceX",
  "vehicle": "Falcon 9",
  "location": "Cape Canaveral, FL, USA",
  "pad": "SLC-40",
  "launch_type": "civilian",
  "status": "scheduled",
  "confidence_score": 0.7,
  "created_at": "2025-06-01T12:00:00Z",
  "updated_at": "2025-06-10T08:45:00Z",
  "sources": [
    {
      "name": "LL2 Commercial – SpaceX",
      "url": "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?format=json&limit=100&lsp__name=SpaceX",
      "scraped_at": "2025-06-10T08:44:00Z"
    }
  ]
}
```

---

## HTTP Status Codes

| Code | Meaning | When |
|------|---------|------|
| `200` | OK | Request succeeded |
| `404` | Not Found | Slug does not exist in the database |
| `422` | Unprocessable Entity | Query parameter validation failed (e.g. invalid `launch_type`, malformed date) |
| `500` | Internal Server Error | Unexpected server-side error |

### 404 Response

```json
{
  "detail": {
    "error": "not_found"
  }
}
```

### 422 Response (FastAPI validation)

```json
{
  "detail": [
    {
      "loc": ["query", "launch_type"],
      "msg": "value is not a valid enumeration member",
      "type": "type_error.enum"
    }
  ]
}
```

---

## Pagination

Use the `meta` block to drive pagination:

```python
import httpx

async def fetch_all_launches():
    base = "http://localhost:8000/v1/launches"
    page, events = 1, []

    async with httpx.AsyncClient() as client:
        while True:
            r = await client.get(base, params={"page": page, "per_page": 100})
            body = r.json()
            events.extend(body["data"])
            if len(events) >= body["meta"]["total"]:
                break
            page += 1

    return events
```
