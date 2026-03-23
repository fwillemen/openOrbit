"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import os
import pytest
from httpx import ASGITransport, AsyncClient

# Use in-memory SQLite for tests to avoid file system pollution
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from openorbit.main import create_app  # noqa: E402


@pytest.fixture
async def async_client():
    """Create async HTTP client for testing with lifespan triggered.

    Uses in-memory SQLite. The ASGITransport triggers the FastAPI lifespan
    (startup → init_db, shutdown → close_db).

    Yields:
        Async HTTP client configured for the test app.
    """
    app = create_app()
    # lifespan="auto" ensures startup/shutdown hooks fire during the test
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Manually trigger lifespan startup since ASGITransport v0.27+ requires it
        from openorbit.db import init_db, close_db
        await init_db()
        try:
            yield client
        finally:
            await close_db()

