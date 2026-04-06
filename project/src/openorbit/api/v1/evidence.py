"""Evidence chain API endpoints (v1).

Provides per-launch evidence chain with source attribution details.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from openorbit.db import get_db, get_event_attributions, get_launch_event_by_slug
from openorbit.models.api import EvidenceAttributionItem, EvidenceResponse

router = APIRouter(tags=["Evidence"])


@router.get(
    "/launches/{slug}/evidence",
    response_model=EvidenceResponse,
    summary="Get evidence chain for a launch",
    description="Returns all source attributions for a launch event with tier coverage summary.",
)
async def get_evidence(slug: str) -> EvidenceResponse:
    """Retrieve the full evidence chain for a launch event.

    Args:
        slug: The unique launch event slug.

    Returns:
        EvidenceResponse with attributions ordered by observed_at desc.

    Raises:
        HTTPException 404: If the launch slug is not found.
    """
    async with get_db() as conn:
        launch = await get_launch_event_by_slug(conn, slug)
        if launch is None:
            raise HTTPException(status_code=404, detail="Launch not found")

        attributions = await get_event_attributions(conn, slug)

    # Sort: observed_at descending, None last
    with_ts = [a for a in attributions if a.observed_at is not None]
    without_ts = [a for a in attributions if a.observed_at is None]
    with_ts_sorted = sorted(with_ts, key=lambda a: a.observed_at, reverse=True)  # type: ignore[arg-type, return-value]
    sorted_attrs = with_ts_sorted + without_ts

    tier_coverage = sorted({a.source_tier for a in attributions if a.source_tier is not None})

    evidence_items = [
        EvidenceAttributionItem(
            source_name=a.source_name,
            source_tier=a.source_tier,
            evidence_type=a.evidence_type,
            source_url=a.source_url,
            observed_at=a.observed_at,
            confidence_score=a.confidence_score,
            confidence_rationale=a.confidence_rationale,
        )
        for a in sorted_attrs
    ]

    return EvidenceResponse(
        launch_id=slug,
        claim_lifecycle=launch.claim_lifecycle,
        event_kind=launch.event_kind,
        evidence_count=len(attributions),
        tier_coverage=tier_coverage,
        attributions=evidence_items,
    )
