# Data Normalization Pipeline

The normalization pipeline converts raw scraper dictionaries into validated, canonical
`LaunchEvent` models before any data reaches the database.

---

## Overview

```
Raw scraper dict
      │
      ▼
normalize(raw, source)
  ├── 1. Resolve provider alias     (PROVIDER_ALIASES)
  ├── 2. Enrich pad metadata        (PAD_LOCATIONS → lat/lon/location)
  └── 3. Validate with Pydantic v2  (LaunchEvent)
      │
      ▼
LaunchEvent  ──or──  NormalizationError
```

All pipeline code lives in `src/openorbit/pipeline/`:

| Module | Purpose |
|--------|---------|
| `normalizer.py` | `normalize()` entry-point function |
| `aliases.py` | `PROVIDER_ALIASES` and `PAD_LOCATIONS` lookup tables |
| `exceptions.py` | `NormalizationError` exception |
| `src/openorbit/models/launch_event.py` | `LaunchEvent` Pydantic model |

---

## `LaunchEvent` Model

`LaunchEvent` is a **Pydantic v2** model that represents a single canonical launch record
produced by the pipeline. It is separate from the database model (`openorbit.models.db`).

```python
from openorbit.models.launch_event import LaunchEvent
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | — | Human-readable event name (required) |
| `launch_date` | `datetime` | — | UTC launch datetime (required) |
| `launch_date_precision` | `"exact" \| "day" \| "week" \| "month"` | `"day"` | Confidence in date accuracy |
| `provider` | `str` | — | Canonical provider name (required) |
| `vehicle` | `str \| None` | `None` | Launch vehicle identifier |
| `location` | `str \| None` | `None` | Human-readable launch location |
| `pad` | `str \| None` | `None` | Launch pad identifier (e.g. `"LC-39A"`) |
| `launch_type` | `"civilian" \| "military" \| "public_report" \| "unknown"` | `"unknown"` | Mission classification |
| `status` | `"scheduled" \| "success" \| "failure" \| "unknown"` | `"unknown"` | Launch outcome |
| `confidence_score` | `float` | `0.4` | Source confidence in `[0.0, 1.0]` |
| `lat` | `float \| None` | `None` | Pad latitude (auto-filled from `PAD_LOCATIONS`) |
| `lon` | `float \| None` | `None` | Pad longitude (auto-filled from `PAD_LOCATIONS`) |

### Validators

#### `parse_launch_date`

Accepts multiple date formats and always returns a **timezone-aware UTC datetime**:

| Input type | Examples |
|------------|---------|
| `datetime` | `datetime(2025, 6, 1, tzinfo=UTC)` |
| `int` / `float` | Unix timestamp `1748736000` |
| ISO 8601 string | `"2025-06-01T12:00:00Z"`, `"2025-06-01"` |
| Long-form string | `"June 1, 2025"`, `"June 1 2025"` |

Raises `NormalizationError` if no format matches.

#### `normalize_launch_type`

Maps raw provider strings to canonical values before validation:

| Raw input | Canonical value |
|-----------|----------------|
| `"commercial"`, `"government"`, `"civil"`, `"civilian"` | `"civilian"` |
| `"mil"`, `"military"` | `"military"` |
| `"public_report"` | `"public_report"` |
| anything else | `"unknown"` |

---

## `normalize()` Function

```python
from openorbit.pipeline.normalizer import normalize
```

### Signature

```python
def normalize(raw: dict[str, object], source: str) -> LaunchEvent
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `raw` | `dict[str, object]` | Raw scraper output dictionary |
| `source` | `str` | Name of the OSINT source (used in error messages) |

### Returns

A fully validated `LaunchEvent` instance.

### Raises

`NormalizationError` — if the raw data cannot be coerced into a valid `LaunchEvent`.

### Basic Example

```python
from openorbit.pipeline.normalizer import normalize

raw = {
    "name": "Falcon 9 — Starlink 6-10",
    "launch_date": "2025-06-01T14:00:00Z",
    "provider": "space exploration technologies",
    "vehicle": "Falcon 9",
    "pad": "LC-39A",
    "status": "scheduled",
    "launch_type": "commercial",
}

event = normalize(raw, source="launch_library")

print(event.provider)           # "SpaceX"
print(event.location)           # "Kennedy Space Center, FL, USA"
print(event.lat, event.lon)     # 28.608, -80.6043
print(event.launch_type)        # "civilian"
```

### Unix Timestamp Example

