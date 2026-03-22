# Configuration Guide

openOrbit follows the **12-factor app** principle of configuration via environment variables. 
This guide documents all configurable settings.

## Environment Variables

All configuration is managed through environment variables. This allows the same application code 
to run across development, staging, and production environments with different settings.

### Quick Reference

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `VERSION` | string | `0.1.0` | No | Application semantic version |
| `LOG_LEVEL` | string | `INFO` | No | Logging verbosity level |
| `DATABASE_URL` | string | `sqlite+aiosqlite:///./openorbit.db` | No | Database connection string |

---

## Detailed Settings

### `VERSION`

**Type:** `string`  
**Default:** `0.1.0`  
**Required:** No

The application version in semantic versioning format (major.minor.patch).

**Usage:**
- Returned by the `/health` endpoint
- Used in API documentation
- Helps track which version is deployed in each environment

**Examples:**
```bash
export VERSION=0.1.0
export VERSION=1.0.0
export VERSION=1.2.3-beta
```

**Setting in different environments:**
```bash
# Development
VERSION=0.1.0-dev

# Staging
VERSION=1.0.0-rc1

# Production
VERSION=1.0.0
```

---

### `LOG_LEVEL`

**Type:** `string`  
**Default:** `INFO`  
**Required:** No  
**Valid values:** `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

Controls the verbosity of application logs.

| Level | Use Case |
|-------|----------|
| `DEBUG` | Development — logs all internal operations, variable values |
| `INFO` | Development and testing — general application flow |
| `WARNING` | Staging — logs unusual but recoverable situations |
| `ERROR` | Production — logs failures and errors only |
| `CRITICAL` | Production — logs only critical failures requiring immediate attention |

**Behavior:**
- Log output format changes based on level:
  - **Development** (DEBUG/INFO) — Pretty-printed to console for readability
  - **Production** (WARNING+) — JSON format for machine parsing and log aggregation

**Examples:**
```bash
# Development
export LOG_LEVEL=DEBUG

# Staging
export LOG_LEVEL=INFO

# Production
export LOG_LEVEL=WARNING
```

**In FastAPI:**
```python
from openorbit.config import get_settings

settings = get_settings()
print(settings.LOG_LEVEL)  # "WARNING"
```

---

### `DATABASE_URL`

**Type:** `string`  
**Default:** `sqlite+aiosqlite:///./openorbit.db`  
**Required:** No

Database connection string. Currently supports SQLite with async connection pooling.

**Format:** `sqlite+aiosqlite:///<path-to-database-file>`

#### SQLite File Database

```bash
# Relative path (recommended for development)
export DATABASE_URL=sqlite+aiosqlite:///./openorbit.db

# Absolute path
export DATABASE_URL=sqlite+aiosqlite:////var/lib/openorbit/openorbit.db

# Custom filename
export DATABASE_URL=sqlite+aiosqlite:///./data/production.db
```

#### SQLite In-Memory (Testing Only)

For testing without persistence:
```bash
export DATABASE_URL=sqlite+aiosqlite:///:memory:
```

#### Directory Creation

The parent directory must exist before the application starts:
```bash
mkdir -p ./data
export DATABASE_URL=sqlite+aiosqlite:///./data/openorbit.db
```

---

## .env File (Local Development)

For local development, create a `.env` file in `project/` with your settings:

```bash
cd project/
cp .env.example .env
# Edit .env with your local settings
```

**Example `.env` file:**
```bash
# Development environment configuration
VERSION=0.1.0-dev
LOG_LEVEL=DEBUG
DATABASE_URL=sqlite+aiosqlite:///./openorbit.dev.db
```

**Important:** Never commit `.env` to version control. The `.env` file is automatically 
ignored by `.gitignore` to prevent accidental exposure of secrets.

---

## Setting Configuration in Different Contexts

### Local Development

```bash
cd project/
cp .env.example .env
# Edit .env
uv run uvicorn openorbit.main:app --reload
```

