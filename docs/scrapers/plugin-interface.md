# Scraper Plugin Interface

openOrbit uses a **plugin architecture** for OSINT data collection. Each data source is
implemented as a concrete subclass of `BaseScraper`. Plugins self-register at import time —
no manual wiring required.

---

## Architecture Overview

```
BaseScraper (ABC)
    │
    ├── auto-registration via __init_subclass__
    │         │
    │         ▼
    │   ScraperRegistry (singleton)
    │         │
    │         ├── SpaceAgencyScraper  (source_name="space_agency")
    │         ├── CommercialScraper   (source_name="commercial")
    │         └── NOTAMSScraper       (source_name="notams")
    │
    └── Scheduler + GET /v1/sources consume registry.get_all()
```

Importing `openorbit.scrapers` (the package) triggers registration of all built-in scrapers.
The `GET /v1/sources` endpoint and the background scheduler both call `registry.get_all()` to
discover scrapers dynamically — adding a new scraper requires no changes outside the
`scrapers/` package.

---

## BaseScraper ABC

**Module:** `openorbit.scrapers.base`

```python
from abc import ABC, abstractmethod
from typing import ClassVar
from openorbit.models.db import LaunchEventCreate


class BaseScraper(ABC):
    source_name: ClassVar[str]   # unique identifier, e.g. "my_source"
    source_url:  ClassVar[str]   # base URL of the data source

    @abstractmethod
    async def scrape(self) -> dict[str, int]: ...

    @abstractmethod
    async def parse(self, raw_data: str) -> list[LaunchEventCreate]: ...
```

### ClassVars

| Attribute | Type | Description |
|-----------|------|-------------|
| `source_name` | `ClassVar[str]` | Unique identifier used as the registry key. Must be a plain `str`. |
| `source_url`  | `ClassVar[str]` | Base URL for the data source (used in `/v1/sources` responses). |

Both ClassVars are **required**. Subclasses that omit either will raise `TypeError` at
class-definition time (enforced by `__init_subclass__`).

### `scrape() -> dict[str, int]`

Entry point called by the scheduler. Fetches remote data, persists new/updated events to
the database, and returns a summary:

```python
{
    "total_fetched":   42,
    "new_events":      10,
    "updated_events":   3,
}
```

Raise any `Exception` on unrecoverable failure; the scheduler will log it and continue with
the next scraper.

### `parse(raw_data: str) -> list[LaunchEventCreate]`

Converts raw API JSON or HTML into a list of `LaunchEventCreate` Pydantic models.
Raise `ValueError` if the payload format is invalid.

---

## ScraperRegistry API

**Module:** `openorbit.scrapers.registry`

The module exposes a ready-made singleton:

```python
from openorbit.scrapers.registry import registry
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `register` | `(scraper_cls: type[BaseScraper]) -> None` | Add a scraper class keyed by `source_name`. Called automatically by `__init_subclass__`; rarely needed directly. |
| `get_all` | `() -> list[type[BaseScraper]]` | Return all registered scraper classes. |
| `get_by_name` | `(name: str) -> type[BaseScraper] \| None` | Look up a scraper by `source_name`; returns `None` if not found. |

---

## Auto-Registration via `__init_subclass__`

`BaseScraper.__init_subclass__` fires **at class-definition time** for every concrete
(non-abstract) subclass. It:

1. Validates that `source_name` and `source_url` are defined as plain `str` values.
2. Calls `registry.register(cls)` to add the class to the singleton.

```python
# happens automatically — no manual call needed
class MyScraper(BaseScraper):
    source_name = "my_source"
    source_url  = "https://example.com/launches"
    ...
```

Abstract intermediate classes (those with remaining abstract methods) are **not**
registered, so you can safely create abstract mixins.

---

## Creating a New Scraper — Step-by-Step

### 1. Create the module

```
src/openorbit/scrapers/my_source.py
```

### 2. Implement the class

```python
"""my_source scraper — fetches launch data from Example.com."""

from __future__ import annotations

import httpx

from openorbit.models.db import LaunchEventCreate
from openorbit.scrapers.base import BaseScraper


class MySourceScraper(BaseScraper):
    """Scraper for Example.com launch data."""

    source_name = "my_source"
    source_url  = "https://example.com/api/launches"

    async def scrape(self) -> dict[str, int]:
        """Fetch and persist launch events from Example.com."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(self.source_url)
            response.raise_for_status()

        events = await self.parse(response.text)

        # persist to DB (use your session/repo pattern)
        new_count = 0
        for event in events:
            # ... upsert logic ...
            new_count += 1

        return {
            "total_fetched":  len(events),
            "new_events":     new_count,
            "updated_events": 0,
        }

    async def parse(self, raw_data: str) -> list[LaunchEventCreate]:
        """Parse JSON response from Example.com."""
        import json

        payload = json.loads(raw_data)
        results: list[LaunchEventCreate] = []
        for item in payload.get("launches", []):
            results.append(
                LaunchEventCreate(
                    source=self.source_name,
                    mission_name=item["name"],
                    launch_date=item["date"],
                    # ... other fields ...
                )
            )
        return results
```

### 3. Register by importing in `scrapers/__init__.py`

```python
# src/openorbit/scrapers/__init__.py

from openorbit.scrapers import commercial, my_source, notams, space_agency  # noqa: F401
```

Adding the import here is sufficient — `__init_subclass__` does the rest.

### 4. Verify registration

```bash
cd project
python - <<'EOF'
import openorbit.scrapers  # triggers registration
from openorbit.scrapers.registry import registry
print([s.source_name for s in registry.get_all()])
EOF
```

Expected output includes `"my_source"`.

### 5. Test

Create `tests/scrapers/test_my_source.py` following the existing test patterns
(mock `httpx.AsyncClient`, verify `scrape()` returns the expected summary dict, and
`parse()` returns correctly typed `LaunchEventCreate` instances).

---

## Built-in Scrapers

| Class | source_name | source_url |
|-------|-------------|------------|
| `SpaceAgencyScraper` | `space_agency` | NASA/ESA feeds |
| `CommercialScraper` | `commercial` | SpaceX / RocketLab feeds |
| `NOTAMSScraper` | `notams` | FAA NOTAM API |

---

## Integration Points

| Consumer | How it uses the registry |
|----------|--------------------------|
| `GET /v1/sources` | Calls `registry.get_all()` to list all available sources |
| Background scheduler | Iterates `registry.get_all()`, instantiates each class, calls `scrape()` |
