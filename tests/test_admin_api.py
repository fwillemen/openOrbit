"""Integration tests for Admin API endpoints (PO-016).

Covers:
- GET /v1/admin/sources — 401 no key, 403 bad key, 200 valid key
- POST /v1/admin/sources/{id}/refresh — 202 known source, 404 unknown, 401/403 auth
- GET /v1/admin/stats — 200 valid key, correct shape, 401 no key
"""
from __future__ import annotations

import pytest

ADMIN_KEY = "test-admin-key-bootstrap"


def _patch_admin_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch settings to use a known admin key."""
    import openorbit.config as cfg_mod

    original = cfg_mod.get_settings()
    monkeypatch.setattr(original, "OPENORBIT_ADMIN_KEY", ADMIN_KEY)
    cfg_mod._settings = original


@pytest.mark.asyncio
class TestListSourcesHealth:
    async def test_missing_key_returns_401(self, async_client) -> None:
        resp = await async_client.get("/v1/admin/sources")
        assert resp.status_code == 401

    async def test_invalid_key_returns_403(self, async_client) -> None:
        resp = await async_client.get(
            "/v1/admin/sources",
            headers={"X-API-Key": "wrong-key-xyz"},
        )
        assert resp.status_code == 403

    async def test_valid_key_returns_200_list(self, async_client, monkeypatch) -> None:
        _patch_admin_key(monkeypatch)
        resp = await async_client.get(
            "/v1/admin/sources",
            headers={"X-API-Key": ADMIN_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_response_items_have_required_fields(self, async_client, monkeypatch) -> None:
        _patch_admin_key(monkeypatch)
        resp = await async_client.get(
            "/v1/admin/sources",
            headers={"X-API-Key": ADMIN_KEY},
        )
        assert resp.status_code == 200
        items = resp.json()
        for item in items:
            assert "id" in item
            assert "name" in item
            assert "url" in item
            assert "scraper_class" in item
            assert "enabled" in item
            assert "source_tier" in item
            assert "event_count" in item
            assert "error_rate" in item


@pytest.mark.asyncio
class TestRefreshSource:
    async def test_missing_key_returns_401(self, async_client) -> None:
        resp = await async_client.post("/v1/admin/sources/1/refresh")
        assert resp.status_code == 401

    async def test_invalid_key_returns_403(self, async_client) -> None:
        resp = await async_client.post(
            "/v1/admin/sources/1/refresh",
            headers={"X-API-Key": "bad-key"},
        )
        assert resp.status_code == 403

    async def test_unknown_source_returns_404(self, async_client, monkeypatch) -> None:
        _patch_admin_key(monkeypatch)
        resp = await async_client.post(
            "/v1/admin/sources/99999/refresh",
            headers={"X-API-Key": ADMIN_KEY},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Source not found"

    async def test_known_source_returns_202(self, async_client, monkeypatch) -> None:
        _patch_admin_key(monkeypatch)

        # First find a source id from the sources list
        sources_resp = await async_client.get(
            "/v1/admin/sources",
            headers={"X-API-Key": ADMIN_KEY},
        )
        sources = sources_resp.json()
        if not sources:
            pytest.skip("No sources seeded in test DB")

        source_id = sources[0]["id"]
        resp = await async_client.post(
            f"/v1/admin/sources/{source_id}/refresh",
            headers={"X-API-Key": ADMIN_KEY},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "triggered"
        assert body["source_id"] == str(source_id)


@pytest.mark.asyncio
class TestAdminStats:
    async def test_missing_key_returns_401(self, async_client) -> None:
        resp = await async_client.get("/v1/admin/stats")
        assert resp.status_code == 401

    async def test_invalid_key_returns_403(self, async_client) -> None:
        resp = await async_client.get(
            "/v1/admin/stats",
            headers={"X-API-Key": "bad-key"},
        )
        assert resp.status_code == 403

    async def test_valid_key_returns_200_correct_shape(self, async_client, monkeypatch) -> None:
        _patch_admin_key(monkeypatch)
        resp = await async_client.get(
            "/v1/admin/stats",
            headers={"X-API-Key": ADMIN_KEY},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "total_events" in body
        assert "events_by_source" in body
        assert "events_by_type" in body
        assert "events_by_lifecycle" in body
        assert "avg_confidence" in body
        assert "last_refresh_at" in body
        assert isinstance(body["total_events"], int)
        assert isinstance(body["events_by_source"], dict)
        assert isinstance(body["events_by_type"], dict)
        assert isinstance(body["events_by_lifecycle"], dict)
        assert isinstance(body["avg_confidence"], float)
