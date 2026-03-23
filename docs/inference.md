# Inference Engine

The openOrbit inference engine (`openorbit.pipeline.inference`) applies deterministic
heuristic rules to launch events stored in the database. Each rule can annotate an event
with one or more **inference flags** and optionally adjust the event's confidence score.

---

## Overview

The engine is exposed via the `InferenceEngine` class and its single public method:

```python
from openorbit.pipeline.inference import InferenceEngine

engine = InferenceEngine()
result = await engine.run(conn)
# → {"events_updated": 12, "rules_applied": 7}
```

Flags are persisted in the `inference_flags` column of `launch_events` (JSON text array,
nullable). The engine is **idempotent** — running it multiple times on the same data
produces identical results without duplicating flags or drifting confidence scores.

---

## Inference Rules

### 1. `multi_source_corroboration`

**Trigger:** An event is attributed to ≥ 2 distinct OSINT source IDs in
`event_attributions`.

**Effect:**
- Adds the `"multi_source_corroboration"` flag to the event.
- Increases `confidence_score` by **+20** (capped at 100).

**Rationale:** Independent confirmation from multiple unrelated sources significantly
increases confidence that the event is genuine and accurately described.

---

### 2. `pad_reuse_pattern`

**Trigger:** At least one other launch event from the **same launch pad** exists with a
`launch_date` falling in the 30-day window immediately before the current event's
`launch_date`.

**Effect:**
- Adds the `"pad_reuse_pattern"` flag to the event.

**Rationale:** Launch pads typically have maintenance and safety clearance cycles.
A pad that fired within the past 30 days is in an active operational phase, which
corroborates the plausibility of subsequent launches.

---

### 3. `notam_cluster`

**Trigger:** ≥ 2 distinct events sourced from an OSINT source whose name contains
`NOTAM` (case-insensitive) have a `launch_date` within the ±3-day window around the
current event's `launch_date`.

**Effect:**
- Adds the `"notam_cluster"` flag to the event.

**Rationale:** NOTAMs (Notices to Air Missions) are published by aviation authorities
to restrict airspace around upcoming launches. A cluster of NOTAM-linked events in the
same time window strongly suggests coordinated launch activity in the area.

---

## Database Schema

The `inference_flags` column was added to `launch_events` via a backwards-compatible
migration in `init_db_schema()`:

```sql
ALTER TABLE launch_events ADD COLUMN inference_flags TEXT;
```

The value is stored as a JSON array string (e.g. `'["multi_source_corroboration"]'`) or
`NULL` when no rules have fired.

---

## API Integration

### Filter by flag — `GET /v1/launches?has_inference_flag=<flag>`

Returns only events whose `inference_flags` array contains the specified flag:

```
GET /v1/launches?has_inference_flag=notam_cluster
GET /v1/launches?has_inference_flag=pad_reuse_pattern
GET /v1/launches?has_inference_flag=multi_source_corroboration
```

### Event detail — `GET /v1/launches/{slug}`

The response includes an `inference_flags` array:

```json
{
  "slug": "spacex-falcon9-2025-01-22",
  "name": "SpaceX Falcon 9 — Starlink",
  "confidence_score": 80.0,
  "inference_flags": ["multi_source_corroboration", "pad_reuse_pattern"],
  ...
}
```

---

## Running the Engine

The engine can be called from any async context with a live `aiosqlite.Connection`:

```python
import aiosqlite
from openorbit.pipeline.inference import InferenceEngine

async with aiosqlite.connect("openorbit.db") as conn:
    conn.row_factory = aiosqlite.Row
    engine = InferenceEngine()
    stats = await engine.run(conn)
    print(stats)  # {"events_updated": 5, "rules_applied": 3}
```

It is safe to schedule this as a periodic background job — the engine applies each rule
only if the corresponding flag is not already present.
