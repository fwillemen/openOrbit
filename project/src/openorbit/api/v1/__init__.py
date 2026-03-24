"""API v1 router package."""

from __future__ import annotations

from fastapi import APIRouter

from openorbit.api.v1 import auth, launches, sources

router = APIRouter(prefix="/v1", tags=["launches"])
router.include_router(launches.router)
router.include_router(sources.router)
router.include_router(auth.router)

__all__ = ["router"]