### Docker Container

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install uv && uv sync

# Set environment at runtime
ENV VERSION=1.0.0
ENV LOG_LEVEL=INFO
ENV DATABASE_URL=sqlite+aiosqlite:////data/openorbit.db

VOLUME /data
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "openorbit.main:app", "--host", "0.0.0.0"]
```

Usage:
```bash
docker run \
  -e VERSION=1.0.0 \
  -e LOG_LEVEL=WARNING \
  -e DATABASE_URL=sqlite+aiosqlite:////data/openorbit.db \
  -v openorbit-data:/data \
  -p 8000:8000 \
  openorbit:latest
```

### Kubernetes

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: openorbit-config
data:
  VERSION: "1.0.0"
  LOG_LEVEL: "INFO"
  DATABASE_URL: "sqlite+aiosqlite:////data/openorbit.db"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: openorbit
spec:
  template:
    spec:
      containers:
      - name: api
        image: openorbit:1.0.0
        envFrom:
        - configMapRef:
            name: openorbit-config
        volumeMounts:
        - name: data
          mountPath: /data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: openorbit-pvc
```

### CI/CD (GitHub Actions)

```yaml
env:
  VERSION: ${{ github.ref_type == 'tag' && github.ref_name || '0.1.0-dev' }}
  LOG_LEVEL: DEBUG
  DATABASE_URL: sqlite+aiosqlite:///:memory:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: uv run pytest
```

---

## Adding New Configuration Settings

When adding a new setting:

1. **Define in `src/openorbit/config.py`:**
   ```python
   class Settings(BaseSettings):
       NEW_SETTING: str = "default_value"
   ```

2. **Document it here** in `docs/configuration.md`

3. **Add to `.env.example`:**
   ```bash
   # Example .env.example
   NEW_SETTING=default_value
   ```

4. **Update README** with usage examples

---

## Validation and Defaults

The `Settings` class validates configuration at startup using Pydantic:

```python
from openorbit.config import get_settings

try:
    settings = get_settings()
except Exception as e:
    print(f"Configuration error: {e}")
    exit(1)
```

If a configuration value is invalid, the application will fail to start with a clear error message.

**Example error:**
```
pydantic.ValidationError: 1 validation error for Settings
LOG_LEVEL
  Input should be 'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL' [type=enum, input_value='VERBOSE', input_type=str]
```

---

## Environment Variable Precedence

The application loads configuration in this order (later values override earlier ones):

1. **Defaults** defined in `Settings` class
2. **`.env` file** (if present)
3. **System environment variables** (highest priority)

Example:
```bash
# .env contains:
# LOG_LEVEL=DEBUG

# But you can override at runtime:
export LOG_LEVEL=INFO
uv run uvicorn openorbit.main:app  # Uses INFO, not DEBUG
```

---

## Troubleshooting

### Application won't start with DATABASE_URL error

**Error:** `Error: Invalid DATABASE_URL format`

**Solution:** Ensure the path is correct and parent directories exist:
```bash
mkdir -p ./data
export DATABASE_URL=sqlite+aiosqlite:///./data/openorbit.db
```

### Logs are not showing expected detail

**Issue:** Expected debug logs but only seeing info

**Solution:** Check LOG_LEVEL:
```bash
export LOG_LEVEL=DEBUG
uv run uvicorn openorbit.main:app --reload
```

### Configuration not being picked up

**Issue:** .env changes not reflected

**Solution:** The `.env` file is read at application startup. Restart the app:
```bash
# Stop the current process (Ctrl+C)
uv run uvicorn openorbit.main:app --reload  # Restart
```

---

## See Also

- [API Reference](./api/health.md) — How to check configuration via `/health` endpoint
- [Development Guide](./development.md) — How to add new endpoints and features
- [Architecture](./architecture.md) — Design decisions (ADR-002 covers configuration)
