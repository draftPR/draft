"""Tests for webhook notification service."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.webhook_service import _build_payload, _sign_payload, fire_webhooks


def test_build_payload():
    payload = _build_payload(
        event="ticket.transitioned",
        ticket_id="t1",
        ticket_title="Fix bug",
        board_id="b1",
        from_state="proposed",
        to_state="approved",
        actor_type="human",
        actor_id="user1",
        reason="Looks good",
    )
    assert payload["event"] == "ticket.transitioned"
    assert payload["ticket"]["id"] == "t1"
    assert payload["ticket"]["from_state"] == "proposed"
    assert payload["ticket"]["to_state"] == "approved"
    assert payload["actor"]["type"] == "human"
    assert payload["reason"] == "Looks good"
    assert "timestamp" in payload


def test_sign_payload():
    data = b'{"test": true}'
    secret = "mysecret"
    sig = _sign_payload(data, secret)
    expected = hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()
    assert sig == expected


@pytest.mark.asyncio
async def test_fire_webhooks_empty():
    """No webhooks = no-op."""
    await fire_webhooks(
        [],
        ticket_id="t1",
        ticket_title="Test",
        board_id="b1",
        from_state="proposed",
        to_state="approved",
        actor_type="human",
        actor_id=None,
        reason=None,
    )


@pytest.mark.asyncio
async def test_fire_webhooks_posts_to_url():
    """Webhook sends POST with correct payload."""
    mock_response = AsyncMock()
    mock_response.status_code = 200

    with patch("app.services.webhook_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        webhooks = [{"id": "w1", "url": "https://example.com/hook", "events": ["*"]}]
        await fire_webhooks(
            webhooks,
            ticket_id="t1",
            ticket_title="Fix bug",
            board_id="b1",
            from_state="proposed",
            to_state="approved",
            actor_type="human",
            actor_id="user1",
            reason=None,
        )

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[1]["headers"]["Content-Type"] == "application/json"
        payload = json.loads(call_args[1]["content"])
        assert payload["event"] == "ticket.transitioned"
        assert payload["ticket"]["id"] == "t1"


@pytest.mark.asyncio
async def test_fire_webhooks_with_secret():
    """Webhook includes HMAC signature when secret is set."""
    mock_response = AsyncMock()
    mock_response.status_code = 200

    with patch("app.services.webhook_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        webhooks = [
            {
                "id": "w1",
                "url": "https://example.com/hook",
                "events": ["*"],
                "secret": "s3cret",
            }
        ]
        await fire_webhooks(
            webhooks,
            ticket_id="t1",
            ticket_title="Test",
            board_id="b1",
            from_state="proposed",
            to_state="approved",
            actor_type="agent",
            actor_id=None,
            reason=None,
        )

        call_args = mock_client.post.call_args
        headers = call_args[1]["headers"]
        assert "X-Webhook-Signature" in headers
        assert headers["X-Webhook-Signature"].startswith("sha256=")


@pytest.mark.asyncio
async def test_fire_webhooks_event_filter():
    """Webhook with non-matching event filter is skipped."""
    with patch("app.services.webhook_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        webhooks = [
            {
                "id": "w1",
                "url": "https://example.com/hook",
                "events": ["ticket.deleted"],
            }
        ]
        await fire_webhooks(
            webhooks,
            ticket_id="t1",
            ticket_title="Test",
            board_id="b1",
            from_state="proposed",
            to_state="approved",
            actor_type="human",
            actor_id=None,
            reason=None,
        )

        mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_fire_webhooks_error_does_not_raise():
    """Webhook delivery failure is swallowed (best-effort)."""
    with patch("app.services.webhook_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        webhooks = [{"id": "w1", "url": "https://example.com/hook", "events": ["*"]}]
        # Should not raise
        await fire_webhooks(
            webhooks,
            ticket_id="t1",
            ticket_title="Test",
            board_id="b1",
            from_state="proposed",
            to_state="approved",
            actor_type="human",
            actor_id=None,
            reason=None,
        )
