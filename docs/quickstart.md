# Quick Start

This guide gets you from zero to a running openOrbit API in minutes.

---

## 1. Install Dependencies

```bash
cd openOrbit
uv sync
```

---

## 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` to set your secrets:

```ini
# Required for managing API keys
OPENORBIT_ADMIN_KEY=your-admin-key-here

# Optional overrides
LOG_LEVEL=INFO
DATABASE_URL=sqlite+aiosqlite:///./openorbit.db
```

---

## 3. Initialize the Database

```bash
python -m openorbit.cli.db init
```

---

## 4. Start the Server

```bash
uv run uvicorn openorbit.main:app --reload
```

The API is now available at **http://localhost:8000**.  
Interactive docs: **http://localhost:8000/docs**

---

## 5. Verify the Health Endpoint

No auth required for health checks:

```bash
curl http://localhost:8000/health
```

```json
{"status": "ok", "version": "0.1.0"}
```

---

## 6. Authentication Quick Start

All GET endpoints are **public**. Write operations require an API key.

### 6.1 Create Your First API Key

Use the bootstrap admin key from your `.env`:

```bash
curl -s -X POST http://localhost:8000/v1/auth/keys \
  -H "X-API-Key: your-admin-key-here" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-first-key", "is_admin": false}'
```

Response:

```json
{
  "id": 1,
  "name": "my-first-key",
  "key": "aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcd",
  "is_admin": false,
  "created_at": "2025-01-22T14:30:00+00:00"
}
```

> **Save the `key` value** — it is shown only once.

### 6.2 Use the API Key

Pass the key in the `X-API-Key` header:

```bash
curl -s http://localhost:8000/v1/launches \
  -H "X-API-Key: aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcd"
```

Or as a query parameter:

```bash
curl -s "http://localhost:8000/v1/launches?api_key=aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcd"
```

### 6.3 Revoke an API Key

```bash
curl -s -X DELETE http://localhost:8000/v1/auth/keys/1 \
  -H "X-API-Key: your-admin-key-here"
```

For full authentication documentation, see [docs/auth.md](auth.md).

---

## 7. Browse the Interactive Docs

Open **http://localhost:8000/docs** in your browser to explore all endpoints with live try-it-out functionality. Click the lock icon on protected endpoints to enter your API key.
