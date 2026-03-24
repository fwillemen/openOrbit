"""Tests for API key authentication.

Covers:
- Key hashing and verification (hash_key, verify_key, generate_salt)
- Key generation (generate_raw_key)
- _extract_raw_key helper (header vs query param priority)
- require_admin dependency (401 missing, 403 invalid, 200 bootstrap key, 200 DB key)
- POST /v1/auth/keys (create key — admin auth, response schema, key stored hashed)
- DELETE /v1/auth/keys/{id} (revoke key — 404 unknown, 409 already revoked, 200 ok)
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Unit tests — pure auth helpers (no HTTP, no DB)
# ---------------------------------------------------------------------------


class TestGenerateSalt:
    def test_returns_64_char_hex_string(self) -> None:
        from openorbit.auth import generate_salt

        salt = generate_salt()
        assert len(salt) == 64
        assert all(c in "0123456789abcdef" for c in salt)

    def test_each_call_returns_different_salt(self) -> None:
        from openorbit.auth import generate_salt

        assert generate_salt() != generate_salt()


class TestHashKey:
    def test_deterministic_for_same_inputs(self) -> None:
        from openorbit.auth import generate_salt, hash_key

        salt = generate_salt()
        assert hash_key("my-key", salt) == hash_key("my-key", salt)

    def test_different_keys_produce_different_hashes(self) -> None:
        from openorbit.auth import generate_salt, hash_key

        salt = generate_salt()
        assert hash_key("key-a", salt) != hash_key("key-b", salt)

    def test_different_salts_produce_different_hashes(self) -> None:
        from openorbit.auth import generate_salt, hash_key

        h1 = hash_key("same-key", generate_salt())
        h2 = hash_key("same-key", generate_salt())
        assert h1 != h2

    def test_returns_hex_string(self) -> None:
        from openorbit.auth import generate_salt, hash_key

        result = hash_key("key", generate_salt())
        assert all(c in "0123456789abcdef" for c in result)


class TestVerifyKey:
    def test_correct_key_returns_true(self) -> None:
        from openorbit.auth import generate_salt, hash_key, verify_key

        salt = generate_salt()
        stored = hash_key("correct", salt)
        assert verify_key("correct", stored, salt) is True

    def test_wrong_key_returns_false(self) -> None:
        from openorbit.auth import generate_salt, hash_key, verify_key

        salt = generate_salt()
        stored = hash_key("correct", salt)
        assert verify_key("wrong", stored, salt) is False

    def test_empty_key_does_not_match_non_empty(self) -> None:
        from openorbit.auth import generate_salt, hash_key, verify_key

        salt = generate_salt()
        stored = hash_key("non-empty", salt)
        assert verify_key("", stored, salt) is False


class TestGenerateRawKey:
    def test_returns_string(self) -> None:
        from openorbit.auth import generate_raw_key

        assert isinstance(generate_raw_key(), str)

    def test_each_call_returns_unique_key(self) -> None:
        from openorbit.auth import generate_raw_key

        assert generate_raw_key() != generate_raw_key()

    def test_minimum_length(self) -> None:
        from openorbit.auth import generate_raw_key

        # 40 bytes of entropy → at least 53 URL-safe base64 chars
        assert len(generate_raw_key()) >= 53


# ---------------------------------------------------------------------------
# Integration tests — HTTP layer (require async_client fixture)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCreateApiKey:
    async def test_missing_admin_key_returns_401(self, async_client) -> None:
        resp = await async_client.post("/v1/auth/keys", json={"name": "test"})
        assert resp.status_code == 401

    async def test_invalid_admin_key_returns_403(self, async_client) -> None:
        resp = await async_client.post(
            "/v1/auth/keys",
            json={"name": "test"},
            headers={"X-API-Key": "bad-key"},
        )
        assert resp.status_code == 403

    async def test_valid_bootstrap_key_creates_key(  # noqa: E501
        self, async_client, monkeypatch
    ) -> None:
        import openorbit.config as cfg_mod

        # Patch settings with a known admin key
        original = cfg_mod.get_settings()
        monkeypatch.setattr(original, "OPENORBIT_ADMIN_KEY", "test-admin-key-bootstrap")
        cfg_mod._settings = original

        resp = await async_client.post(
            "/v1/auth/keys",
            json={"name": "ci-key", "is_admin": False},
            headers={"X-API-Key": "test-admin-key-bootstrap"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "key" in data
        assert data["name"] == "ci-key"
        assert "id" in data
        assert data["is_admin"] is False

    async def test_response_contains_raw_key_once(  # noqa: E501
        self, async_client, monkeypatch
    ) -> None:
        import openorbit.config as cfg_mod

        original = cfg_mod.get_settings()
        monkeypatch.setattr(original, "OPENORBIT_ADMIN_KEY", "test-admin-key-bootstrap")
        cfg_mod._settings = original

        resp = await async_client.post(
            "/v1/auth/keys",
            json={"name": "raw-key-check"},
            headers={"X-API-Key": "test-admin-key-bootstrap"},
        )
        assert resp.status_code == 201
        body = resp.json()
        # Raw key must be present, non-empty, and URL-safe-base64-like
        assert len(body["key"]) >= 53


@pytest.mark.asyncio
class TestRevokeApiKey:
    async def test_revoke_unknown_id_returns_404(  # noqa: E501
        self, async_client, monkeypatch
    ) -> None:
        import openorbit.config as cfg_mod

        original = cfg_mod.get_settings()
        monkeypatch.setattr(original, "OPENORBIT_ADMIN_KEY", "test-admin-key-bootstrap")
        cfg_mod._settings = original

        resp = await async_client.delete(
            "/v1/auth/keys/99999",
            headers={"X-API-Key": "test-admin-key-bootstrap"},
        )
        assert resp.status_code == 404

    async def test_revoke_already_revoked_returns_409(  # noqa: E501
        self, async_client, monkeypatch
    ) -> None:
        import openorbit.config as cfg_mod

        original = cfg_mod.get_settings()
        monkeypatch.setattr(original, "OPENORBIT_ADMIN_KEY", "test-admin-key-bootstrap")
        cfg_mod._settings = original

        # Create then revoke
        create_resp = await async_client.post(
            "/v1/auth/keys",
            json={"name": "revoke-twice"},
            headers={"X-API-Key": "test-admin-key-bootstrap"},
        )
        key_id = create_resp.json()["id"]

        await async_client.delete(
            f"/v1/auth/keys/{key_id}",
            headers={"X-API-Key": "test-admin-key-bootstrap"},
        )
        second = await async_client.delete(
            f"/v1/auth/keys/{key_id}",
            headers={"X-API-Key": "test-admin-key-bootstrap"},
        )
        assert second.status_code == 409

    async def test_revoke_valid_key_returns_200(  # noqa: E501
        self, async_client, monkeypatch
    ) -> None:
        import openorbit.config as cfg_mod

        original = cfg_mod.get_settings()
        monkeypatch.setattr(original, "OPENORBIT_ADMIN_KEY", "test-admin-key-bootstrap")
        cfg_mod._settings = original

        create_resp = await async_client.post(
            "/v1/auth/keys",
            json={"name": "to-revoke"},
            headers={"X-API-Key": "test-admin-key-bootstrap"},
        )
        key_id = create_resp.json()["id"]

        resp = await async_client.delete(
            f"/v1/auth/keys/{key_id}",
            headers={"X-API-Key": "test-admin-key-bootstrap"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == key_id
        assert "revoked_at" in body

    async def test_revoked_key_cannot_authenticate(  # noqa: E501
        self, async_client, monkeypatch
    ) -> None:
        import openorbit.config as cfg_mod

        original = cfg_mod.get_settings()
        monkeypatch.setattr(original, "OPENORBIT_ADMIN_KEY", "test-admin-key-bootstrap")
        cfg_mod._settings = original

        # Create an admin key
        create_resp = await async_client.post(
            "/v1/auth/keys",
            json={"name": "to-revoke-then-use", "is_admin": True},
            headers={"X-API-Key": "test-admin-key-bootstrap"},
        )
        data = create_resp.json()
        raw_key = data["key"]
        key_id = data["id"]

        # Revoke it
        await async_client.delete(
            f"/v1/auth/keys/{key_id}",
            headers={"X-API-Key": "test-admin-key-bootstrap"},
        )

        # Attempt to use the revoked key
        resp = await async_client.post(
            "/v1/auth/keys",
            json={"name": "should-fail"},
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestPublicEndpointsUnaffected:
    async def test_get_launches_requires_no_key(self, async_client) -> None:
        resp = await async_client.get("/v1/launches")
        assert resp.status_code == 200

    async def test_get_sources_requires_no_key(self, async_client) -> None:
        resp = await async_client.get("/v1/sources")
        assert resp.status_code == 200

    async def test_health_requires_no_key(self, async_client) -> None:
        resp = await async_client.get("/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestRequireAdminDbKeyPath:
    """Cover lines 138-139, 141 — DB admin key lookup inside require_admin."""

    async def test_db_admin_key_authenticates_successfully(
        self, async_client, monkeypatch
    ) -> None:
        import openorbit.config as cfg_mod

        original = cfg_mod.get_settings()
        monkeypatch.setattr(original, "OPENORBIT_ADMIN_KEY", "bootstrap-admin-key")
        cfg_mod._settings = original

        # Create a DB-stored admin key via the bootstrap key
        create_resp = await async_client.post(
            "/v1/auth/keys",
            json={"name": "db-admin-key", "is_admin": True},
            headers={"X-API-Key": "bootstrap-admin-key"},
        )
        assert create_resp.status_code == 201
        raw_key = create_resp.json()["key"]

        # Now remove bootstrap key so only DB lookup is available
        monkeypatch.setattr(original, "OPENORBIT_ADMIN_KEY", "")
        cfg_mod._settings = original

        # The DB admin key must succeed via the DB lookup path (lines 137-141)
        resp = await async_client.post(
            "/v1/auth/keys",
            json={"name": "created-via-db-key"},
            headers={"X-API-Key": raw_key},
        )
        assert resp.status_code == 201

    async def test_db_admin_key_wrong_key_returns_403(
        self, async_client, monkeypatch
    ) -> None:
        import openorbit.config as cfg_mod

        original = cfg_mod.get_settings()
        # No bootstrap key, no DB key that matches "wrong-key"
        monkeypatch.setattr(original, "OPENORBIT_ADMIN_KEY", "")
        cfg_mod._settings = original

        resp = await async_client.post(
            "/v1/auth/keys",
            json={"name": "should-fail"},
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests for require_valid_key (lines 155-181) — tested via unit-level mocking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRequireValidKey:
    """Cover require_valid_key function (lines 155-181)."""

    async def test_missing_key_raises_401(self) -> None:
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from openorbit.auth import require_valid_key

        request = MagicMock()
        request.headers.get.return_value = None
        request.query_params.get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await require_valid_key(request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "API key required"

    async def test_bootstrap_key_succeeds(self, monkeypatch) -> None:
        from unittest.mock import MagicMock

        import openorbit.config as cfg_mod
        from openorbit.auth import require_valid_key

        original = cfg_mod.get_settings()
        monkeypatch.setattr(original, "OPENORBIT_ADMIN_KEY", "my-bootstrap-key")
        cfg_mod._settings = original

        request = MagicMock()
        request.headers.get.return_value = "my-bootstrap-key"
        request.query_params.get.return_value = None

        # Should return None without raising
        result = await require_valid_key(request)
        assert result is None

    async def test_invalid_key_raises_403(self, monkeypatch) -> None:
        from contextlib import asynccontextmanager
        from unittest.mock import AsyncMock, MagicMock, patch

        import openorbit.config as cfg_mod
        from fastapi import HTTPException
        from openorbit.auth import require_valid_key

        original = cfg_mod.get_settings()
        monkeypatch.setattr(original, "OPENORBIT_ADMIN_KEY", "")
        cfg_mod._settings = original

        # Mock get_db to return empty rows — no matching key
        @asynccontextmanager
        async def mock_get_db():  # type: ignore[override]
            cursor = AsyncMock()
            cursor.fetchall = AsyncMock(return_value=[])
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=cursor)
            cm.__aexit__ = AsyncMock(return_value=None)
            db = MagicMock()
            db.execute = MagicMock(return_value=cm)
            yield db

        request = MagicMock()
        request.headers.get.return_value = "bad-key"
        request.query_params.get.return_value = None

        with patch("openorbit.db.get_db", mock_get_db):
            with pytest.raises(HTTPException) as exc_info:
                await require_valid_key(request)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Invalid or revoked API key"

    async def test_valid_db_key_succeeds(self, monkeypatch) -> None:
        from contextlib import asynccontextmanager
        from unittest.mock import AsyncMock, MagicMock, patch

        import openorbit.config as cfg_mod
        from openorbit.auth import generate_salt, hash_key, require_valid_key

        original = cfg_mod.get_settings()
        monkeypatch.setattr(original, "OPENORBIT_ADMIN_KEY", "")
        cfg_mod._settings = original

        raw_key = "my-valid-key"
        salt = generate_salt()
        stored_hash = hash_key(raw_key, salt)

        @asynccontextmanager
        async def mock_get_db():  # type: ignore[override]
            cursor = AsyncMock()
            cursor.fetchall = AsyncMock(
                return_value=[{"key_hash": stored_hash, "salt": salt}]
            )
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=cursor)
            cm.__aexit__ = AsyncMock(return_value=None)
            db = MagicMock()
            db.execute = MagicMock(return_value=cm)
            yield db

        request = MagicMock()
        request.headers.get.return_value = raw_key
        request.query_params.get.return_value = None

        with patch("openorbit.db.get_db", mock_get_db):
            result = await require_valid_key(request)
        assert result is None

    async def test_query_param_key_accepted(self, monkeypatch) -> None:
        from unittest.mock import MagicMock

        import openorbit.config as cfg_mod
        from openorbit.auth import require_valid_key

        original = cfg_mod.get_settings()
        monkeypatch.setattr(original, "OPENORBIT_ADMIN_KEY", "qp-bootstrap")
        cfg_mod._settings = original

        request = MagicMock()
        request.headers.get.return_value = None  # No header
        request.query_params.get.return_value = "qp-bootstrap"  # Key via query param

        result = await require_valid_key(request)
        assert result is None
