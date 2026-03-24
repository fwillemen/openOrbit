"""Tests for BaseScraper ABC and ScraperRegistry."""

from __future__ import annotations

import pytest

from openorbit.scrapers.base import BaseScraper
from openorbit.scrapers.registry import ScraperRegistry
from openorbit.models.db import LaunchEventCreate


# ---------------------------------------------------------------------------
# Minimal concrete stub used throughout this test module
# ---------------------------------------------------------------------------

class ConcreteTestScraper(BaseScraper):
    """Minimal concrete scraper for testing auto-registration."""

    source_name: str = "test_scraper"
    source_url: str = "https://example.com/"

    async def scrape(self) -> dict[str, int]:
        return {"total_fetched": 0, "new_events": 0, "updated_events": 0}

    async def parse(self, raw_data: str) -> list[LaunchEventCreate]:
        return []


# ---------------------------------------------------------------------------
# BaseScraper tests
# ---------------------------------------------------------------------------


def test_base_scraper_is_abstract() -> None:
    """BaseScraper cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseScraper()  # type: ignore[abstract]


def test_concrete_subclass_auto_registers() -> None:
    """ConcreteTestScraper is auto-registered upon class definition."""
    from openorbit.scrapers.registry import registry

    registered = registry.get_by_name("test_scraper")
    assert registered is ConcreteTestScraper


def test_missing_source_name_raises_type_error() -> None:
    """Defining a subclass without source_name raises TypeError."""
    with pytest.raises(TypeError, match="source_name"):

        class _BadScraper(BaseScraper):
            source_url: str = "https://example.com/"

            async def scrape(self) -> dict[str, int]:
                return {}

            async def parse(self, raw_data: str) -> list[LaunchEventCreate]:
                return []


def test_missing_source_url_raises_type_error() -> None:
    """Defining a subclass without source_url raises TypeError."""
    with pytest.raises(TypeError, match="source_url"):

        class _BadScraper(BaseScraper):
            source_name: str = "missing_url_scraper"

            async def scrape(self) -> dict[str, int]:
                return {}

            async def parse(self, raw_data: str) -> list[LaunchEventCreate]:
                return []


# ---------------------------------------------------------------------------
# ScraperRegistry tests  (use a fresh isolated registry for each test)
# ---------------------------------------------------------------------------


@pytest.fixture()
def fresh_registry() -> ScraperRegistry:
    """Return a new, empty ScraperRegistry not tied to the global singleton."""
    return ScraperRegistry()


def test_registry_get_all_returns_registered(fresh_registry: ScraperRegistry) -> None:
    """get_all() returns all manually registered scrapers."""
    fresh_registry.register(ConcreteTestScraper)
    assert ConcreteTestScraper in fresh_registry.get_all()


def test_registry_get_by_name_found(fresh_registry: ScraperRegistry) -> None:
    """get_by_name() returns the class when it is registered."""
    fresh_registry.register(ConcreteTestScraper)
    result = fresh_registry.get_by_name("test_scraper")
    assert result is ConcreteTestScraper


def test_registry_get_by_name_not_found(fresh_registry: ScraperRegistry) -> None:
    """get_by_name() returns None for an unknown name."""
    result = fresh_registry.get_by_name("does_not_exist")
    assert result is None


def test_registry_register_idempotent(fresh_registry: ScraperRegistry) -> None:
    """Registering the same scraper twice is idempotent (no duplication)."""
    fresh_registry.register(ConcreteTestScraper)
    fresh_registry.register(ConcreteTestScraper)
    matches = [c for c in fresh_registry.get_all() if c is ConcreteTestScraper]
    assert len(matches) == 1


def test_registry_get_all_empty(fresh_registry: ScraperRegistry) -> None:
    """get_all() returns an empty list when nothing is registered."""
    assert fresh_registry.get_all() == []


def test_concrete_scraper_can_be_instantiated() -> None:
    """ConcreteTestScraper can be instantiated normally."""
    scraper = ConcreteTestScraper()
    assert scraper.source_name == "test_scraper"
    assert scraper.source_url == "https://example.com/"
