# API Reference

Complete reference for all openOrbit REST API endpoints.

Interactive documentation is also available at **http://localhost:8000/docs** (Swagger UI) and **http://localhost:8000/redoc** (ReDoc) when the server is running.

---

## Authentication

All `GET` endpoints are **public** — no key required.  
Write operations require an admin API key passed in the `X-API-Key` header (or `?api_key=` query parameter).

| Header | Example |
|--------|---------|
| `X-API-Key` | `X-API-Key: aBcDeFgHiJkL...` |

---

## Launches

Endpoints for discovering and retrieving orbital launch events.

### `GET /v1/launches`

List launch events with optional filtering and pagination.

| Field | Value |
|-------|-------|
| **Auth required** | No |
| **Response** | `200 PaginatedLaunchResponse` |

#### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `from` | `datetime` | Filter events on or after this datetime (ISO 8601). |
| `to` | `datetime` | Filter events on or before this datetime (ISO 8601). |
| `provider` | `string` | Case-insensitive substring match on provider name (e.g. `SpaceX`). |
| `launch_type` | `civilian \| military \| unknown` | Filter by launch classification. |
| `status` | `scheduled \| delayed \| launched \| failed \| cancelled` | Filter by event status. |
| `min_confidence` | `float [0–100]` | Exclude events with a confidence score below this value. |
| `has_inference_flag` | `string` | Filter to events that include a specific inference flag. |
| `claim_lifecycle` | `string` | Filter by epistemic lifecycle state. One of: `rumor`, `indicated`, `corroborated`, `confirmed`, `retracted`. |
| `location` | `string` | Centre point for proximity search, format: `lat,lon` (e.g. `28.573,-80.649`). |
| `radius_km` | `integer ≥ 1` | Search radius in km (requires `location`). Defaults to `100`. |
| `cursor` | `string` | Opaque cursor token for cursor-based pagination (takes precedence over `page`/`per_page`). |
| `limit` | `integer [1–100]` | Results per page for cursor pagination. Default: `25`. |
| `page` | `integer ≥ 1` | Page number for page-based pagination. Default: `1`. |
| `per_page` | `integer [1–100]` | Results per page for page-based pagination. Default: `25`. |

#### Example

```bash
curl "http://localhost:8000/v1/launches?provider=SpaceX&status=scheduled&per_page=10"
```

#### Error Responses

| Status | Reason |
|--------|--------|
| `400` | Invalid `location` format or invalid `cursor` token. |

---

### `GET /v1/launches/{slug}`

Retrieve a single launch event by its URL-safe slug.

| Field | Value |
|-------|-------|
| **Auth required** | No |
| **Response** | `200 LaunchEventResponse` |

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `slug` | `string` | URL-safe unique event identifier (e.g. `falcon-9-starlink-6-32-2025-01-22`). |

#### Example

```bash
curl "http://localhost:8000/v1/launches/falcon-9-starlink-6-32-2025-01-22"
```

#### Error Responses

| Status | Reason |
|--------|--------|
| `404` | No launch event found for the given slug. |

---

## Source Tiers & Claim Lifecycle

openOrbit uses a two-dimensional trust model for every launch event:

### Source Tiers

| Tier | Label | Examples |
|------|-------|---------|
| 1 | Official | SpaceX, NASA, ESA, JAXA, ISRO, CNSA, Arianespace |
| 2 | Operational | NOTAMs, AIS, radar tracking feeds |
| 3 | Analytical | SpaceflightNow, NASASpaceflight, amateur observers |

### Claim Lifecycle

Events progress through these epistemic states:

| State | Meaning |
|-------|---------|
| `rumor` | Unverified mention |
| `indicated` | Single credible source |
| `corroborated` | Multiple independent sources agree |
| `confirmed` | Official confirmation received |
| `retracted` | Previously reported event cancelled or withdrawn |

---

## Sources

Endpoint for inspecting the OSINT source registry.

### `GET /v1/sources`

Return all OSINT sources registered in the system with event counts.

| Field | Value |
|-------|-------|
| **Auth required** | No |
| **Response** | `200 { data: SourceRecord[] }` |

#### Example

```bash
curl "http://localhost:8000/v1/sources"
```

#### Source Record Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `integer` | Internal source ID. |
| `name` | `string` | Human-readable source name. |
| `url` | `string` | Base URL of the source. |
| `enabled` | `boolean` | Whether this source is actively scraped. |
| `refresh_interval_hours` | `integer` | How often the source is scraped. |
| `last_scraped_at` | `datetime \| null` | ISO 8601 timestamp of last successful scrape. |
| `event_count` | `integer` | Number of distinct launch events attributed to this source. |
| `last_error` | `string \| null` | Last scrape error message, if any. |

---

## Auth

Admin-only endpoints for API key lifecycle management.

### `POST /v1/auth/keys`

Create a new API key.

| Field | Value |
|-------|-------|
| **Auth required** | Yes (admin) |
| **Request body** | `ApiKeyCreateRequest` |
| **Response** | `201 ApiKeyCreateResponse` |

#### Request Body

