"""API v1 router package."""

from __future__ import annotations

from fastapi import APIRouter

from openorbit.api.v1 import admin, auth, evidence, launches, sources

router = APIRouter(prefix="/v1", tags=["launches"])
router.include_router(launches.router)
router.include_router(evidence.router)
router.include_router(sources.router)
router.include_router(auth.router)
router.include_router(admin.router)

__all__ = ["router"]
