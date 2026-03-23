"""Unit tests for the background scheduler module."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import openorbit.config
import openorbit.db as db_module
import openorbit.scheduler as scheduler_module
from openorbit.db import close_db, init_db
from openorbit.models.db import OSINTSource
from openorbit.scheduler import (
    create_scheduler,
    get_scheduler,
    run_scraper_job,
    start_scheduler,
    stop_scheduler,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(**kwargs: object) -> OSINTSource:
    defaults: dict[str, object] = {
        "id": 1,
        "name": "Test Source",
        "url": "https://example.com",
        "scraper_class": "openorbit.scrapers.commercial.CommercialLaunchScraper",
        "enabled": True,
        "last_scraped_at": None,
        "refresh_interval_hours": 6,
    }
    defaults.update(kwargs)
    return OSINTSource(**defaults)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
async def reset_scheduler() -> AsyncIterator[None]:
    """Ensure the scheduler module global is reset between tests."""
    scheduler_module._scheduler = None
    yield
    if scheduler_module._scheduler is not None:
        try:
            if scheduler_module._scheduler.running:
                scheduler_module._scheduler.shutdown(wait=False)
        except Exception:
            pass
        scheduler_module._scheduler = None


@pytest.fixture
async def temp_db() -> AsyncIterator[None]:
    """Spin up a fresh in-process DB and tear it down afterwards."""
    db_file = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
    openorbit.config._settings = None
    db_module._db_connection = None

    await init_db()
    yield

    await close_db()
    if os.path.exists(db_file):
        os.unlink(db_file)
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
    openorbit.config._settings = None


# ---------------------------------------------------------------------------
# create_scheduler
# ---------------------------------------------------------------------------


def test_create_scheduler_returns_async_io_scheduler() -> None:
    """create_scheduler() must return an AsyncIOScheduler instance."""
    sched = create_scheduler()
    assert isinstance(sched, AsyncIOScheduler)


# ---------------------------------------------------------------------------
# get_scheduler
# ---------------------------------------------------------------------------


def test_get_scheduler_returns_none_before_start() -> None:
    """get_scheduler() returns None when the scheduler has not been started."""
    assert get_scheduler() is None


# ---------------------------------------------------------------------------
# run_scraper_job — success path
# ---------------------------------------------------------------------------


async def test_run_scraper_job_calls_scraper(temp_db: None) -> None:
    """run_scraper_job() dynamically imports the scraper and calls scrape()."""
    mock_scraper_instance = AsyncMock()
    mock_scraper_cls = MagicMock(return_value=mock_scraper_instance)

    with patch("importlib.import_module") as mock_import:
        mock_module = MagicMock()
        mock_module.MockScraper = mock_scraper_cls
        mock_import.return_value = mock_module

        await run_scraper_job("some.module.MockScraper", source_id=1)

    mock_import.assert_called_once_with("some.module")
    mock_scraper_cls.assert_called_once()
    mock_scraper_instance.scrape.assert_awaited_once()


# ---------------------------------------------------------------------------
# run_scraper_job — error path
# ---------------------------------------------------------------------------


async def test_run_scraper_job_logs_error_and_does_not_reraise(
    temp_db: None,
) -> None:
    """run_scraper_job() catches exceptions, logs them, and does not re-raise."""
    with patch("importlib.import_module", side_effect=ImportError("no module")):
        # Must NOT raise
        await run_scraper_job("bad.module.Scraper", source_id=99)


async def test_run_scraper_job_scraper_exception_does_not_reraise(
    temp_db: None,
) -> None:
    """run_scraper_job() swallows scraper.scrape() exceptions."""
    mock_scraper_instance = AsyncMock()
    mock_scraper_instance.scrape.side_effect = RuntimeError("network down")
    mock_scraper_cls = MagicMock(return_value=mock_scraper_instance)

    with patch("importlib.import_module") as mock_import:
        mock_module = MagicMock()
        mock_module.BrokenScraper = mock_scraper_cls
        mock_import.return_value = mock_module

        # Must NOT raise
        await run_scraper_job("some.module.BrokenScraper", source_id=5)


# ---------------------------------------------------------------------------
# start_scheduler / stop_scheduler / get_scheduler
# ---------------------------------------------------------------------------


async def test_start_scheduler_with_no_sources(temp_db: None) -> None:
    """start_scheduler() succeeds when there are no enabled sources."""
    with patch(
        "openorbit.scheduler.get_osint_sources",
        new=AsyncMock(return_value=[]),
    ):
        await start_scheduler()

    sched = get_scheduler()
    assert sched is not None
    assert sched.running


async def test_start_scheduler_registers_jobs(temp_db: None) -> None:
    """start_scheduler() registers one job per enabled source."""
    sources = [_make_source(id=1), _make_source(id=2, name="Source2")]

    with patch(
        "openorbit.scheduler.get_osint_sources",
        new=AsyncMock(return_value=sources),
    ):
        await start_scheduler()

    sched = get_scheduler()
    assert sched is not None
    job_ids = {job.id for job in sched.get_jobs()}
    assert "scraper_1" in job_ids
    assert "scraper_2" in job_ids


async def test_stop_scheduler_sets_none(temp_db: None) -> None:
    """stop_scheduler() shuts down the scheduler and sets global to None."""
    with patch(
        "openorbit.scheduler.get_osint_sources",
        new=AsyncMock(return_value=[]),
    ):
        await start_scheduler()

    assert get_scheduler() is not None
    await stop_scheduler()
    assert get_scheduler() is None


async def test_stop_scheduler_safe_when_not_started() -> None:
    """stop_scheduler() is idempotent when called before start."""
    await stop_scheduler()  # must not raise
    assert get_scheduler() is None


async def test_get_scheduler_returns_instance_after_start(temp_db: None) -> None:
    """get_scheduler() returns the scheduler after start_scheduler() is called."""
    with patch(
        "openorbit.scheduler.get_osint_sources",
        new=AsyncMock(return_value=[]),
    ):
        await start_scheduler()

    assert isinstance(get_scheduler(), AsyncIOScheduler)
