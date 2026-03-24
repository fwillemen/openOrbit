"""API Key management endpoints (v1).

Admin-only routes for creating and revoking API keys.
All endpoints require the bootstrap OPENORBIT_ADMIN_KEY or a stored admin key.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Path

from openorbit.auth import generate_raw_key, generate_salt, hash_key, require_admin
from openorbit.db import get_db
from openorbit.models.api import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyRevokeResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/keys",
    response_model=ApiKeyCreateResponse,
    status_code=201,
    dependencies=[Depends(require_admin)],
    tags=["auth"],
    summary="Create a new API key",
    description=(
        "Create a new API key. The plaintext key is returned **once** in the response "
        "and is never stored — only the PBKDF2-SHA256 hash and salt are persisted. "
        "Requires an admin API key in the `X-API-Key` header."
    ),
    response_description="Created key details including the plaintext key (shown once only).",
    responses={
        401: {"description": "Missing API key."},
        403: {"description": "Invalid, revoked, or non-admin API key."},
    },
)
async def create_api_key(body: ApiKeyCreateRequest) -> ApiKeyCreateResponse:
    """Create a new API key.

    The raw key is returned **once** in the response and never stored.
    Only the PBKDF2-SHA256 hash and salt are persisted.

    Args:
        body: Key creation parameters (name, is_admin flag).

    Returns:
        Created key details including the plaintext key (show once).
    """
    raw_key = generate_raw_key()
    salt = generate_salt()
    key_hash = hash_key(raw_key, salt)
    now = datetime.now(UTC).isoformat()

    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO api_keys (name, key_hash, salt, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (body.name, key_hash, salt, int(body.is_admin), now),
        )
        await db.commit()
        key_id = cursor.lastrowid
        if key_id is None:
            raise HTTPException(status_code=500, detail="Failed to create API key")

    return ApiKeyCreateResponse(
        id=key_id,
        name=body.name,
        key=raw_key,
        is_admin=body.is_admin,
        created_at=now,
    )


@router.delete(
    "/keys/{key_id}",
    response_model=ApiKeyRevokeResponse,
    dependencies=[Depends(require_admin)],
    tags=["auth"],
    summary="Revoke an API key",
    description=(
        "Revoke an existing API key by setting its `revoked_at` timestamp. "
        "Revoked keys are retained in the database for audit purposes but are refused "
        "on all subsequent authentication checks. "
        "Requires an admin API key in the `X-API-Key` header."
    ),
    response_description="Confirmation with key ID and revocation timestamp.",
    responses={
        401: {"description": "Missing API key."},
        403: {"description": "Invalid, revoked, or non-admin API key."},
        404: {"description": "API key not found."},
        409: {"description": "API key is already revoked."},
    },
)
async def revoke_api_key(
    key_id: int = Path(..., description="ID of the API key to revoke"),
) -> ApiKeyRevokeResponse:
    """Revoke an existing API key by setting its revoked_at timestamp.

    Revoked keys are retained in the database for audit purposes but
    are refused on all subsequent authentication checks.

    Args:
        key_id: Database ID of the key to revoke.

    Returns:
        Confirmation with key ID and revocation timestamp.

    Raises:
        HTTPException 404: Key not found.
        HTTPException 409: Key already revoked.
    """
    now = datetime.now(UTC).isoformat()

    async with get_db() as db:
        async with db.execute(
            "SELECT id, name, revoked_at FROM api_keys WHERE id = ?", (key_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="API key not found")
        if row["revoked_at"] is not None:
            raise HTTPException(status_code=409, detail="API key already revoked")

        await db.execute(
            "UPDATE api_keys SET revoked_at = ? WHERE id = ?", (now, key_id)
        )
        await db.commit()

    return ApiKeyRevokeResponse(id=key_id, revoked_at=now)
