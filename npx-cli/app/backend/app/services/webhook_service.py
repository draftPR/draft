"""Webhook notification service for ticket state changes.

Sends POST requests to configured webhook URLs when ticket status changes.
Webhooks are stored in Board.config["webhooks"] as a list of webhook objects:
  [{"url": "https://...", "events": ["*"], "secret": "optional-hmac-key"}]

Events:
  - "ticket.transitioned" — any state change
  - "*" — all events (same as above, for future extensibility)
"""

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime

import httpx

logger = logging.getLogger(__name__)

# Timeout for webhook HTTP calls (connect, read)
WEBHOOK_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


def _build_payload(
    *,
    event: str,
    ticket_id: str,
    ticket_title: str,
    board_id: str,
    from_state: str | None,
    to_state: str,
    actor_type: str,
    actor_id: str | None,
    reason: str | None,
) -> dict:
    """Build the webhook JSON payload."""
    return {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        "ticket": {
            "id": ticket_id,
            "title": ticket_title,
            "board_id": board_id,
            "from_state": from_state,
            "to_state": to_state,
        },
        "actor": {
            "type": actor_type,
            "id": actor_id,
        },
        "reason": reason,
    }


async def fire_webhooks(
    webhooks: list[dict],
    *,
    ticket_id: str,
    ticket_title: str,
    board_id: str,
    from_state: str | None,
    to_state: str,
    actor_type: str,
    actor_id: str | None,
    reason: str | None,
) -> None:
    """Send webhook notifications for a ticket transition.

    Non-blocking best-effort: logs errors but never raises.
    """
    if not webhooks:
        return

    event = "ticket.transitioned"
    payload = _build_payload(
        event=event,
        ticket_id=ticket_id,
        ticket_title=ticket_title,
        board_id=board_id,
        from_state=from_state,
        to_state=to_state,
        actor_type=actor_type,
        actor_id=actor_id,
        reason=reason,
    )
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()

    async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
        for wh in webhooks:
            url = wh.get("url")
            if not url:
                continue

            # Check event filter
            events = wh.get("events", ["*"])
            if "*" not in events and event not in events:
                continue

            headers = {"Content-Type": "application/json"}
            secret = wh.get("secret")
            if secret:
                headers["X-Webhook-Signature"] = (
                    f"sha256={_sign_payload(payload_bytes, secret)}"
                )

            try:
                resp = await client.post(url, content=payload_bytes, headers=headers)
                logger.info(
                    "Webhook delivered: url=%s status=%d ticket=%s %s->%s",
                    url,
                    resp.status_code,
                    ticket_id,
                    from_state,
                    to_state,
                )
            except Exception:
                logger.warning(
                    "Webhook failed: url=%s ticket=%s", url, ticket_id, exc_info=True
                )
