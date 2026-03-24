"""API response models for openOrbit endpoints.

Defines Pydantic response schemas decoupled from DB and pipeline models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class AttributionResponse(BaseModel):
    """Attribution source linked to a launch event."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "SpaceFlightNow",
                "url": "https://spaceflightnow.com/2025/01/22/falcon-9-starlink-launch/",
                "scraped_at": "2025-01-22T10:00:00Z",
            }
        }
    )

    name: str
    url: str
    scraped_at: datetime | None = None


class PaginationMeta(BaseModel):
    """Pagination metadata for list responses."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 142,
                "page": 1,
                "per_page": 25,
                "next_cursor": "MTQy",
            }
        }
    )

    total: int
    page: int
    per_page: int
    next_cursor: str | None = None


class LaunchEventResponse(BaseModel):
    """Full launch event representation returned by the API."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 42,
                "slug": "falcon-9-starlink-6-32-2025-01-22",
                "name": "Falcon 9 | Starlink Group 6-32",
                "launch_date": "2025-01-22T14:30:00Z",
                "launch_date_precision": "hour",
                "provider": "SpaceX",
                "vehicle": "Falcon 9",
                "location": "28.573,-80.649",
                "pad": "LC-39A, Kennedy Space Center",
                "launch_type": "civilian",
                "status": "scheduled",
                "confidence_score": 87.5,
                "result_tier": "verified",
                "evidence_count": 3,
                "created_at": "2025-01-20T08:00:00Z",
                "updated_at": "2025-01-22T09:15:00Z",
                "sources": [
                    {
                        "name": "SpaceFlightNow",
                        "url": "https://spaceflightnow.com/2025/01/22/falcon-9-starlink-launch/",
                        "scraped_at": "2025-01-22T10:00:00Z",
                    }
                ],
                "inference_flags": ["date_inferred_from_window"],
            }
        }
    )

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
    result_tier: Literal["emerging", "tracked", "verified"]
    evidence_count: int
    created_at: datetime
    updated_at: datetime
    sources: list[AttributionResponse] = []
    inference_flags: list[str] = []


class PaginatedLaunchResponse(BaseModel):
    """Paginated list of launch events."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "data": [
                    {
                        "id": 42,
                        "slug": "falcon-9-starlink-6-32-2025-01-22",
                        "name": "Falcon 9 | Starlink Group 6-32",
                        "launch_date": "2025-01-22T14:30:00Z",
                        "launch_date_precision": "hour",
                        "provider": "SpaceX",
                        "vehicle": "Falcon 9",
                        "location": "28.573,-80.649",
                        "pad": "LC-39A, Kennedy Space Center",
                        "launch_type": "civilian",
                        "status": "scheduled",
                        "confidence_score": 87.5,
                        "result_tier": "verified",
                        "evidence_count": 3,
                        "created_at": "2025-01-20T08:00:00Z",
                        "updated_at": "2025-01-22T09:15:00Z",
                        "sources": [],
                        "inference_flags": [],
                    }
                ],
                "meta": {
                    "total": 142,
                    "page": 1,
                    "per_page": 25,
                    "next_cursor": "MTQy",
                },
            }
        }
    )

    data: list[LaunchEventResponse]
    meta: PaginationMeta


# ---------------------------------------------------------------------------
# Auth models
# ---------------------------------------------------------------------------


class ApiKeyCreateRequest(BaseModel):
    """Request body for creating a new API key."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "ci-pipeline",
                "is_admin": False,
            }
        }
    )

    name: str
    is_admin: bool = False


class ApiKeyCreateResponse(BaseModel):
    """Response after creating an API key.

    The ``key`` field contains the plaintext key shown **once only**.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "ci-pipeline",
                "key": "aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcd",
                "is_admin": False,
                "created_at": "2025-01-22T14:30:00+00:00",
            }
        }
    )

    id: int
    name: str
    key: str
    is_admin: bool
    created_at: str


class ApiKeyRevokeResponse(BaseModel):
    """Response after revoking an API key."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "revoked_at": "2025-01-22T15:00:00+00:00",
            }
        }
    )

    id: int
    revoked_at: str