```json
{
  "name": "ci-pipeline",
  "is_admin": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | ✅ | Human-readable label for the key. |
| `is_admin` | `boolean` | ❌ (default `false`) | Whether this key can manage other keys. |

#### Example

```bash
curl -s -X POST http://localhost:8000/v1/auth/keys \
  -H "X-API-Key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"name": "ci-pipeline", "is_admin": false}'
```

#### Error Responses

| Status | Reason |
|--------|--------|
| `401` | Missing API key. |
| `403` | Invalid, revoked, or non-admin API key. |

---

### `DELETE /v1/auth/keys/{key_id}`

Revoke an existing API key.

| Field | Value |
|-------|-------|
| **Auth required** | Yes (admin) |
| **Response** | `200 ApiKeyRevokeResponse` |

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `key_id` | `integer` | Database ID of the API key to revoke. |

#### Example

```bash
curl -s -X DELETE http://localhost:8000/v1/auth/keys/1 \
  -H "X-API-Key: your-admin-key"
```

#### Error Responses

| Status | Reason |
|--------|--------|
| `401` | Missing API key. |
| `403` | Invalid, revoked, or non-admin API key. |
| `404` | API key not found. |
| `409` | API key is already revoked. |

---

## Health

### `GET /health`

Service health and version check. No authentication required.

| Field | Value |
|-------|-------|
| **Auth required** | No |
| **Response** | `200 { status: string, version: string }` |

#### Example

```bash
curl http://localhost:8000/health
```

```json
{"status": "ok", "version": "0.1.0"}
```

---

## Response Schemas

### `LaunchEventResponse`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `integer` | Internal database ID. |
| `slug` | `string` | URL-safe unique identifier. |
| `name` | `string` | Human-readable event name. |
| `launch_date` | `datetime` | Scheduled launch date/time (ISO 8601). |
| `launch_date_precision` | `string` | Precision of the date: `exact`, `hour`, `day`, `week`, `month`. |
| `provider` | `string` | Launch provider (e.g. `SpaceX`, `Roscosmos`). |
| `vehicle` | `string \| null` | Launch vehicle name. |
| `location` | `string \| null` | Launch site coordinates in `lat,lon` format. |
| `pad` | `string \| null` | Launch pad name and site. |
| `launch_type` | `string` | Classification: `civilian`, `military`, or `unknown`. |
| `status` | `string` | Event status: `scheduled`, `delayed`, `launched`, `failed`, `cancelled`. |
| `confidence_score` | `float` | Composite confidence score (0–100). |
| `claim_lifecycle` | `string` | Epistemic lifecycle state: `rumor` → `indicated` → `corroborated` → `confirmed` (or `retracted`). Default: `indicated`. |
| `event_kind` | `string` | Whether the event is `observed` (direct evidence) or `inferred`. Default: `observed`. |
| `result_tier` | `string` | Dashboard tier: `emerging`, `tracked`, or `verified`. |
| `evidence_count` | `integer` | Number of source attributions for this event. |
| `created_at` | `datetime` | Record creation timestamp. |
| `updated_at` | `datetime` | Record last-updated timestamp. |
| `sources` | `AttributionResponse[]` | OSINT sources that confirmed this event. |
| `inference_flags` | `string[]` | Flags describing inferred fields (e.g. `date_inferred_from_window`). |

### `PaginationMeta`

| Field | Type | Description |
|-------|------|-------------|
| `total` | `integer` | Total matching events across all pages. |
| `page` | `integer` | Current page (page-based) or `1` (cursor-based). |
| `per_page` | `integer` | Results per page. |
| `next_cursor` | `string \| null` | Opaque cursor for the next page (cursor-based pagination only). |

### `AttributionResponse`

| Field | Type | Description |
|-------|------|-------------|
| `name` | `string` | Source name. |
| `url` | `string` | Direct URL to the source article or page. |
| `scraped_at` | `datetime \| null` | When this attribution was captured. |
| `evidence_type` | `string \| null` | Classification of evidence: `official_schedule`, `notam`, `press_release`, `social_media`, `analyst_report`. |
| `source_tier` | `integer \| null` | Source credibility tier: `1`=Official, `2`=Operational, `3`=Analytical. |
| `confidence_score` | `integer \| null` | Attribution-level confidence score (0–100). |
| `confidence_rationale` | `string \| null` | Human-readable rationale for the confidence score. |

### `ApiKeyCreateRequest`

| Field | Type | Description |
|-------|------|-------------|
| `name` | `string` | Human-readable key label. |
| `is_admin` | `boolean` | Admin privilege flag (default `false`). |

### `ApiKeyCreateResponse`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `integer` | Database ID. |
| `name` | `string` | Key label. |
| `key` | `string` | Plaintext key — shown **once only**, store securely. |
| `is_admin` | `boolean` | Admin privilege flag. |
| `created_at` | `string` | ISO 8601 creation timestamp. |

### `ApiKeyRevokeResponse`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `integer` | Database ID of the revoked key. |
| `revoked_at` | `string` | ISO 8601 revocation timestamp. |
