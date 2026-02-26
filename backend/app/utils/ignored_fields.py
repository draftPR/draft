"""Utility for tracking and logging ignored request fields.

SECURITY: Only echo KNOWN deprecated fields in X-Ignored-Fields header.
Arbitrary unknown fields are logged internally but NOT echoed to client
(prevents using this as an echo channel).

When deprecated fields are sent:
1. Add X-Ignored-Fields header with ONLY known deprecated fields
2. Log once per client_id per day (avoid spam)
3. Unknown fields: log internally only, do NOT echo
"""

import logging
from datetime import date
from typing import Any

from fastapi import Request, Response

logger = logging.getLogger(__name__)

# Track which clients have been warned today: {(client_id, field): date}
_warned_today: dict[tuple[str, str], date] = {}

# ALLOWLIST: Only these deprecated fields are echoed in X-Ignored-Fields
# This prevents using the header as an echo channel for arbitrary data
KNOWN_DEPRECATED_FIELDS = frozenset({
    "workspace_path",  # Removed for security - use board.repo_root instead
    "repo_path",       # Alias for workspace_path
})


def get_client_id(request: Request) -> str:
    """Get client identifier from request."""
    client_id = request.headers.get("X-Client-ID")
    if client_id and len(client_id) <= 64:
        return client_id
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


def check_ignored_fields(
    request: Request,
    raw_body: dict[str, Any],
    allowed_fields: set[str],
) -> list[str]:
    """Check for ignored/deprecated fields in request body.

    SECURITY: Only KNOWN_DEPRECATED_FIELDS are returned for echoing.
    Unknown extra fields are logged internally but NOT returned.

    Args:
        request: The FastAPI request
        raw_body: Parsed request body dict
        allowed_fields: Fields that are actually used by the endpoint

    Returns:
        List of KNOWN deprecated field names that were sent (safe to echo)
    """
    if not raw_body:
        return []

    sent_fields = set(raw_body.keys())
    all_ignored = sent_fields - allowed_fields

    if not all_ignored:
        return []

    client_id = get_client_id(request)
    today = date.today()

    # Split into known deprecated (safe to echo) and unknown (log only)
    known_deprecated_sent = all_ignored & KNOWN_DEPRECATED_FIELDS
    unknown_sent = all_ignored - KNOWN_DEPRECATED_FIELDS

    # Log known deprecated fields (once per client per day)
    for field in known_deprecated_sent:
        cache_key = (client_id, field)
        if _warned_today.get(cache_key) != today:
            logger.warning(
                f"Client {client_id} sent deprecated field '{field}' - "
                f"this field is ignored for security. "
                f"Please remove it from your requests."
            )
            _warned_today[cache_key] = today

    # Log unknown fields internally only (do NOT echo to client)
    if unknown_sent:
        # Only log once per client per day to avoid spam
        cache_key = (client_id, "__unknown_fields__")
        if _warned_today.get(cache_key) != today:
            logger.info(
                f"Client {client_id} sent unknown fields: {sorted(unknown_sent)} - "
                f"these are silently ignored."
            )
            _warned_today[cache_key] = today

    # Return ONLY known deprecated fields (safe to echo)
    return sorted(known_deprecated_sent)


def add_ignored_fields_header(response: Response, ignored_fields: list[str]) -> None:
    """Add X-Ignored-Fields header to response.

    SECURITY: Only adds header if ignored_fields contains known deprecated fields.
    The ignored_fields list should come from check_ignored_fields() which already
    filters to KNOWN_DEPRECATED_FIELDS only.
    """
    if ignored_fields:
        # Double-check: only include known deprecated fields
        safe_fields = [f for f in ignored_fields if f in KNOWN_DEPRECATED_FIELDS]
        if safe_fields:
            response.headers["X-Ignored-Fields"] = ", ".join(safe_fields)


def cleanup_old_warnings() -> None:
    """Clean up warning cache for old dates."""
    global _warned_today
    today = date.today()
    _warned_today = {k: v for k, v in _warned_today.items() if v == today}

