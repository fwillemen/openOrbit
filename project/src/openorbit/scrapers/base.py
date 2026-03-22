"""Base protocol for OSINT scrapers.

Defines the interface that all scrapers must implement.
Future scrapers (military, social media) will implement this protocol.
"""

from __future__ import annotations

from typing import Protocol

from openorbit.models.db import LaunchEventCreate


class BaseScraper(Protocol):
    """Protocol defining the interface for all OSINT scrapers.

    All concrete scrapers must implement the scrape() method
    that fetches and parses data from their respective sources.
    """

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
        ...

    async def parse(self, raw_data: str) -> list[LaunchEventCreate]:
        """Parse raw API/HTML response into LaunchEventCreate models.

        Args:
            raw_data: Raw JSON or HTML string from the source.

        Returns:
            List of parsed LaunchEventCreate models.

        Raises:
            ValueError: If data format is invalid.
        """
        ...
