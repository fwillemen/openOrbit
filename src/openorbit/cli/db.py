"""Compatibility entry point for database CLI commands.

This module preserves the documented invocation path:
    python -m openorbit.cli.db init
"""

from __future__ import annotations

from openorbit.cli_db import init_command, main

__all__ = ["init_command", "main"]


if __name__ == "__main__":
    main()
