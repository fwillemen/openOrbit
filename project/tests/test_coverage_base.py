"""Tests for scrapers/base.py — Protocol coverage."""

from __future__ import annotations

from openorbit.models.db import LaunchEventCreate
from openorbit.scrapers.base import BaseScraper


class DummyScraper:
    """Concrete implementation of BaseScraper protocol for testing."""

    async def scrape(self) -> dict[str, int]:
        return {"total_fetched": 0, "new_events": 0, "updated_events": 0}

    async def parse(self, raw_data: str) -> list[LaunchEventCreate]:
        return []


async def test_base_scraper_is_protocol() -> None:
    """BaseScraper is a Protocol class."""
    import typing

    assert isinstance(BaseScraper, type)
    # Protocol base should be in MRO or bases
    origin = getattr(BaseScraper, "__bases__", ())
    assert any(b is typing.Protocol or getattr(b, "_is_protocol", False) for b in origin) or getattr(
        BaseScraper, "_is_protocol", False
    )


async def test_dummy_scraper_has_required_methods() -> None:
    """DummyScraper has scrape and parse methods matching the protocol."""
    dummy = DummyScraper()
    assert hasattr(dummy, "scrape")
    assert hasattr(dummy, "parse")
    assert callable(dummy.scrape)
    assert callable(dummy.parse)


async def test_dummy_scraper_scrape_returns_dict() -> None:
    """DummyScraper.scrape() returns a dict with the expected keys."""
    dummy = DummyScraper()
    result = await dummy.scrape()
    assert isinstance(result, dict)
    assert "total_fetched" in result
    assert "new_events" in result
    assert "updated_events" in result


async def test_dummy_scraper_parse_returns_list() -> None:
    """DummyScraper.parse() returns a list of LaunchEventCreate."""
    dummy = DummyScraper()
    result = await dummy.parse('{"data": []}')
    assert isinstance(result, list)


async def test_base_scraper_module_docstring() -> None:
    """The base module has a docstring."""
    import openorbit.scrapers.base as base_module

    assert base_module.__doc__ is not None


async def test_base_scraper_class_docstring() -> None:
    """BaseScraper has a docstring."""
    assert BaseScraper.__doc__ is not None


async def test_base_scraper_scrape_docstring() -> None:
    """BaseScraper.scrape has a docstring."""
    assert BaseScraper.scrape.__doc__ is not None


async def test_base_scraper_parse_docstring() -> None:
    """BaseScraper.parse has a docstring."""
    assert BaseScraper.parse.__doc__ is not None
