"""Launch event API endpoints (v1).

Provides paginated listing and slug-based detail retrieval for launch events.
"""

from __future__ import annotations

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
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 25,
) -> PaginatedLaunchResponse:
    """List launch events with optional filtering and pagination.

    Args:
        from_date: Filter events on or after this datetime.
        to_date: Filter events on or before this datetime.
        provider: Filter by launch provider name.
        launch_type: Filter by launch type.
        status: Filter by launch status.
        page: Page number (1-indexed).
        per_page: Results per page (1–100).

    Returns:
        Paginated list of launch events with metadata.
    """
    date_from = from_date.isoformat() if from_date else None
    date_to = to_date.isoformat() if to_date else None

    async with get_db() as conn:
        total = await count_launch_events(
            conn,
            date_from=date_from,
            date_to=date_to,
            provider=provider,
            status=status,
            launch_type=launch_type,
        )
        events = await get_launch_events(
            conn,
            date_from=date_from,
            date_to=date_to,
            provider=provider,
            status=status,
            launch_type=launch_type,
            limit=per_page,
            offset=(page - 1) * per_page,
        )

    data = [_build_launch_response(e) for e in events]
    return PaginatedLaunchResponse(
        data=data,
        meta=PaginationMeta(total=total, page=page, per_page=per_page),
    )


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