```python
raw = {
    "name": "Soyuz MS-28",
    "launch_date": 1748736000,        # Unix timestamp
    "provider": "Roscosmos State Corporation",
    "pad": "Site 1/5",
}

event = normalize(raw, source="spaceflight_now")
print(event.location)   # "Baikonur Cosmodrome, Kazakhstan"
```

### Error Handling Example

```python
from openorbit.pipeline.exceptions import NormalizationError

try:
    event = normalize({"name": "Bad Event", "launch_date": "not-a-date"}, source="test")
except NormalizationError as exc:
    print(f"Skipping bad record: {exc}")
    # [test] Failed to normalize launch event: Cannot parse launch_date: 'not-a-date'
```

---

## `NormalizationError` Exception

```python
from openorbit.pipeline.exceptions import NormalizationError
```

`NormalizationError` is a subclass of `ValueError`. It is raised when:

- `launch_date` cannot be parsed into a datetime.
- A required field is missing or of the wrong type.
- Pydantic validation fails for any other field constraint.

The message always includes the `source` name so log-based triage is straightforward:

```
[launch_library] Failed to normalize launch event: Cannot parse launch_date: 'TBD'
```

---

## Provider Aliases

The `PROVIDER_ALIASES` dict maps long-form or alternative provider names to canonical
short names. Matching is **case-insensitive** (keys are lower-cased at lookup time).

| Raw provider string | Canonical name |
|--------------------|---------------|
| `"space exploration technologies"` | `SpaceX` |
| `"space exploration technologies corp"` | `SpaceX` |
| `"national aeronautics and space administration"` | `NASA` |
| `"united launch alliance"` | `ULA` |
| `"rocket lab usa"` | `Rocket Lab` |
| `"china aerospace science and technology corporation"` | `CASC` |
| `"roscosmos state corporation"` | `Roscosmos` |
| `"arianespace sa"` | `Arianespace` |
| `"blue origin llc"` | `Blue Origin` |
| `"northrop grumman innovation systems"` | `Northrop Grumman` |
| `"virgin orbit llc"` | `Virgin Orbit` |

Providers not found in the table are left unchanged.

---

## Pad Locations

The `PAD_LOCATIONS` dict maps pad identifiers to geographic metadata. When a raw record
contains a matching `pad` value, `normalize()` automatically fills `lat`, `lon`, and
`location` if they are not already set.

| Pad ID | Location | Latitude | Longitude |
|--------|---------|----------|-----------|
| `LC-39A` | Kennedy Space Center, FL, USA | 28.6080 | −80.6043 |
| `SLC-40` | Cape Canaveral SFS, FL, USA | 28.5620 | −80.5773 |
| `SLC-4E` | Vandenberg SFB, CA, USA | 34.6321 | −120.6110 |
| `Site 1/5` | Baikonur Cosmodrome, Kazakhstan | 45.9200 | 63.3420 |
| `LP-0A` | Wallops Island, VA, USA | 37.8329 | −75.4880 |
| `SLC-8` | Vandenberg SFB, CA, USA | 34.6400 | −120.5950 |
| `LC-1` | Kapustin Yar, Russia | 48.5170 | 45.7640 |
| `ELA-3` | Guiana Space Centre, French Guiana | 5.2390 | −52.7680 |
| `LC-200/39` | Cape Canaveral SFS, FL, USA | 28.4756 | −80.5290 |
| `LA-0B` | Alcântara, Maranhão, Brazil | −2.3736 | −44.3760 |
| `Starbase` | Starbase, TX, USA | 25.9972 | −97.1561 |

---

## Extending Aliases & Pad Locations

### Adding a Provider Alias

Open `src/openorbit/pipeline/aliases.py` and add an entry to `PROVIDER_ALIASES`:

```python
PROVIDER_ALIASES: dict[str, str] = {
    # existing entries …
    "isro": "ISRO",  # Indian Space Research Organisation short-form
}
```

Keys **must be lower-cased**; the lookup in `normalize()` calls `.lower()` automatically.

### Adding a Pad Location

Add an entry to `PAD_LOCATIONS` in the same file:

```python
PAD_LOCATIONS: dict[str, dict[str, float | str]] = {
    # existing entries …
    "SLC-37B": {
        "lat": 28.5312,
        "lon": -80.5656,
        "location": "Cape Canaveral SFS, FL, USA",
    },
}
```

The pad key must match the `pad` field value **exactly** (case-sensitive) as it arrives
from the scraper. No import changes are required — `normalizer.py` imports the tables
directly from `aliases.py`.
