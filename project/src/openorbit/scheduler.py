"""Background scheduler for periodic scraping jobs."""

from __future__ import annotations

import importlib
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import openorbit.scrapers  # noqa: F401 — triggers scraper registration
from openorbit.db import get_db, get_osint_sources
from openorbit.scrapers.registry import registry

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
    Registry-registered scrapers not in the DB are also scheduled.
    """
    global _scheduler
    _scheduler = create_scheduler()

    async with get_db() as conn:
        sources = await get_osint_sources(conn, enabled_only=True)

    scheduled_ids: set[str] = set()

    for source in sources:
        interval_hours = source.refresh_interval_hours or 6
        job_id = f"scraper_{source.id}"
        _scheduler.add_job(
            run_scraper_job,
            "interval",
            hours=interval_hours,
            args=[source.scraper_class, source.id],
            id=job_id,
            max_instances=1,
            misfire_grace_time=300,
        )
        scheduled_ids.add(job_id)

    # Also schedule registry scrapers not already covered by a DB source
    db_scraper_classes = {source.scraper_class for source in sources}
    for scraper_cls in registry.get_all():
        module = scraper_cls.__module__
        class_name = scraper_cls.__name__
        class_path = f"{module}.{class_name}"
        if class_path not in db_scraper_classes:
            job_id = f"registry_{scraper_cls.source_name}"
            if job_id not in scheduled_ids:
                _scheduler.add_job(
                    run_scraper_job,
                    "interval",
                    hours=6,
                    args=[class_path, -1],
                    id=job_id,
                    max_instances=1,
                    misfire_grace_time=300,
                )

    _scheduler.start()
    logger.info(f"Scheduler started with {len(sources)} DB job(s)")


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
