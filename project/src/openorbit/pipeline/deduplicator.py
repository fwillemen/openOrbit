"""Multi-source event deduplication and merging for the openOrbit pipeline."""

from __future__ import annotations

import logging
import time
from datetime import datetime

import aiosqlite

from openorbit.pipeline.aliases import PROVIDER_ALIASES

logger = logging.getLogger(__name__)

# Two events are "near" if their launch dates differ by at most this many days.
DATE_WINDOW_DAYS = 3


def _normalize_provider(provider: str) -> str:
    """Resolve a provider string to its canonical alias form.

    Args:
        provider: Raw provider name.

    Returns:
        Canonical provider name (lower-cased key resolved via PROVIDER_ALIASES,
        or the stripped original if no alias exists).
    """
    key = provider.strip().lower()
    return PROVIDER_ALIASES.get(key, provider.strip())


def _normalize_location(location: str | None) -> str:
    """Normalise a location string for comparison.

    Args:
        location: Raw location string or None.

    Returns:
        Lower-cased, stripped string; empty string when input is None.
    """
    return (location or "").strip().lower()


def _events_are_duplicates(e1: dict[str, object], e2: dict[str, object]) -> bool:
    """Return True when two event dicts represent the same real-world launch.

    Duplicate criteria (all must hold):
    - Same provider after alias resolution.
    - Launch dates within DATE_WINDOW_DAYS of each other.
    - Same launch location after normalisation (both empty counts as matching).

    Args:
        e1: First event dict with keys ``provider``, ``launch_date``, ``location``.
        e2: Second event dict with the same keys.

    Returns:
        True if the events should be merged.
    """
    if _normalize_provider(str(e1.get("provider", ""))) != _normalize_provider(
        str(e2.get("provider", ""))
    ):
        return False

    try:
        date1 = datetime.fromisoformat(str(e1.get("launch_date", "")))
        date2 = datetime.fromisoformat(str(e2.get("launch_date", "")))
    except ValueError:
        return False

    if abs((date1 - date2).days) > DATE_WINDOW_DAYS:
        return False

    raw_loc1 = e1.get("location")
    raw_loc2 = e2.get("location")
    loc1 = _normalize_location(raw_loc1 if isinstance(raw_loc1, str) else None)
    loc2 = _normalize_location(raw_loc2 if isinstance(raw_loc2, str) else None)
    return not (loc1 and loc2 and loc1 != loc2)


def _calculate_confidence(num_sources: int, base_score: float = 0.4) -> int:
    """Calculate confidence score based on the number of corroborating sources.

    Formula: ``min(0.3 * num_sources + base_score, 1.0)``
    Result is scaled to the DB range 0-100 (integer).

    Args:
        num_sources: Number of distinct sources that reference this event.
        base_score: Base confidence when only a single source exists (default 0.4).

    Returns:
        Integer confidence score in the range [0, 100].
    """
    score = min(0.3 * num_sources + base_score, 1.0)
    return round(score * 100)


async def deduplicate_and_merge(conn: aiosqlite.Connection) -> dict[str, int]:
    """Run a deduplication pass over all launch events in the database.

    For each pair of events that meet the duplicate criteria:

    1. Keep the event with the lexicographically earlier ``created_at``
       (the "canonical" record).
    2. Reassign all ``event_attributions`` rows from the duplicate to the
       canonical slug, skipping any that would violate the unique constraint.
    3. Recalculate ``confidence_score`` for the canonical event based on the
       merged distinct-source count.
    4. Delete the duplicate ``launch_events`` row.

    The operation is idempotent: running it twice on the same database
    produces the same result as running it once.

    Args:
        conn: Active aiosqlite database connection.

    Returns:
        A dict with keys:

        - ``merged_count``: Number of duplicate events removed.
        - ``elapsed_ms``: Wall-clock time in milliseconds for the full pass.
    """
    start = time.monotonic()
    merged = 0

    async with conn.execute(
        "SELECT slug, provider, launch_date, location "
        "FROM launch_events ORDER BY created_at ASC"
    ) as cursor:
        events: list[dict[str, object]] = [dict(row) for row in await cursor.fetchall()]

    processed: set[str] = set()

    for i, event in enumerate(events):
        slug = str(event["slug"])
        if slug in processed:
            continue

        for other in events[i + 1 :]:
            other_slug = str(other["slug"])
            if other_slug in processed:
                continue

            if not _events_are_duplicates(event, other):
                continue

            # Reassign attributions from duplicate to canonical.
            # Fetch scrape_record_ids already attributed to the canonical slug
            # to avoid unique-constraint violations.
            async with conn.execute(
                "SELECT scrape_record_id FROM event_attributions WHERE event_slug = ?",
                (slug,),
            ) as cur:
                existing_ids: set[int] = {row[0] for row in await cur.fetchall()}

            async with conn.execute(
                "SELECT id, scrape_record_id, attributed_at "
                "FROM event_attributions WHERE event_slug = ?",
                (other_slug,),
            ) as cur:
                dup_attributions = await cur.fetchall()

            for attr_row in dup_attributions:
                attr_id, scrape_record_id, attributed_at = attr_row
                if scrape_record_id in existing_ids:
                    # Skip duplicates that would violate the unique constraint.
                    await conn.execute(
                        "DELETE FROM event_attributions WHERE id = ?", (attr_id,)
                    )
                else:
                    await conn.execute(
                        "UPDATE event_attributions SET event_slug = ? WHERE id = ?",
                        (slug, attr_id),
                    )
                    existing_ids.add(scrape_record_id)

            # Recalculate confidence based on merged distinct-source count.
            async with conn.execute(
                "SELECT COUNT(DISTINCT scrape_record_id) "
                "FROM event_attributions WHERE event_slug = ?",
                (slug,),
            ) as cur:
                row = await cur.fetchone()
                num_sources = row[0] if row else 1

            new_confidence = _calculate_confidence(max(num_sources, 1))
            await conn.execute(
                "UPDATE launch_events SET confidence_score = ? WHERE slug = ?",
                (new_confidence, slug),
            )

            # Delete the duplicate record.
            await conn.execute(
                "DELETE FROM launch_events WHERE slug = ?", (other_slug,)
            )
            processed.add(other_slug)
            merged += 1

    await conn.commit()
    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info("Deduplication complete: merged=%d, elapsed_ms=%d", merged, elapsed_ms)
    return {"merged_count": merged, "elapsed_ms": elapsed_ms}
