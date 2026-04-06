"""API key authentication utilities.

Provides hashed key storage (PBKDF2-SHA256 + random salt), timing-safe
comparison via hmac.compare_digest, and a FastAPI dependency that validates
keys from the X-API-Key header or ?api_key= query param.

Bootstrap admin key (OPENORBIT_ADMIN_KEY) is compared in-memory only and
is never stored in the database.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import HTTPException, Request

from openorbit.config import get_settings

# ---------------------------------------------------------------------------
# Key hashing helpers
# ---------------------------------------------------------------------------

_PBKDF2_ITERATIONS = 260_000
_HASH_ALGO = "sha256"


def generate_salt() -> str:
    """Generate a cryptographically-random hex salt (32 bytes / 64 hex chars).

    Returns:
        Hex-encoded random salt string.
    """
    return secrets.token_hex(32)


def hash_key(raw_key: str, salt: str) -> str:
    """Derive a PBKDF2-SHA256 hash for an API key.

    Args:
        raw_key: The plaintext API key.
        salt: Hex-encoded salt (from generate_salt()).

    Returns:
        Hex-encoded PBKDF2 digest.
    """
    dk = hashlib.pbkdf2_hmac(
        _HASH_ALGO,
        raw_key.encode(),
        bytes.fromhex(salt),
        _PBKDF2_ITERATIONS,
    )
    return dk.hex()


def verify_key(raw_key: str, stored_hash: str, salt: str) -> bool:
    """Timing-safe comparison of a raw key against its stored hash.

    Args:
        raw_key: Plaintext key supplied by the caller.
        stored_hash: Hex-encoded PBKDF2 digest from the database.
        salt: Hex-encoded salt from the database.

    Returns:
        True if the key matches; False otherwise.
    """
    candidate_hash = hash_key(raw_key, salt)
    return hmac.compare_digest(candidate_hash, stored_hash)


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

def generate_raw_key() -> str:
    """Generate a new plaintext API key (URL-safe, 40 bytes of entropy).

    Returns:
        URL-safe random key string.
    """
    return secrets.token_urlsafe(40)


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def _extract_raw_key(request: Request) -> str | None:
    """Extract raw API key from X-API-Key header or ?api_key= query param.

    Args:
        request: The incoming FastAPI request.

    Returns:
        Raw key string, or None if absent.
    """
    header_key = request.headers.get("X-API-Key")
    if header_key:
        return header_key
    return request.query_params.get("api_key")


async def require_admin(request: Request) -> None:
    """FastAPI dependency that enforces admin-level authentication.

    Accepts the bootstrap OPENORBIT_ADMIN_KEY env var (in-memory only)
    or any non-revoked is_admin key stored in the database.

    Raises:
        HTTPException 401: No key supplied.
        HTTPException 403: Key supplied but invalid or revoked.
    """
    from openorbit.db import get_db  # noqa: PLC0415

    raw_key = _extract_raw_key(request)
    if raw_key is None:
        raise HTTPException(status_code=401, detail="API key required")

    settings = get_settings()

    # Bootstrap admin key — compared in memory, never stored
    if settings.OPENORBIT_ADMIN_KEY and hmac.compare_digest(
        raw_key, settings.OPENORBIT_ADMIN_KEY
    ):
        return

    # Database lookup
    _admin_key_query = (
        "SELECT key_hash, salt FROM api_keys"
        " WHERE revoked_at IS NULL AND is_admin = 1"
    )
    async with get_db() as db:
        async with db.execute(_admin_key_query) as cursor:
            rows = await cursor.fetchall()
        found = False
        for row in rows:
            if verify_key(raw_key, row["key_hash"], row["salt"]):
                found = True
        if found:
            return

    raise HTTPException(status_code=403, detail="Invalid or revoked API key")


async def require_valid_key(request: Request) -> None:
    """FastAPI dependency that enforces any valid (non-revoked) API key.

    Used for protected non-admin endpoints if added in the future.

    Raises:
        HTTPException 401: No key supplied.
        HTTPException 403: Key supplied but invalid or revoked.
    """
    from openorbit.db import get_db  # noqa: PLC0415

    raw_key = _extract_raw_key(request)
    if raw_key is None:
        raise HTTPException(status_code=401, detail="API key required")

    settings = get_settings()

    # Bootstrap admin key is also a valid key for any protected route
    if settings.OPENORBIT_ADMIN_KEY and hmac.compare_digest(
        raw_key, settings.OPENORBIT_ADMIN_KEY
    ):
        return

    async with get_db() as db:
        async with db.execute(
            "SELECT key_hash, salt FROM api_keys WHERE revoked_at IS NULL"
        ) as cursor:
            rows = await cursor.fetchall()
        found = False
        for row in rows:
            if verify_key(raw_key, row["key_hash"], row["salt"]):
                found = True
        if found:
            return

    raise HTTPException(status_code=403, detail="Invalid or revoked API key")
