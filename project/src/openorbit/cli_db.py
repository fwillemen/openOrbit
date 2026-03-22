"""CLI command for database initialization.

Usage:
    uv run python -m openorbit.cli.db init
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import aiosqlite

from openorbit.config import get_settings
from openorbit.db import init_db_schema

logger = logging.getLogger(__name__)


async def init_command() -> int:
    """Initialize database schema.

    Returns:
        Exit code (0 = success, 1 = failure).
    """
    try:
        settings = get_settings()
        db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")

        print(f"Initializing database at {db_path}...")

        # Create database file if it doesn't exist
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Connect and initialize schema
        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            await init_db_schema(conn)

        print("✅ Database schema initialized successfully")
        return 0

    except Exception as e:
        print(f"❌ Failed to initialize database: {e}", file=sys.stderr)
        logger.exception("Database initialization failed")
        return 1


def main() -> None:
    """Entry point for CLI command."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Parse command
    if len(sys.argv) < 2 or sys.argv[1] != "init":
        print("Usage: python -m openorbit.cli.db init", file=sys.stderr)
        sys.exit(1)

    # Run async init command
    exit_code = asyncio.run(init_command())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
