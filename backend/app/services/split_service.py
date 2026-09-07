"""Split a ticket into sub-tickets.

The executor decides: instead of implementing an oversized ticket it writes
`.draft/subtasks.json` in its worktree (see PromptBundleBuilder split section).
The worker parses that file, creates one child ticket per subtask (each with
its own worktree and, via Nadir, its own executor profile), and blocks the
parent until the children are done.
"""

import json
import logging
from dataclasses import dataclass

from app.database_sync import get_sync_db
from app.models.enums import EventType
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.services.config_service import DraftConfig
from app.services.routing_service import TIERS, route_ticket
from app.state_machine import ActorType, TicketState

logger = logging.getLogger(__name__)

SUBTASKS_RELPATH = ".draft/subtasks.json"
MIN_CHILDREN = 2


class SubtasksError(ValueError):
    """The subtasks file is missing, malformed, or violates the rules."""


@dataclass
class Subtask:
    title: str
    description: str
    blocked_by: str | None = None
    complexity: str | None = None


def parse_subtasks(raw: str, max_children: int) -> list[Subtask]:
    """Parse and validate the executor's subtasks JSON. Raises SubtasksError."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SubtasksError(f"invalid JSON: {exc}") from exc

    items = data.get("subtasks") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise SubtasksError("expected {'subtasks': [...]}")
    if not MIN_CHILDREN <= len(items) <= max_children:
        raise SubtasksError(
            f"need {MIN_CHILDREN}..{max_children} subtasks, got {len(items)}"
        )

    subtasks: list[Subtask] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise SubtasksError(f"subtask {i} is not an object")
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        if not title or not description:
            raise SubtasksError(f"subtask {i} needs title and description")
        blocked_by = item.get("blocked_by")
        blocked_by = str(blocked_by).strip() or None if blocked_by else None
        complexity = item.get("complexity")
        if complexity is not None and complexity not in TIERS:
            raise SubtasksError(f"subtask {i}: complexity must be one of {TIERS}")
        subtasks.append(Subtask(title[:255], description, blocked_by, complexity))

    titles = {s.title.lower() for s in subtasks}
    if len(titles) != len(subtasks):
        raise SubtasksError("subtask titles must be unique")
    for s in subtasks:
        if s.blocked_by and s.blocked_by.lower() not in titles:
            raise SubtasksError(
                f"'{s.title}' blocked_by unknown title '{s.blocked_by}'"
            )
        if s.blocked_by and s.blocked_by.lower() == s.title.lower():
            raise SubtasksError(f"'{s.title}' cannot block itself")

    # Cycle check: each subtask has at most one blocker, so follow the chain.
    blocker_of = {s.title.lower(): (s.blocked_by or "").lower() for s in subtasks}
    for start in blocker_of:
        seen, cur = set(), start
        while cur:
            if cur in seen:
                raise SubtasksError("blocked_by forms a cycle")
            seen.add(cur)
            cur = blocker_of.get(cur, "")
    return subtasks


def create_child_tickets_sync(
    parent_ticket_id: str,
    subtasks: list[Subtask],
    config: DraftConfig,
    actor_id: str = "execute_worker",
) -> list[str]:
    """Create PLANNED child tickets for `subtasks` under the parent.

    Each child gets `executor_profile` from Nadir routing (if enabled) and
    `blocked_by_ticket_id` resolved by title within this batch.
    Returns the new ticket ids in subtask order.
    """
    routing = config.routing_config
    with get_sync_db() as db:
        parent = db.query(Ticket).filter(Ticket.id == parent_ticket_id).first()
        if parent is None:
            raise SubtasksError(f"parent ticket {parent_ticket_id} not found")

        by_title: dict[str, Ticket] = {}
        for order, st in enumerate(subtasks):
            decision = route_ticket(st.title, st.description, routing)
            profile = decision.profile
            if profile and profile not in config.executor_profiles:
                logger.warning(
                    "routing_config.by_tier -> '%s' is not a defined executor profile",
                    profile,
                )
                profile = None

            child = Ticket(
                goal_id=parent.goal_id,
                board_id=parent.board_id,
                parent_ticket_id=parent.id,
                title=st.title,
                description=st.description,
                state=TicketState.PLANNED.value,
                priority=parent.priority,
                sort_order=order,
                executor_profile=profile,
            )
            db.add(child)
            db.flush()
            by_title[st.title.lower()] = child

            db.add(
                TicketEvent(
                    ticket_id=child.id,
                    event_type=EventType.CREATED.value,
                    from_state=None,
                    to_state=TicketState.PLANNED.value,
                    actor_type=ActorType.EXECUTOR.value,
                    actor_id=actor_id,
                    reason=f"Split from '{parent.title}'",
                    payload_json=json.dumps(
                        {
                            "parent_ticket_id": parent.id,
                            "split": True,
                            "complexity_hint": st.complexity,
                            "routing": decision.as_payload(),
                        }
                    ),
                )
            )

        for st in subtasks:
            if st.blocked_by:
                by_title[st.title.lower()].blocked_by_ticket_id = by_title[
                    st.blocked_by.lower()
                ].id

        child_ids = [by_title[s.title.lower()].id for s in subtasks]
        db.add(
            TicketEvent(
                ticket_id=parent.id,
                event_type=EventType.COMMENT.value,
                from_state=parent.state,
                to_state=parent.state,
                actor_type=ActorType.EXECUTOR.value,
                actor_id=actor_id,
                reason=f"Split into {len(child_ids)} sub-tickets",
                payload_json=json.dumps({"split_children": child_ids}),
            )
        )
        db.commit()

    logger.info("Split ticket %s into %d children", parent_ticket_id, len(child_ids))
    return child_ids
