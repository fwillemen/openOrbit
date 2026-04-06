"""Inference engine for multi-source correlation and pattern detection.

Applies heuristic rules to launch events stored in the database, annotating
each event with a list of inference flags and adjusting confidence scores.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta

import aiosqlite

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in kilometres.

    Args:
        lat1: Latitude of point 1 in degrees.
        lon1: Longitude of point 1 in degrees.
        lat2: Latitude of point 2 in degrees.
        lon2: Longitude of point 2 in degrees.

    Returns:
        Distance in kilometres.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class InferenceEngine:
    """Apply inference rules to annotate launch events with flags.

    Rules implemented:
    - ``multi_source_corroboration``: event confirmed by ≥2 distinct source
      categories increases confidence by 0.2.
    - ``pad_reuse_pattern``: another event from the same pad occurred within
      the previous 30 days.
    - ``notam_cluster``: ≥2 NOTAM-sourced events exist within the same 7-day
      window around this event.
    """

    async def run(self, conn: aiosqlite.Connection) -> dict[str, int]:
        """Run all inference rules against DB events.

        Args:
            conn: Active aiosqlite database connection.

        Returns:
            Dict with keys ``events_updated`` and ``rules_applied``.
        """
        events_updated = 0
        rules_applied = 0

        # Load all events.
        async with conn.execute(
            "SELECT slug, name, provider, launch_date, location, pad, "
            "confidence_score, inference_flags, launch_type "
            "FROM launch_events"
        ) as cursor:
            rows = [dict(row) for row in await cursor.fetchall()]

        for event in rows:
            flags: list[str] = json.loads(event.get("inference_flags") or "[]")
            original_flags = set(flags)
            original_confidence = float(event.get("confidence_score") or 40.0)
            new_confidence = original_confidence

            # Rule 1: multi_source_corroboration
            num_sources = await self._count_distinct_sources(conn, event["slug"])
            if num_sources >= 2 and "multi_source_corroboration" not in flags:
                flags.append("multi_source_corroboration")
                new_confidence = min(new_confidence + 20.0, 100.0)
                rules_applied += 1

            # Rule 2: historical_pad_pattern
            if event.get("pad"):
                pad_reuse_count = await self._count_recent_pad_events(
                    conn, event["pad"], event["slug"], event.get("launch_date", "")
                )
                if pad_reuse_count > 0 and "pad_reuse_pattern" not in flags:
                    flags.append("pad_reuse_pattern")
                    rules_applied += 1

            # Rule 3: notam_cluster_signal
            notam_count = await self._count_nearby_notam_events(
                conn, event["slug"], event.get("launch_date", "")
            )
            if notam_count >= 2 and "notam_cluster" not in flags:
                flags.append("notam_cluster")
                rules_applied += 1

            # Write back only if something changed.
            if set(flags) != original_flags or new_confidence != original_confidence:
                await conn.execute(
                    "UPDATE launch_events SET inference_flags = ?, confidence_score = ? WHERE slug = ?",
                    (json.dumps(flags), new_confidence, event["slug"]),
                )
                events_updated += 1

        await conn.commit()
        logger.info(
            "Inference complete: events_updated=%d, rules_applied=%d",
            events_updated,
            rules_applied,
        )
        return {"events_updated": events_updated, "rules_applied": rules_applied}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _count_distinct_sources(
        self, conn: aiosqlite.Connection, slug: str
    ) -> int:
        """Return the number of distinct OSINT sources attributing this event.

        Args:
            conn: Database connection.
            slug: Launch event slug.

        Returns:
            Count of distinct source IDs in event_attributions.
        """
        async with conn.execute(
            """SELECT COUNT(DISTINCT rr.source_id)
               FROM event_attributions ea
               JOIN raw_scrape_records rr ON rr.id = ea.scrape_record_id
               WHERE ea.event_slug = ?""",
            (slug,),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def _count_recent_pad_events(
        self,
        conn: aiosqlite.Connection,
        pad: str,
        exclude_slug: str,
        launch_date_str: str,
    ) -> int:
        """Count events from the same pad within 30 days before this event.

        Args:
            conn: Database connection.
            pad: Launch pad identifier.
            exclude_slug: Slug of the current event to exclude from count.
            launch_date_str: ISO 8601 launch date of the current event.

        Returns:
            Number of matching events (positive indicates pad reuse).
        """
        try:
            event_dt = datetime.fromisoformat(str(launch_date_str))
        except (ValueError, TypeError):
            return 0

        thirty_days_ago = (event_dt - timedelta(days=30)).isoformat()
        async with conn.execute(
            "SELECT COUNT(*) FROM launch_events "
            "WHERE pad = ? AND slug != ? AND launch_date >= ? AND launch_date < ?",
            (pad, exclude_slug, thirty_days_ago, event_dt.isoformat()),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def _count_nearby_notam_events(
        self,
        conn: aiosqlite.Connection,
        exclude_slug: str,
        launch_date_str: str,
    ) -> int:
        """Count NOTAM-sourced events in a ±3-day window around this event.

        An event is NOTAM-sourced if it has an attribution via a source whose
        name contains 'NOTAM' (case-insensitive).

        Args:
            conn: Database connection.
            exclude_slug: Slug of the current event to exclude.
            launch_date_str: ISO 8601 launch date of the current event.

        Returns:
            Count of NOTAM-sourced events in the time window.
        """
        try:
            event_dt = datetime.fromisoformat(str(launch_date_str))
        except (ValueError, TypeError):
            return 0

        week_start = (event_dt - timedelta(days=3)).isoformat()
        week_end = (event_dt + timedelta(days=4)).isoformat()

        async with conn.execute(
            """SELECT COUNT(DISTINCT e.slug)
               FROM launch_events e
               JOIN event_attributions ea ON ea.event_slug = e.slug
               JOIN raw_scrape_records rr ON rr.id = ea.scrape_record_id
               JOIN osint_sources os ON os.id = rr.source_id
               WHERE LOWER(os.name) LIKE '%notam%'
               AND e.slug != ?
               AND e.launch_date BETWEEN ? AND ?""",
            (exclude_slug, week_start, week_end),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0
