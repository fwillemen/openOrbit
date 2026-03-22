"""Health check API endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from openorbit.config import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    """Health check endpoint.

    Returns basic service status and version information.

    Args:
        settings: Application settings (injected).

    Returns:
        Health status and version.
    """
    return {
        "status": "ok",
        "version": settings.VERSION,
    }
