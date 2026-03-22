"""Tests for health check endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint_returns_200_ok(async_client: AsyncClient) -> None:
    """Test that /health endpoint returns 200 OK with correct structure."""
    response = await async_client.get("/health")

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert isinstance(data["version"], str)


@pytest.mark.asyncio
async def test_health_endpoint_returns_correct_version(
    async_client: AsyncClient,
) -> None:
    """Test that /health endpoint returns the configured version."""
    response = await async_client.get("/health")

    data = response.json()
    # Default version from config is 0.1.0
    assert data["version"] == "0.1.0"
