"""Scraper registry — singleton that maps source_name to scraper class."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openorbit.scrapers.base import BaseScraper


class ScraperRegistry:
    """Singleton registry for all registered scraper classes."""

    def __init__(self) -> None:
        """Initialize with empty registry."""
        self._scrapers: dict[str, type[BaseScraper]] = {}

    def register(self, scraper_cls: type[BaseScraper]) -> None:
        """Register a scraper class by its source_name.

        Args:
            scraper_cls: Concrete scraper class to register.
        """
        self._scrapers[scraper_cls.source_name] = scraper_cls

    def get_all(self) -> list[type[BaseScraper]]:
        """Return all registered scraper classes.

        Returns:
            List of registered scraper classes.
        """
        return list(self._scrapers.values())

    def get_by_name(self, name: str) -> type[BaseScraper] | None:
        """Return a scraper class by source_name, or None if not found.

        Args:
            name: The source_name to look up.

        Returns:
            The scraper class, or None if not registered.
        """
        return self._scrapers.get(name)


# Module-level singleton
registry = ScraperRegistry()
