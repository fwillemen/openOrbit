"""API response models for openOrbit endpoints.

Defines Pydantic response schemas decoupled from DB and pipeline models.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AttributionResponse(BaseModel):
    """Attribution source linked to a launch event."""

    name: str
    url: str
    scraped_at: datetime | None = None


class PaginationMeta(BaseModel):
    """Pagination metadata for list responses."""

    total: int
    page: int
    per_page: int


class LaunchEventResponse(BaseModel):
    """Full launch event representation returned by the API."""

    id: int
    slug: str
    name: str
    launch_date: datetime
    launch_date_precision: str
    provider: str
    vehicle: str | None = None
    location: str | None = None
    pad: str | None = None
    launch_type: str
    status: str
    confidence_score: float
    created_at: datetime
    updated_at: datetime
    sources: list[AttributionResponse] = []


class PaginatedLaunchResponse(BaseModel):
    """Paginated list of launch events."""

    data: list[LaunchEventResponse]
    meta: PaginationMeta
