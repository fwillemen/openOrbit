# API Key Authentication

openOrbit uses **API key authentication** to protect write operations while keeping all read (GET) endpoints public.

---

## Auth Model Overview

| Mechanism | Details |
|-----------|---------|
| Key format | URL-safe random string, 40 bytes of entropy |
| Storage | PBKDF2-SHA256 hash + random 32-byte salt (never plaintext) |
| Comparison | `hmac.compare_digest` (timing-safe) |
| Transport | `X-API-Key` request header **or** `?api_key=` query parameter |
| Admin bootstrap | `OPENORBIT_ADMIN_KEY` environment variable (in-memory only, never stored) |

### Public vs. Protected Endpoints

| Method | Endpoint | Auth required? |
|--------|----------|---------------|
| `GET` | `/health`, `/v1/launches/**` | ❌ Public |
| `POST` | `/v1/auth/keys` | ✅ Admin key |
| `DELETE` | `/v1/auth/keys/{id}` | ✅ Admin key |

---

## Bootstrap Admin Key

Before any API keys exist in the database, use the **bootstrap admin key** to create the first keys.

Set the environment variable before starting the server:

```bash
export OPENORBIT_ADMIN_KEY="your-strong-secret-here"
uv run uvicorn openorbit.main:app --reload
```

Or add it to your `.env` file:

```ini
OPENORBIT_ADMIN_KEY=your-strong-secret-here
```

> **Security note:** The bootstrap key is compared in-memory and is **never written to the database**. Rotate it like any other secret.

---

## Creating an API Key

Send a `POST` request to `/v1/auth/keys` authenticated with an admin key.

**Request:**

```bash
curl -s -X POST http://localhost:8000/v1/auth/keys \
  -H "X-API-Key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"name": "ci-bot", "is_admin": false}'
```

**Response (201 Created):**

```json
{
  "id": 1,
  "name": "ci-bot",
  "key": "aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcd",
  "is_admin": false,
  "created_at": "2025-01-22T14:30:00+00:00"
}
```

> **⚠️ Important:** The plaintext `key` is returned **once only**. Store it securely — it cannot be retrieved again.

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Human-readable label for the key |
| `is_admin` | boolean | ❌ (default: `false`) | Whether this key can manage other keys |

---

## Using an API Key

Pass the key in the `X-API-Key` header (preferred):

```bash
curl -s http://localhost:8000/v1/launches \
  -H "X-API-Key: aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcd"
```

Or as a query parameter (for tools that don't support custom headers):

```bash
curl -s "http://localhost:8000/v1/launches?api_key=aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcd"
```

---

## Revoking an API Key

Send a `DELETE` request to `/v1/auth/keys/{id}` authenticated with an admin key.

```bash
curl -s -X DELETE http://localhost:8000/v1/auth/keys/1 \
  -H "X-API-Key: your-admin-key"
```

**Response (200 OK):**

```json
{
  "id": 1,
  "revoked_at": "2025-01-22T15:00:00+00:00"
}
```

Revoked keys are **retained in the database** for audit purposes but are refused on all subsequent authentication checks.

---

## Error Codes

| HTTP Status | When it occurs |
|-------------|---------------|
| `401 Unauthorized` | No API key provided on a protected endpoint |
| `403 Forbidden` | API key present but invalid, revoked, or lacks admin privileges |
| `404 Not Found` | `DELETE /v1/auth/keys/{id}` — key ID does not exist |
| `409 Conflict` | `DELETE /v1/auth/keys/{id}` — key is already revoked |

### Example error responses

**401 — missing key:**
```json
{"detail": "Missing API key"}
```

**403 — invalid or revoked key:**
```json
{"detail": "Invalid or revoked API key"}
```

**409 — already revoked:**
```json
{"detail": "API key already revoked"}
```

---

## Database Schema

The `api_keys` table stores key metadata:

```sql
CREATE TABLE api_keys (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    key_hash   TEXT    NOT NULL,   -- PBKDF2-SHA256 hex digest
    salt       TEXT    NOT NULL,   -- 32-byte random salt (hex)
    is_admin   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL,
    revoked_at TEXT                -- NULL = active
);
```

---

## Security Considerations

- **PBKDF2-SHA256** with 260,000 iterations makes brute-force attacks computationally expensive.
- **`hmac.compare_digest`** prevents timing attacks during key comparison.
- **Revocation** is soft-delete: old keys are kept for audit logs.
- Rotate the `OPENORBIT_ADMIN_KEY` regularly, especially after team membership changes.
- Use HTTPS in production so keys are not transmitted in plaintext.
