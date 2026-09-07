"""Subtasks parsing and Nadir routing (no network, no DB)."""

import io
import json

import pytest

from app.services import routing_service
from app.services.config_service import RoutingConfig
from app.services.split_service import SubtasksError, parse_subtasks

GOOD = {
    "subtasks": [
        {"title": "Add model", "description": "Add column", "complexity": "simple"},
        {
            "title": "Wire API",
            "description": "Expose it",
            "blocked_by": "Add model",
            "complexity": "medium",
        },
    ]
}


def test_parse_subtasks_ok():
    subs = parse_subtasks(json.dumps(GOOD), max_children=6)
    assert [s.title for s in subs] == ["Add model", "Wire API"]
    assert subs[1].blocked_by == "Add model"
    assert subs[0].complexity == "simple"


@pytest.mark.parametrize(
    "raw, msg",
    [
        ("not json", "invalid JSON"),
        ('{"subtasks": [{"title": "only one", "description": "x"}]}', "need 2..6"),
        (
            '{"subtasks": [{"title": "a", "description": "x"}, {"title": "a", "description": "y"}]}',
            "unique",
        ),
        (
            '{"subtasks": [{"title": "a", "description": "x", "blocked_by": "zzz"}, {"title": "b", "description": "y"}]}',
            "unknown title",
        ),
        (
            '{"subtasks": [{"title": "a", "description": "x", "blocked_by": "b"}, {"title": "b", "description": "y", "blocked_by": "a"}]}',
            "cycle",
        ),
        (
            '{"subtasks": [{"title": "a", "description": "x", "complexity": "huge"}, {"title": "b", "description": "y"}]}',
            "complexity",
        ),
    ],
)
def test_parse_subtasks_rejects(raw, msg):
    with pytest.raises(SubtasksError, match=msg):
        parse_subtasks(raw, max_children=6)


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_route_ticket_maps_tier_to_profile(monkeypatch):
    body = {
        "bucket": "medium",
        "confidence": 0.9,
        "request_id": "r1",
        "plan": {"tier": "complex"},
    }
    monkeypatch.setattr(
        routing_service.urllib.request,
        "urlopen",
        lambda req, timeout: _FakeResp(json.dumps(body).encode()),
    )
    cfg = RoutingConfig(enabled=True, by_tier={"complex": "claude-opus"})
    d = routing_service.route_ticket("t", "d", cfg)
    assert d.profile == "claude-opus"
    assert d.tier == "complex" and d.request_id == "r1"


def test_route_ticket_fails_open(monkeypatch):
    def boom(req, timeout):
        raise OSError("down")

    monkeypatch.setattr(routing_service.urllib.request, "urlopen", boom)
    cfg = RoutingConfig(enabled=True, by_tier={"simple": "codex"})
    d = routing_service.route_ticket("t", None, cfg)
    assert d.profile is None and "down" in d.error


def test_route_ticket_disabled_skips_network(monkeypatch):
    monkeypatch.setattr(
        routing_service.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call")),
    )
    assert routing_service.route_ticket("t", "d", RoutingConfig()).profile is None
