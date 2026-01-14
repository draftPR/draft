"""Queued message service for chaining prompts during execution.

Allows users to queue the next prompt while an execution is in progress.
When the current execution completes, the queued message is automatically
executed. Similar to vibe-kanban's QueuedMessageService.

Uses Redis for cross-process persistence.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime

import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_KEY_PREFIX = "queued_message:"
FOLLOWUP_KEY_PREFIX = "followup_prompt:"  # For active follow-up prompts
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
    
    def __init__(self):
        self._redis: redis.Redis | None = None
    
    def _get_redis(self) -> redis.Redis:
        """Lazy-init Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(REDIS_URL)
        return self._redis
    
    def _get_key(self, ticket_id: str) -> str:
        """Get Redis key for a ticket's queued message."""
        return f"{QUEUE_KEY_PREFIX}{ticket_id}"
    
    def queue_message(self, ticket_id: str, message: str) -> QueuedMessage:
        """Queue a follow-up message for a ticket.
        
        Replaces any existing queued message for this ticket.
        
        Args:
            ticket_id: The ticket ID
            message: The follow-up prompt/message
            
        Returns:
            The queued message
        """
        queued = QueuedMessage(
            ticket_id=ticket_id,
            message=message,
            queued_at=datetime.now(UTC),
        )
        
        r = self._get_redis()
        key = self._get_key(ticket_id)
        r.setex(key, QUEUE_TTL, json.dumps(queued.to_dict()))
        
        logger.info(f"Queued message for ticket {ticket_id}: {message[:50]}...")
        return queued
    
    def get_queued(self, ticket_id: str) -> QueuedMessage | None:
        """Get the queued message for a ticket (if any).
        
        Args:
            ticket_id: The ticket ID
            
        Returns:
            The queued message, or None if no message is queued
        """
        r = self._get_redis()
        key = self._get_key(ticket_id)
        data = r.get(key)
        
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
        
        Args:
            ticket_id: The ticket ID
            
        Returns:
            The queued message, or None if no message was queued
        """
        r = self._get_redis()
        key = self._get_key(ticket_id)
        
        # Get and delete atomically
        data = r.getdel(key)
        
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
        """Cancel/remove a queued message for a ticket.
        
        Args:
            ticket_id: The ticket ID
            
        Returns:
            True if a message was cancelled, False if none existed
        """
        r = self._get_redis()
        key = self._get_key(ticket_id)
        deleted = r.delete(key)
        
        if deleted:
            logger.info(f"Cancelled queued message for ticket {ticket_id}")
        return bool(deleted)
    
    def has_queued(self, ticket_id: str) -> bool:
        """Check if a ticket has a queued message.
        
        Args:
            ticket_id: The ticket ID
            
        Returns:
            True if a message is queued
        """
        r = self._get_redis()
        key = self._get_key(ticket_id)
        return r.exists(key) > 0
    
    # ========== Follow-up prompt storage (for worker) ==========
    
    def set_followup_prompt(self, ticket_id: str, prompt: str) -> None:
        """Set a follow-up prompt for the worker to pick up.
        
        Used by the planner when executing a queued message.
        The worker checks this when building the prompt bundle.
        
        Args:
            ticket_id: The ticket ID
            prompt: The follow-up prompt
        """
        r = self._get_redis()
        key = f"{FOLLOWUP_KEY_PREFIX}{ticket_id}"
        r.setex(key, 3600, prompt)  # 1 hour TTL (should be consumed quickly)
        logger.info(f"Set follow-up prompt for ticket {ticket_id}")
    
    def get_followup_prompt(self, ticket_id: str) -> str | None:
        """Get and clear the follow-up prompt for a ticket.
        
        Used by the worker when building the prompt bundle.
        Returns None if no follow-up prompt is set.
        
        Args:
            ticket_id: The ticket ID
            
        Returns:
            The follow-up prompt, or None
        """
        r = self._get_redis()
        key = f"{FOLLOWUP_KEY_PREFIX}{ticket_id}"
        prompt = r.getdel(key)
        if prompt:
            logger.info(f"Retrieved follow-up prompt for ticket {ticket_id}")
            return prompt.decode() if isinstance(prompt, bytes) else prompt
        return None


# Global singleton
queued_message_service = QueuedMessageService()
