"""Launch event API endpoints (v1).

Provides paginated listing and slug-based detail retrieval for launch events.
"""

from __future__ import annotations

import base64
import math
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from openorbit.db import (
    count_launch_events,
    get_db,
    get_event_attributions,
    get_launch_event_by_slug,
    get_launch_events,
)
from openorbit.models.api import (
    AttributionResponse,
    LaunchEventResponse,
    PaginatedLaunchResponse,
    PaginationMeta,
)
from openorbit.models.db import EventAttribution, LaunchEvent

router = APIRouter()

_EARTH_RADIUS_KM = 6371.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in km between two (lat, lon) points.

    Args:
        lat1: Latitude of the first point in degrees.
        lon1: Longitude of the first point in degrees.
        lat2: Latitude of the second point in degrees.
        lon2: Longitude of the second point in degrees.

    Returns:
        Distance in kilometres.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return _EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


def _parse_lat_lon(value: str) -> tuple[float, float] | None:
    """Try to parse a 'lat,lon' string.

    Args:
        value: String in 'lat,lon' format (e.g. '28.573,-80.649').

    Returns:
        Tuple (lat, lon) on success, None otherwise.
    """
    parts = value.split(",", 1)
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def _encode_cursor(row_id: int) -> str:
    """Base64-encode a row ID into an opaque cursor token.

    Args:
        row_id: SQLite rowid of the last returned event.

    Returns:
        URL-safe base64 string.
    """
    return base64.urlsafe_b64encode(str(row_id).encode()).decode()


def _decode_cursor(cursor: str) -> int | None:
    """Decode a cursor token back to a row ID.

    Args:
        cursor: Opaque cursor token from a previous response.

    Returns:
        Integer row ID, or None if the cursor is invalid.
    """
    try:
        return int(base64.urlsafe_b64decode(cursor).decode())
    except Exception:
        return None


def _build_launch_response(
    event: LaunchEvent,
    attributions: list[EventAttribution] | None = None,
) -> LaunchEventResponse:
    """Build a LaunchEventResponse from a DB LaunchEvent.

    Args:
        event: DB LaunchEvent model instance.
        attributions: Optional list of EventAttribution models.

    Returns:
        LaunchEventResponse populated from the event.
    """
    sources = [
        AttributionResponse(
            name=attr.source_name,
            url=attr.url,
            scraped_at=attr.scraped_at,
        )
        for attr in (attributions or [])
    ]
    return LaunchEventResponse(
        id=event.id,
        slug=event.slug,
        name=event.name,
        launch_date=event.launch_date,
        launch_date_precision=event.launch_date_precision,
        provider=event.provider,
        vehicle=event.vehicle,
        location=event.location,
        pad=event.pad,
        launch_type=event.launch_type,
        status=event.status,
        confidence_score=float(event.confidence_score),
        created_at=event.created_at,
        updated_at=event.updated_at,
        sources=sources,
    )


