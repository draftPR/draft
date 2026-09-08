"""Tests for the interactive goal suggestion flow."""

import json
from unittest.mock import MagicMock

import pytest

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


async def test_returns_questions_when_ambiguous(db, tmp_path):
    payload = {
        "questions": [
            {"question": "Which layer?", "options": ["API", "Worker", "UI", "extra"]}
        ]
    }
    service = _service(db, json.dumps(payload))

    result = service.suggest_goal(tmp_path, "add caching", [])

    assert result["questions"][0]["question"] == "Which layer?"
    assert result["questions"][0]["options"] == ["API", "Worker", "UI"]  # capped at 3
    prompt = service.llm.call_completion.call_args.kwargs["messages"][0]["content"]
    assert "add caching" in prompt


async def test_force_suggest_ignores_questions(db, tmp_path):
    payload = {
        "questions": [{"question": "Which?", "options": ["a", "b"]}],
        "suggestion": {"title": "Add caching layer", "description": "Do it."},
    }
    service = _service(db, json.dumps(payload))

    result = service.suggest_goal(
        tmp_path, "add caching", [("Which?", "a")], force_suggest=True
    )

    assert result == {
        "suggestion": {"title": "Add caching layer", "description": "Do it."}
    }
    prompt = service.llm.call_completion.call_args.kwargs["messages"][0]["content"]
    assert "Q: Which?\nA: a" in prompt
    assert "MUST return a suggestion" in prompt


async def test_unparseable_response_raises(db, tmp_path):
    service = _service(db, "not json at all")
    with pytest.raises(ValueError, match="Could not parse"):
        service.suggest_goal(tmp_path, None, [])
