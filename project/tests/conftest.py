"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from openorbit.main import create_app


@pytest.fixture
async def async_client() -> AsyncClient:
    """Create async HTTP client for testing.

    Yields:
        Async HTTP client configured for the test app.
    """
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