@router.get("/launches", response_model=PaginatedLaunchResponse)
async def list_launches(
    from_date: Annotated[datetime | None, Query(alias="from")] = None,
    to_date: Annotated[datetime | None, Query(alias="to")] = None,
    provider: Annotated[str | None, Query()] = None,
    launch_type: Annotated[
        Literal["civilian", "military", "unknown"] | None, Query()
    ] = None,
    status: Annotated[
        Literal["scheduled", "delayed", "launched", "failed", "cancelled"] | None,
        Query(),
    ] = None,
    min_confidence: Annotated[float | None, Query(ge=0.0, le=100.0)] = None,
    location: Annotated[str | None, Query(description="lat,lon e.g. 28.573,-80.649")] = None,
    radius_km: Annotated[int | None, Query(ge=1)] = None,
    cursor: Annotated[str | None, Query(description="Opaque cursor for cursor-based pagination")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Results per page for cursor pagination")] = 25,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 25,
) -> PaginatedLaunchResponse:
    """List launch events with optional filtering and pagination.

    Supports both page-based (``page`` + ``per_page``) and cursor-based
    (``cursor`` + ``limit``) pagination.  When ``cursor`` is provided it takes
    precedence and ``page``/``per_page`` are ignored.

    Args:
        from_date: Filter events on or after this datetime.
        to_date: Filter events on or before this datetime.
        provider: Case-insensitive substring match on provider name.
        launch_type: Filter by launch type.
        status: Filter by launch status.
        min_confidence: Exclude events below this confidence score.
        location: Centre point for proximity search (format: ``lat,lon``).
        radius_km: Radius in km for proximity search (requires ``location``).
        cursor: Opaque cursor token for cursor-based pagination.
        limit: Maximum results for cursor-based pagination (1–100).
        page: Page number for page-based pagination (1-indexed).
        per_page: Results per page for page-based pagination (1–100).

    Returns:
        Paginated list of launch events with metadata.

    Raises:
        HTTPException: 400 if ``location`` format is invalid.
    """
    date_from = from_date.isoformat() if from_date else None
    date_to = to_date.isoformat() if to_date else None

    # Validate and parse location query param.
    geo_center: tuple[float, float] | None = None
    if location is not None:
        geo_center = _parse_lat_lon(location)
        if geo_center is None:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_location", "message": "location must be 'lat,lon'"},
            )

    # Decode cursor for cursor-based pagination.
    cursor_id: int | None = None
    using_cursor = cursor is not None
    if cursor is not None:
        cursor_id = _decode_cursor(cursor)
        if cursor_id is None:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_cursor", "message": "cursor token is invalid"},
            )

    # Determine page size and offset.
    page_size = limit if using_cursor else per_page
    db_offset = 0 if using_cursor else (page - 1) * per_page

    async with get_db() as conn:
        if geo_center is not None:
            # Proximity filtering requires Python-side evaluation — fetch all
            # events matching other filters then apply Haversine.
            all_events = await get_launch_events(
                conn,
                date_from=date_from,
                date_to=date_to,
                provider=provider,
                status=status,
                launch_type=launch_type,
                min_confidence=min_confidence,
                limit=10_000,
                offset=0,
            )
            lat0, lon0 = geo_center
            eff_radius = radius_km if radius_km is not None else 100
            filtered: list[LaunchEvent] = []
            for ev in all_events:
                if ev.location is None:
                    continue
                coords = _parse_lat_lon(ev.location)
                if coords is None:
                    continue
                if _haversine_km(lat0, lon0, coords[0], coords[1]) <= eff_radius:
                    filtered.append(ev)

            total = len(filtered)
            if using_cursor:
                # Find the position after cursor_id in the filtered list.
                start = 0
                if cursor_id is not None:
                    for i, ev in enumerate(filtered):
                        if ev.id == cursor_id:
                            start = i + 1
                            break
                page_events = filtered[start: start + page_size]
            else:
                page_events = filtered[db_offset: db_offset + page_size]
        else:
            total = await count_launch_events(
                conn,
                date_from=date_from,
                date_to=date_to,
                provider=provider,
                status=status,
                launch_type=launch_type,
                min_confidence=min_confidence,
            )
            page_events = await get_launch_events(
                conn,
                date_from=date_from,
                date_to=date_to,
                provider=provider,
                status=status,
                launch_type=launch_type,
                min_confidence=min_confidence,
                cursor_id=cursor_id,
                limit=page_size,
                offset=db_offset,
            )

    # Build next_cursor if there are more results.
    next_cursor: str | None = None
    if using_cursor and len(page_events) == page_size:
        next_cursor = _encode_cursor(page_events[-1].id)

    data = [_build_launch_response(e) for e in page_events]

    if using_cursor:
        meta = PaginationMeta(total=total, page=1, per_page=page_size, next_cursor=next_cursor)
    else:
        meta = PaginationMeta(total=total, page=page, per_page=per_page, next_cursor=next_cursor)

    return PaginatedLaunchResponse(data=data, meta=meta)


@router.get("/launches/{slug}", response_model=LaunchEventResponse)
async def get_launch(slug: str) -> LaunchEventResponse:
    """Retrieve a single launch event by slug.

    Args:
        slug: URL-safe unique event identifier.

    Returns:
        Launch event with sources array populated.

    Raises:
        HTTPException: 404 if the slug does not exist.
    """
    async with get_db() as conn:
        event = await get_launch_event_by_slug(conn, slug)
        if event is None:
            raise HTTPException(status_code=404, detail={"error": "not_found"})
        attributions = await get_event_attributions(conn, event.slug)

    return _build_launch_response(event, attributions)
