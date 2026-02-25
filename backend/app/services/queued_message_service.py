"""Queued message service for chaining prompts during execution.

Allows users to queue the next prompt while an execution is in progress.
When the current execution completes, the queued message is automatically
executed.

Uses SQLite kv_store for persistence.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

QUEUE_KEY_PREFIX = "queued_message:"
FOLLOWUP_KEY_PREFIX = "followup_prompt:"
QUEUE_TTL = 86400  # 24 hours


@dataclass
class QueuedMessage:
    """A queued follow-up message."""
    ticket_id: str
    message: str
    queued_at: datetime

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "ticket_id": self.ticket_id,
            "message": self.message,
            "queued_at": self.queued_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QueuedMessage":
        """Deserialize from dict."""
        return cls(
            ticket_id=data["ticket_id"],
            message=data["message"],
            queued_at=datetime.fromisoformat(data["queued_at"]),
        )


class QueuedMessageService:
    """Service for queuing follow-up messages during execution.

    One queued message per ticket. New messages replace old ones.
    """

    def _get_key(self, ticket_id: str) -> str:
        """Get key for a ticket's queued message."""
        return f"{QUEUE_KEY_PREFIX}{ticket_id}"

    def queue_message(self, ticket_id: str, message: str) -> QueuedMessage:
        """Queue a follow-up message for a ticket.

        Replaces any existing queued message for this ticket.
        """
        from app.sqlite_kv import kv_set

        queued = QueuedMessage(
            ticket_id=ticket_id,
            message=message,
            queued_at=datetime.now(UTC),
        )

        key = self._get_key(ticket_id)
        kv_set(key, json.dumps(queued.to_dict()), ttl_seconds=QUEUE_TTL)

        logger.info(f"Queued message for ticket {ticket_id}: {message[:50]}...")
        return queued

    def get_queued(self, ticket_id: str) -> QueuedMessage | None:
        """Get the queued message for a ticket (if any)."""
        from app.sqlite_kv import kv_get

        key = self._get_key(ticket_id)
        data = kv_get(key)

        if data is None:
            return None

        try:
            return QueuedMessage.from_dict(json.loads(data))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Invalid queued message for {ticket_id}: {e}")
            return None

    def take_queued(self, ticket_id: str) -> QueuedMessage | None:
        """Take (remove and return) the queued message for a ticket.

        Used by the planner to consume queued messages after execution.
        """
        from app.sqlite_kv import kv_take

        key = self._get_key(ticket_id)
        data = kv_take(key)

        if data is None:
            return None

        try:
            msg = QueuedMessage.from_dict(json.loads(data))
            logger.info(f"Consumed queued message for ticket {ticket_id}")
            return msg
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Invalid queued message for {ticket_id}: {e}")
            return None

    def cancel_queued(self, ticket_id: str) -> bool:
        """Cancel/remove a queued message for a ticket."""
        from app.sqlite_kv import kv_delete

        key = self._get_key(ticket_id)
        deleted = kv_delete(key)

        if deleted:
            logger.info(f"Cancelled queued message for ticket {ticket_id}")
        return deleted

    def has_queued(self, ticket_id: str) -> bool:
        """Check if a ticket has a queued message."""
        from app.sqlite_kv import kv_exists

        key = self._get_key(ticket_id)
        return kv_exists(key)

    # ========== Follow-up prompt storage (for worker) ==========

    def set_followup_prompt(self, ticket_id: str, prompt: str) -> None:
        """Set a follow-up prompt for the worker to pick up."""
        from app.sqlite_kv import kv_set

        key = f"{FOLLOWUP_KEY_PREFIX}{ticket_id}"
        kv_set(key, prompt, ttl_seconds=3600)
        logger.info(f"Set follow-up prompt for ticket {ticket_id}")

    def get_followup_prompt(self, ticket_id: str) -> str | None:
        """Get and clear the follow-up prompt for a ticket."""
        from app.sqlite_kv import kv_take

        key = f"{FOLLOWUP_KEY_PREFIX}{ticket_id}"
        prompt = kv_take(key)

        if prompt:
            logger.info(f"Retrieved follow-up prompt for ticket {ticket_id}")
            return prompt.decode() if isinstance(prompt, bytes) else prompt
        return None


# Global singleton
queued_message_service = QueuedMessageService()
