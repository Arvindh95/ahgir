"""Tests for the Re-ID sidecar HTTP client.

Re-ID is fail-soft by design — any failure path MUST return None, not raise.
These tests enforce that contract so a reid-api outage cannot crash the
indexer or scan endpoint.
"""
from __future__ import annotations

from unittest.mock import patch, AsyncMock, MagicMock

import httpx
import pytest

from app.config import settings
from app.reid_client import compute_embedding, healthcheck


@pytest.fixture(autouse=True)
def _enable_reid():
    # The client short-circuits when both indexing and scan flags are off.
    # Enable indexing for the test session so we exercise the HTTP path.
    original = settings.reid_enabled_indexing
    settings.reid_enabled_indexing = True
    try:
        yield
    finally:
        settings.reid_enabled_indexing = original


@pytest.mark.asyncio
async def test_returns_none_on_empty_input():
    assert await compute_embedding(b"") is None


@pytest.mark.asyncio
async def test_returns_none_when_both_flags_off():
    # _enable_reid autouse flips indexing on; explicitly turn both off here
    # to exercise the short-circuit branch. Cleanup is handled by the
    # autouse fixtures (file-level and conftest) restoring originals.
    settings.reid_enabled_indexing = False
    settings.reid_enabled_scan = False
    assert await compute_embedding(b"abc") is None


@pytest.mark.asyncio
async def test_happy_path_returns_512_vector():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"embedding": [0.1] * 512, "dim": 512}

    with patch("app.reid_client.httpx.AsyncClient") as mock_client_cls:
        client_ctx = mock_client_cls.return_value.__aenter__.return_value
        client_ctx.post = AsyncMock(return_value=fake_response)
        result = await compute_embedding(b"fake-image-bytes")

    assert result is not None
    assert len(result) == 512
    assert all(isinstance(v, float) for v in result)


@pytest.mark.asyncio
async def test_timeout_returns_none():
    with patch("app.reid_client.httpx.AsyncClient") as mock_client_cls:
        client_ctx = mock_client_cls.return_value.__aenter__.return_value
        client_ctx.post = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )
        result = await compute_embedding(b"x")
    assert result is None


@pytest.mark.asyncio
async def test_http_error_returns_none():
    with patch("app.reid_client.httpx.AsyncClient") as mock_client_cls:
        client_ctx = mock_client_cls.return_value.__aenter__.return_value
        client_ctx.post = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        result = await compute_embedding(b"x")
    assert result is None


@pytest.mark.asyncio
async def test_503_returns_none():
    fake_response = MagicMock()
    fake_response.status_code = 503
    fake_response.text = "model not loaded"
    with patch("app.reid_client.httpx.AsyncClient") as mock_client_cls:
        client_ctx = mock_client_cls.return_value.__aenter__.return_value
        client_ctx.post = AsyncMock(return_value=fake_response)
        result = await compute_embedding(b"x")
    assert result is None


@pytest.mark.asyncio
async def test_malformed_json_returns_none():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.side_effect = ValueError("not json")
    fake_response.text = "not json at all"
    with patch("app.reid_client.httpx.AsyncClient") as mock_client_cls:
        client_ctx = mock_client_cls.return_value.__aenter__.return_value
        client_ctx.post = AsyncMock(return_value=fake_response)
        result = await compute_embedding(b"x")
    assert result is None


@pytest.mark.asyncio
async def test_wrong_dim_returns_none():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"embedding": [0.1] * 256, "dim": 256}
    with patch("app.reid_client.httpx.AsyncClient") as mock_client_cls:
        client_ctx = mock_client_cls.return_value.__aenter__.return_value
        client_ctx.post = AsyncMock(return_value=fake_response)
        result = await compute_embedding(b"x")
    assert result is None


@pytest.mark.asyncio
async def test_missing_embedding_key_returns_none():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"dim": 512}
    with patch("app.reid_client.httpx.AsyncClient") as mock_client_cls:
        client_ctx = mock_client_cls.return_value.__aenter__.return_value
        client_ctx.post = AsyncMock(return_value=fake_response)
        result = await compute_embedding(b"x")
    assert result is None


@pytest.mark.asyncio
async def test_healthcheck_returns_false_on_error():
    with patch("app.reid_client.httpx.AsyncClient") as mock_client_cls:
        client_ctx = mock_client_cls.return_value.__aenter__.return_value
        client_ctx.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        assert await healthcheck() is False


@pytest.mark.asyncio
async def test_healthcheck_returns_true_on_200():
    fake_response = MagicMock()
    fake_response.status_code = 200
    with patch("app.reid_client.httpx.AsyncClient") as mock_client_cls:
        client_ctx = mock_client_cls.return_value.__aenter__.return_value
        client_ctx.get = AsyncMock(return_value=fake_response)
        assert await healthcheck() is True
