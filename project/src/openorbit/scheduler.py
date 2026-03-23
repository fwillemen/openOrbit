"""Background scheduler for periodic scraping jobs."""

from __future__ import annotations

import importlib
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from openorbit.db import get_db, get_osint_sources

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def run_scraper_job(scraper_class_path: str, source_id: int) -> None:
    """Run a single scraper job, handling errors gracefully.

    Args:
        scraper_class_path: Dotted Python path to the scraper class.
        source_id: ID of the OSINT source being scraped.
    """
    try:
        module_path, class_name = scraper_class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        scraper_cls = getattr(module, class_name)

        async with get_db() as conn:
            scraper = scraper_cls()
            await scraper.scrape(conn)

        logger.info(f"Scraper job completed for source {source_id}")
    except Exception as e:
        logger.error(f"Scraper job failed for source {source_id}: {e}")
        # Do not re-raise — scheduler continues running


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure an APScheduler AsyncIOScheduler instance.

    Returns:
        Unconfigured AsyncIOScheduler ready for job registration.
    """
    return AsyncIOScheduler()


async def start_scheduler() -> None:
    """Start the background scheduler and register one job per enabled source.

    Reads enabled OSINT sources from the database and schedules each scraper
    using its configured ``refresh_interval_hours`` (default 6 h).
    """
    global _scheduler
    _scheduler = create_scheduler()

    async with get_db() as conn:
        sources = await get_osint_sources(conn, enabled_only=True)

    for source in sources:
        interval_hours = source.refresh_interval_hours or 6
        _scheduler.add_job(
            run_scraper_job,
            "interval",
            hours=interval_hours,
            args=[source.scraper_class, source.id],
            id=f"scraper_{source.id}",
            max_instances=1,
            misfire_grace_time=300,
        )

    _scheduler.start()
    logger.info(f"Scheduler started with {len(sources)} job(s)")


async def stop_scheduler() -> None:
    """Stop the scheduler gracefully.

    Safe to call even if the scheduler has not been started.
    """
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None


def get_scheduler() -> AsyncIOScheduler | None:
    """Return the active scheduler, or None if not started.

    Returns:
        The running AsyncIOScheduler, or None.
    """
    return _scheduler
