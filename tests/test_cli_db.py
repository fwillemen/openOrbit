"""Tests for CLI database initialization command.

Tests cover:
- CLI init command success path
- CLI init command error handling
- Database file creation
- Schema initialization via CLI
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

import aiosqlite
import pytest

from openorbit.cli_db import init_command


@pytest.mark.asyncio
async def test_init_command_creates_database() -> None:
    """Test that init_command creates database file and initializes schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_openorbit.db"

        # Mock get_settings to use temp database
        with mock.patch(
            "openorbit.cli_db.get_settings"
        ) as mock_settings:
            mock_settings.return_value.DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"

            # Run init command
            exit_code = await init_command()

            # Verify success
            assert exit_code == 0
            assert db_path.exists()

            # Verify schema was created
            async with aiosqlite.connect(str(db_path)) as conn:
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                tables = [row[0] for row in await cursor.fetchall()]

                # Check all expected tables exist
                expected_tables = [
                    "launch_events",
                    "osint_sources",
                    "event_attributions",
                    "raw_scrape_records",
                ]
                for table in expected_tables:
                    assert table in tables, f"Table {table} not found"


@pytest.mark.asyncio
async def test_init_command_idempotent() -> None:
    """Test that init_command can be run multiple times without error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_openorbit.db"

        with mock.patch(
            "openorbit.cli_db.get_settings"
        ) as mock_settings:
            mock_settings.return_value.DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"

            # First init
            exit_code_1 = await init_command()
            assert exit_code_1 == 0

            # Second init (should be idempotent)
            exit_code_2 = await init_command()
            assert exit_code_2 == 0


@pytest.mark.asyncio
async def test_init_command_creates_parent_directories() -> None:
    """Test that init_command creates parent directories if needed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "subdir1" / "subdir2" / "test_openorbit.db"

        with mock.patch(
            "openorbit.cli_db.get_settings"
        ) as mock_settings:
            mock_settings.return_value.DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"

            exit_code = await init_command()

            assert exit_code == 0
            assert db_path.exists()
            assert db_path.parent.exists()


@pytest.mark.asyncio
async def test_init_command_handles_exception() -> None:
    """Test that init_command handles exceptions gracefully."""
    with mock.patch("openorbit.cli_db.init_db_schema") as mock_init:
        # Simulate an error in init_db_schema
        mock_init.side_effect = RuntimeError("Test error")

        with mock.patch("openorbit.cli_db.get_settings") as mock_settings:
            mock_settings.return_value.DATABASE_URL = "sqlite+aiosqlite:///./test.db"

            exit_code = await init_command()

            # Should return non-zero exit code on error
            assert exit_code == 1
