"""Tests for database connection management."""

from __future__ import annotations

import os
import tempfile

import pytest

from openorbit.db import close_db, get_db, init_db


@pytest.mark.asyncio
async def test_db_connection_lifecycle() -> None:
    """Test database initialization and cleanup."""
    # Use temporary database file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # Override DATABASE_URL for this test
        import openorbit.config

        original_settings = openorbit.config._settings
        openorbit.config._settings = None

        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

        # Initialize database
        await init_db()

        # Get connection should work
        async with get_db() as conn:
            assert conn is not None

        # Clean up
        await close_db()

        # After close, get_db should raise
        with pytest.raises(RuntimeError, match="Database not initialized"):
            async with get_db() as conn:
                pass

    finally:
        # Restore original settings and clean up
        openorbit.config._settings = original_settings
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        if os.path.exists(db_path):
            os.unlink(db_path)
