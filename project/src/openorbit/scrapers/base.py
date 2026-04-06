"""Base class for OSINT scrapers.

Defines the abstract interface that all scrapers must implement.
Concrete subclasses are auto-registered in the global ScraperRegistry
via __init_subclass__.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import ClassVar

from openorbit.models.db import LaunchEventCreate


class BaseScraper(ABC):
    """Abstract base class for all OSINT scrapers.

    Subclasses must define:
        - source_name: ClassVar[str] — unique scraper identifier
        - source_url: ClassVar[str] — base URL of the data source

    Concrete (non-abstract) subclasses are auto-registered in the global
    registry via __init_subclass__.
    """

    source_name: ClassVar[str]
    source_url: ClassVar[str]
    source_tier: ClassVar[int] = 1
    evidence_type: ClassVar[str] = "official_schedule"

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "source_name") or not isinstance(
            getattr(cls, "source_name", None), str
        ):
            raise TypeError(f"{cls.__name__} must define source_name: ClassVar[str]")
        if not hasattr(cls, "source_url") or not isinstance(
            getattr(cls, "source_url", None), str
        ):
            raise TypeError(f"{cls.__name__} must define source_url: ClassVar[str]")

        # Only register concrete (non-abstract) classes
        if not inspect.isabstract(cls):
            from openorbit.scrapers.registry import registry

            registry.register(cls)

    @abstractmethod
    async def scrape(self) -> dict[str, int]:
        """Scrape data from the configured source.

        Returns:
            Summary dict with keys:
                - total_fetched: Total number of events retrieved
                - new_events: Number of newly created events
                - updated_events: Number of updated events

        Raises:
            Exception: If critical failure occurs (network timeout, DB error, etc.)
        """

    @abstractmethod
    async def parse(self, raw_data: str) -> list[LaunchEventCreate]:
        """Parse raw API/HTML response into LaunchEventCreate models.

        Args:
            raw_data: Raw JSON or HTML string from the source.

        Returns:
            List of parsed LaunchEventCreate models.

        Raises:
            ValueError: If data format is invalid.
        """
