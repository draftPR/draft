"""Tests for chat/meeting-notes planning: draft extraction and plan apply."""

import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.exceptions import ResourceNotFoundError
from app.models.board import Board
from app.models.goal import Goal
from app.models.ticket import Ticket
from app.schemas.planner import PlanGoalDraft
from app.services.goal_service import GoalService
from app.services.llm_service import LLMResponse
from app.services.ticket_generation_service import TicketGenerationService


def _service(db, llm_content: str) -> TicketGenerationService:
    service = TicketGenerationService(db)
    service.config.model = "gpt-4o-mini"  # API path, no CLI subprocess
    llm = MagicMock()
    llm.call_completion.return_value = LLMResponse(content=llm_content, model="test")
    llm.safe_parse_json = service.llm.safe_parse_json
    service.llm = llm
    service._get_llm_for_api_fallback = lambda: llm
    return service


async def test_extracts_and_normalizes_plan(db, tmp_path):
    payload = {
        "reply": "Found 2 goals.",
        "goals": [
            {
                "title": "Add CSV export",
                "description": "Users export boards.",
                "existing_goal_id": "made-up-id",  # unknown -> dropped
                "tickets": [
                    {"title": "Export endpoint", "priority_bucket": "p1"},
                    {"title": "Export button", "priority_bucket": "urgent"},
                    {"title": "   "},  # junk -> dropped
                ],
            },
            {"title": "Speed up board", "existing_goal_id": "g1", "tickets": []},
            {"description": "no title"},  # junk -> dropped
        ],
    }
    service = _service(db, json.dumps(payload))

    result = service.plan_from_chat(
        tmp_path,
        [("user", "Meeting notes: Dana wants CSV export ASAP.")],
        [],
        [("g1", "Board performance")],
    )

    assert result["reply"] == "Found 2 goals."
    first, second = result["goals"]
    assert first["existing_goal_id"] is None
    assert [t["title"] for t in first["tickets"]] == [
        "Export endpoint",
        "Export button",
    ]
    assert [t["priority_bucket"] for t in first["tickets"]] == ["P1", "P2"]
    assert second["existing_goal_id"] == "g1"
    prompt = service.llm.call_completion.call_args.kwargs["messages"][0]["content"]
    assert "Dana wants CSV export" in prompt
    assert "- g1: Board performance" in prompt


async def test_reply_only_keeps_current_plan(db, tmp_path):
    service = _service(db, json.dumps({"reply": "Which service owns billing?"}))
    current = [{"title": "Billing", "description": "", "tickets": []}]

    result = service.plan_from_chat(tmp_path, [("user", "hmm")], current, [])

    assert result["reply"] == "Which service owns billing?"
    assert [g["title"] for g in result["goals"]] == ["Billing"]


async def test_unparseable_plan_raises(db, tmp_path):
    service = _service(db, "not json")
    with pytest.raises(ValueError, match="Could not parse plan"):
        service.plan_from_chat(tmp_path, [("user", "x")], [], [])


async def test_create_from_plan(db):
    board = Board(id="b1", name="B", repo_root="/tmp")
    other = Board(id="b2", name="Other", repo_root="/tmp")
    existing = Goal(id="g-existing", title="Perf", board_id="b1")
    foreign = Goal(id="g-foreign", title="Other", board_id="b2")
    db.add_all([board, other, existing, foreign])
    await db.flush()

    drafts = [
        PlanGoalDraft.model_validate(
            {
                "title": "CSV export",
                "tickets": [
                    {"title": "Endpoint", "priority_bucket": "P0"},
                    {"title": "Button", "blocked_by": "endpoint"},
                    {"title": "Docs", "blocked_by": "Later ticket"},
                ],
            }
        ),
        PlanGoalDraft(
            title="ignored",
            existing_goal_id="g-existing",
            tickets=[{"title": "Cache board query"}],
        ),
    ]
    goal_ids, goals_created, tickets_created = await GoalService(db).create_from_plan(
        "b1", drafts
    )

    assert (goals_created, tickets_created) == (1, 4)
    assert goal_ids[1] == "g-existing"
    tickets = {t.title: t for t in (await db.execute(select(Ticket))).scalars().all()}
    assert all(t.state == "proposed" for t in tickets.values())
    assert tickets["Endpoint"].priority == 90
    assert tickets["Button"].blocked_by_ticket_id == tickets["Endpoint"].id
    assert tickets["Docs"].blocked_by_ticket_id is None
    assert tickets["Cache board query"].goal_id == "g-existing"
    new_goal = await db.get(Goal, goal_ids[0])
    assert (new_goal.title, new_goal.board_id) == ("CSV export", "b1")

    with pytest.raises(ResourceNotFoundError):
        await GoalService(db).create_from_plan(
            "b1", [PlanGoalDraft(title="x", existing_goal_id="g-foreign")]
        )
