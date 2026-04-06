# Command-Line Interface

openOrbit provides CLI commands for database management and other operations.

## Database Commands

### Initialize Database

Initialize the SQLite database schema and create all tables, indexes, and triggers.

```bash
python -m openorbit.cli.db init
```

**Parameters:** None

**Returns:**
- Exit code 0 on success
- Exit code 1 on failure

**Output:**
```
Initializing database at ./openorbit.db...
✅ Database schema initialized successfully
```

**Error Output:**
```
❌ Failed to initialize database: [error details]
```

**What It Does:**

1. Reads database path from `DATABASE_URL` environment variable
2. Creates parent directories if they don't exist
3. Loads `schema.sql` from the package
4. Executes schema to create tables:
   - `osint_sources` — OSINT data source registry
   - `raw_scrape_records` — Immutable scrape audit trail
   - `launch_events` — Normalized launch event records
   - `event_attributions` — Event-to-source linking
   - `launch_events_fts` — FTS5 full-text search index
5. Creates all indexes and triggers

**Idempotency:** Safe to run multiple times (uses `CREATE TABLE IF NOT EXISTS`)

**Example Usage:**

```bash
# Initialize with default database path

python -m openorbit.cli.db init

# With custom database path (via environment variable)
DATABASE_URL="sqlite+aiosqlite:///./custom.db" python -m openorbit.cli.db init
```

**Troubleshooting:**

| Error | Cause | Solution |
|-------|-------|----------|
| `No module named openorbit` | Running outside project directory | Run from repo root |
| `DATABASE_URL not set` | Missing environment variable | Set `DATABASE_URL` in `.env` or environment |
| `Permission denied` | Cannot write to database directory | Check directory permissions |
| `database is locked` | Another process has database open | Close other instances or wait |

---

## Environment Variables

### `DATABASE_URL`

**Type:** `str`  
**Required:** Yes  
**Default:** `sqlite+aiosqlite:///./openorbit.db`

SQLite connection string in SQLAlchemy format.

**Format:** `sqlite+aiosqlite:///path/to/database.db`

**Examples:**
```bash
# Default (local file)
DATABASE_URL="sqlite+aiosqlite:///./openorbit.db"

# Custom path
DATABASE_URL="sqlite+aiosqlite:///./data/openorbit.db"

# Absolute path
DATABASE_URL="sqlite+aiosqlite:////var/lib/openorbit/db.sqlite"

# In-memory database (for testing)
DATABASE_URL="sqlite+aiosqlite:///:memory:"
```

**Notes:**
- The CLI extracts the file path by removing `sqlite+aiosqlite:///` prefix
- Parent directories are created automatically if they don't exist
- In-memory databases are ephemeral (lost when application exits)

---

## Common Tasks

### First-Time Setup

```bash
# 1. Clone repository and navigate to project


# 2. Install dependencies
uv sync

# 3. Create .env file
cp .env.example .env

# 4. Initialize database
python -m openorbit.cli.db init

# 5. Run tests to verify
uv run pytest tests/test_db.py -v
```

### Reset Database (Development)

```bash
# Delete existing database
rm openorbit.db

# Recreate from scratch
python -m openorbit.cli.db init
```

### Programmatic Usage

Use the database API directly in Python code:

```python
from openorbit.db import init_db, close_db, get_db

async def main():
    # Initialize
    await init_db()
    
    # Use database
    async with get_db() as conn:
        from openorbit.db import get_osint_sources
        sources = await get_osint_sources(conn)
        print(f"Found {len(sources)} sources")
    
    # Cleanup
    await close_db()

# Run in FastAPI app startup
# (automatically called via lifespan handler)
```

---

## See Also

- [Database API Reference](./api/database.md) — Repository functions
- [Database Schema](./database/schema.md) — Table definitions
- [Developer Guide](./development.md) — Database development workflows
