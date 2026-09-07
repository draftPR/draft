"""Nadir tier routing — pick an executor profile per ticket by task complexity.

Calls Nadir's bucket API (https://getnadir.com/skill), which classifies a task
as simple / medium / complex. Draft maps that tier to an executor profile via
`routing_config.by_tier`. Nadir returns a model tier, not an executor, so the
tier->profile mapping is where codex vs claude gets decided.

Fail-open: any network/API problem yields `profile=None` (board default).
"""

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

from app.services.config_service import RoutingConfig

logger = logging.getLogger(__name__)

TIERS = ("simple", "medium", "complex")
PROMPT_MAX_CHARS = 2000


@dataclass
class RoutingDecision:
    profile: str | None
    tier: str | None = None
    confidence: float | None = None
    request_id: str | None = None
    error: str | None = None

    def as_payload(self) -> dict:
        return asdict(self)


def route_ticket(
    title: str,
    description: str | None,
    config: RoutingConfig,
    timeout: float = 5.0,
) -> RoutingDecision:
    """Ask Nadir for a tier and map it to an executor profile name."""
    if not config.enabled or not config.by_tier:
        return RoutingDecision(profile=None)

    text = f"{title}\n\n{description or ''}".strip()[:PROMPT_MAX_CHARS]
    payload = {
        "prompt": text,
        "source": "draft",
        "context": {"expected_turns": config.expected_turns},
    }
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("NADIR_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        req = urllib.request.Request(
            config.nadir_url,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception as exc:  # fail open: HTTP errors, timeouts, bad JSON
        logger.warning("Nadir routing unavailable, using board default: %s", exc)
        return RoutingDecision(profile=None, error=str(exc)[:200])

    plan = data.get("plan") or {}
    tier = plan.get("tier") or data.get("bucket")
    if tier not in TIERS:
        return RoutingDecision(profile=None, error=f"unexpected tier: {tier!r}")

    profile = config.by_tier.get(tier)
    if profile is None:
        logger.info("Nadir tier %s has no profile in routing_config.by_tier", tier)
    return RoutingDecision(
        profile=profile,
        tier=tier,
        confidence=data.get("confidence"),
        request_id=data.get("request_id"),
    )
