"""Tests for UDAR agent (Phase 1: Foundation).

Tests basic functionality of tools and LangGraph workflow compilation.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from app.services.agent_tools import analyze_codebase, search_tickets, get_goal_context
from app.services.langchain_adapter import LangChainLLMAdapter
from app.services.udar_planner_service import UDARPlannerService
from app.models.goal import Goal
from app.models.ticket import Ticket


@pytest.mark.asyncio
async def test_analyze_codebase_tool():
    """Test analyze_codebase tool returns valid JSON."""
    # Use current repo for testing
    repo_path = str(Path(__file__).parent.parent.parent)

    result = await analyze_codebase.ainvoke({"repo_root": repo_path})

    # Should return valid JSON
    import json
    parsed = json.loads(result)

    assert "project_type" in parsed
    assert "file_count" in parsed
    assert parsed["file_count"] > 0


@pytest.mark.asyncio
async def test_search_tickets_tool(db):
    """Test search_tickets tool queries database correctly."""
    # Create test goal and tickets
    goal = Goal(
        id="test-goal-1",
        title="Test Goal",
        description="Test",
    )
    db.add(goal)

    ticket1 = Ticket(
        id="test-ticket-1",
        goal_id=goal.id,
        title="Implement authentication",
        description="Add OAuth2",
        state="planned",
        priority=90,
    )
    ticket2 = Ticket(
        id="test-ticket-2",
        goal_id=goal.id,
        title="Add tests",
        description="Test coverage",
        state="done",
        priority=50,
    )
    db.add(ticket1)
    db.add(ticket2)
    await db.commit()

    # Test search
    result = await search_tickets.ainvoke({
        "db": db,
        "goal_id": goal.id,
        "query": "auth",
    })

    # Should return valid JSON with matching tickets
    import json
    parsed = json.loads(result)

    assert parsed["total"] == 1
    assert parsed["tickets"][0]["title"] == "Implement authentication"


@pytest.mark.asyncio
async def test_get_goal_context_tool(db):
    """Test get_goal_context tool retrieves goal details."""
    # Create test goal
    goal = Goal(
        id="test-goal-2",
        title="Add feature X",
        description="Detailed description",
    )
    db.add(goal)
    await db.commit()

    # Test retrieval
    result = await get_goal_context.ainvoke({
        "db": db,
        "goal_id": goal.id,
    })

    # Should return valid JSON with goal details
    import json
    parsed = json.loads(result)

    assert parsed["id"] == goal.id
    assert parsed["title"] == "Add feature X"
    assert "ticket_counts" in parsed


def test_langchain_adapter_properties():
    """Test LangChainLLMAdapter class exists and can be imported."""
    # Just test that the adapter class exists
    # Full integration testing requires actual LLMService instance
    assert LangChainLLMAdapter is not None
    assert hasattr(LangChainLLMAdapter, "_llm_type")


@pytest.mark.asyncio
async def test_udar_workflow_compiles():
    """Test UDAR LangGraph workflow compiles without errors."""
    from unittest.mock import MagicMock

    # Mock database
    mock_db = MagicMock()

    # Create service (this will compile the workflow)
    service = UDARPlannerService(db=mock_db)

    # Verify workflow compiled
    assert service.agent is not None

    # Verify all nodes exist in graph
    # Note: This is a basic test - full workflow testing requires mocking LLM


@pytest.mark.asyncio
async def test_udar_state_initialization():
    """Test UDAR state can be initialized with correct types."""
    from app.services.udar_planner_service import UDARState

    # Create state
    state: UDARState = {
        "goal_id": "test-goal",
        "goal_title": "Test Goal",
        "goal_description": "Test description",
        "repo_root": "/path/to/repo",
        "trigger": "initial_generation",
        "codebase_summary": None,
        "existing_tickets": [],
        "existing_ticket_count": 0,
        "project_type": None,
        "proposed_tickets": [],
        "reasoning": "",
        "should_generate_new": False,
        "llm_calls_made": 0,
        "validated_tickets": [],
        "validation_results": [],
        "final_tickets": [],
        "review_summary": "",
        "phase": "init",
        "iteration": 0,
        "errors": [],
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }

    # Verify required keys exist
    assert "goal_id" in state
    assert "llm_calls_made" in state
    assert state["llm_calls_made"] == 0


@pytest.mark.asyncio
async def test_analyze_ticket_changes_tool(db):
    """Test analyze_ticket_changes tool parses diffs correctly."""
    from app.services.agent_tools import analyze_ticket_changes
    from app.models.revision import Revision
    import json

    # Create test ticket with revision
    goal = Goal(
        id="test-goal-3",
        title="Test Goal",
        description="Test",
    )
    db.add(goal)

    ticket = Ticket(
        id="test-ticket-3",
        goal_id=goal.id,
        title="Add authentication",
        description="Implement OAuth2",
        state="done",
        priority=90,
    )
    db.add(ticket)

    # Create revision with diff content
    revision = Revision(
        ticket_id=ticket.id,
        number=1,
        status="approved",
        diff_stat_content="""backend/app/auth.py | 50 ++++++++++++++++++++++
backend/app/models.py | 20 ++++++----
backend/tests/test_auth.py | 100 ++++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 170 insertions(+), 5 deletions(-)""",
    )
    db.add(revision)
    await db.commit()

    # Test tool
    result = await analyze_ticket_changes.ainvoke({
        "db": db,
        "ticket_id": ticket.id,
    })

    # Should return valid JSON with parsed data
    parsed = json.loads(result)

    assert parsed["ticket_id"] == ticket.id
    assert parsed["file_count"] == 3
    assert "backend/app/auth.py" in parsed["files_changed"]
    assert parsed["verification_passed"] is True


@pytest.mark.asyncio
async def test_udar_config_loads():
    """Test UDAR config loads from YAML correctly."""
    from app.services.config_service import ConfigService

    config = ConfigService().load_config()

    assert hasattr(config.planner_config, "udar")
    assert hasattr(config.planner_config.udar, "enabled")
    assert hasattr(config.planner_config.udar, "replan_batch_size")
    assert config.planner_config.udar.replan_batch_size == 5  # Default value
    assert config.planner_config.udar.max_self_correction_iterations == 1  # Default


@pytest.mark.asyncio
async def test_agent_memory_service(db):
    """Test agent memory service saves and loads checkpoints."""
    from app.services.agent_memory_service import AgentMemoryService

    memory_service = AgentMemoryService(db)

    # Create test goal
    goal = Goal(
        id="test-goal-memory",
        title="Test Goal",
        description="Test memory",
    )
    db.add(goal)
    await db.commit()

    # Save checkpoint
    test_state = {
        "goal_id": goal.id,
        "phase": "review",
        "iteration": 0,
        "proposed_tickets": [{"title": "Test Ticket"}],
        "validated_tickets": [{"title": "Test Ticket"}],
        "reasoning": "Test reasoning for memory checkpoint",
        "llm_calls_made": 1,
        "trigger": "initial_generation",
    }

    await memory_service.save_checkpoint(
        goal_id=goal.id,
        checkpoint_id="test-checkpoint-1",
        state=test_state,
    )

    # Load checkpoint
    loaded = await memory_service.load_checkpoint(goal.id)

    assert loaded is not None
    assert loaded["phase"] == "review"
    assert loaded["llm_calls_made"] == 1
    assert loaded["tickets_proposed"] == 1


@pytest.mark.asyncio
async def test_agent_memory_cleanup(db):
    """Test agent memory cleanup deletes old checkpoints."""
    from app.services.agent_memory_service import AgentMemoryService
    from datetime import timedelta

    memory_service = AgentMemoryService(db)

    # Create test goal
    goal = Goal(
        id="test-goal-cleanup",
        title="Test Goal",
        description="Test cleanup",
    )
    db.add(goal)
    await db.commit()

    # Save checkpoint
    test_state = {
        "goal_id": goal.id,
        "phase": "review",
        "iteration": 0,
        "proposed_tickets": [],
        "validated_tickets": [],
        "reasoning": "Test",
        "llm_calls_made": 0,
        "trigger": "initial_generation",
    }

    await memory_service.save_checkpoint(
        goal_id=goal.id,
        checkpoint_id="test-checkpoint-old",
        state=test_state,
    )

    # Cleanup old checkpoints (0 days = everything)
    deleted_count = await memory_service.cleanup_old_checkpoints(days=0)

    assert deleted_count >= 1


@pytest.mark.asyncio
async def test_self_correction_conditional_edge():
    """Test self-correction conditional edge logic."""
    from app.services.udar_planner_service import UDARState, UDARPlannerService
    from unittest.mock import MagicMock

    # Mock database
    mock_db = MagicMock()
    service = UDARPlannerService(db=mock_db)

    # Test case 1: No failures, should proceed
    state_no_failures: UDARState = {
        "goal_id": "test",
        "goal_title": "Test",
        "goal_description": "Test",
        "repo_root": ".",
        "trigger": "initial_generation",
        "codebase_summary": None,
        "existing_tickets": [],
        "existing_ticket_count": 0,
        "project_type": None,
        "proposed_tickets": [],
        "reasoning": "",
        "should_generate_new": False,
        "llm_calls_made": 0,
        "validated_tickets": [],
        "validation_results": [
            {"ticket_title": "Test", "is_valid": True, "reason": "Valid"}
        ],
        "final_tickets": [],
        "review_summary": "",
        "phase": "validate",
        "iteration": 0,
        "errors": [],
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }

    result = service._should_retry(state_no_failures)
    assert result == "proceed"  # No failures, should proceed

    # Test case 2: Failures but max iterations reached
    state_max_iterations: UDARState = {
        **state_no_failures,
        "validation_results": [
            {"ticket_title": "Test", "is_valid": False, "reason": "Duplicate"}
        ],
        "iteration": 1,  # Already at max (default is 1)
    }

    result = service._should_retry(state_max_iterations)
    assert result == "proceed"  # Max iterations reached, should proceed

    # Test case 3: Failures and under iteration limit
    state_can_retry: UDARState = {
        **state_no_failures,
        "validation_results": [
            {"ticket_title": "Test", "is_valid": False, "reason": "Duplicate"}
        ],
        "iteration": 0,  # Under max
    }

    result = service._should_retry(state_can_retry)
    assert result == "retry"  # Can retry
    assert state_can_retry["iteration"] == 1  # Iteration incremented


# Phase 1 verification checklist:
# [x] Tools can be called independently
# [x] LangGraph state graph compiles
# [ ] No disruption to existing ticket generation (requires integration test)
# [x] Unit tests for tools pass

# Phase 3 verification checklist:
# [x] analyze_ticket_changes tool works
# [x] UDAR config loads with replanning settings
# [ ] Replanning batches tickets correctly (requires integration test)
# [ ] Only calls LLM for significant changes (requires integration test)


# Phase 5: Production Hardening Tests


@pytest.mark.asyncio
async def test_udar_timeout_fallback(db):
    """Test UDAR falls back to legacy on timeout."""
    from app.services.udar_planner_service import UDARPlannerService
    from app.exceptions import LLMTimeoutError
    from unittest.mock import AsyncMock, patch
    from app.models.goal import Goal
    from app.models.board import Board

    # Create test board and goal
    board = Board(
        id="test-board",
        name="Test Board",
        repo_root=".",
    )
    db.add(board)

    goal = Goal(
        id="test-goal-timeout",
        title="Test Goal",
        description="Test timeout handling",
        board_id=board.id,
    )
    db.add(goal)
    await db.commit()

    # Mock LangGraph agent to timeout
    service = UDARPlannerService(db)

    with patch.object(service.agent, "ainvoke", side_effect=AsyncMock(side_effect=TimeoutError())):
        # With fallback enabled (default), should return legacy result
        result = await service.generate_from_goal(goal.id, fallback_to_legacy=True, timeout_seconds=1)
        assert result["used_legacy_fallback"] is True
        assert result["fallback_reason"] == "timeout"

        # With fallback disabled, should raise exception
        with pytest.raises(LLMTimeoutError):
            await service.generate_from_goal(goal.id, fallback_to_legacy=False, timeout_seconds=1)


@pytest.mark.asyncio
async def test_udar_tool_error_fallback(db):
    """Test UDAR falls back to legacy on tool execution error."""
    from app.services.udar_planner_service import UDARPlannerService
    from app.exceptions import ToolExecutionError
    from unittest.mock import AsyncMock, patch
    from app.models.goal import Goal
    from app.models.board import Board

    # Create test board and goal
    board = Board(
        id="test-board-2",
        name="Test Board",
        repo_root=".",
    )
    db.add(board)

    goal = Goal(
        id="test-goal-tool-error",
        title="Test Goal",
        description="Test tool error handling",
        board_id=board.id,
    )
    db.add(goal)
    await db.commit()

    service = UDARPlannerService(db)

    # Mock tool execution failure
    with patch.object(
        service.agent,
        "ainvoke",
        side_effect=ToolExecutionError("analyze_codebase", "File not found", "understand"),
    ):
        result = await service.generate_from_goal(goal.id, fallback_to_legacy=True)
        assert result["used_legacy_fallback"] is True
        assert "tool_error" in result["fallback_reason"]


@pytest.mark.asyncio
async def test_udar_cost_tracking(db):
    """Test UDAR tracks costs in AgentSession."""
    from app.services.udar_planner_service import UDARPlannerService
    from app.models.agent_session import AgentSession
    from app.models.goal import Goal
    from app.models.board import Board
    from sqlalchemy import select

    # Create test board and goal
    board = Board(
        id="test-board-3",
        name="Test Board",
        repo_root=".",
    )
    db.add(board)

    goal = Goal(
        id="test-goal-cost",
        title="Test Goal",
        description="Test cost tracking",
        board_id=board.id,
    )
    db.add(goal)
    await db.commit()

    service = UDARPlannerService(db)

    # Mock successful state with token counts
    test_state = {
        "goal_id": goal.id,
        "phase": "review",
        "final_tickets": [],
        "review_summary": "Test",
        "llm_calls_made": 1,
        "errors": [],
        "total_input_tokens": 1000,
        "total_output_tokens": 500,
    }

    # Call cost tracking
    await service._track_agent_session(goal.id, test_state)

    # Verify AgentSession created
    result = await db.execute(
        select(AgentSession).where(AgentSession.goal_id == goal.id)
    )
    session = result.scalar_one_or_none()

    assert session is not None
    assert session.total_input_tokens == 1000
    assert session.total_output_tokens == 500
    assert session.estimated_cost_usd > 0


@pytest.mark.asyncio
async def test_phase5_config_loads():
    """Test Phase 5 configuration options load correctly."""
    from app.services.config_service import ConfigService

    config = ConfigService().load_config()

    # Verify Phase 5 settings exist and have defaults
    assert hasattr(config.planner_config.udar, "fallback_to_legacy")
    assert config.planner_config.udar.fallback_to_legacy is True

    assert hasattr(config.planner_config.udar, "timeout_seconds")
    assert config.planner_config.udar.timeout_seconds == 120

    assert hasattr(config.planner_config.udar, "enable_cost_tracking")
    assert config.planner_config.udar.enable_cost_tracking is True

    assert hasattr(config.planner_config.udar, "max_retries_on_error")
    assert config.planner_config.udar.max_retries_on_error == 0


@pytest.mark.asyncio
async def test_udar_graceful_degradation(db):
    """Test UDAR degrades gracefully on unexpected errors."""
    from app.services.udar_planner_service import UDARPlannerService
    from app.exceptions import UDARAgentError
    from unittest.mock import AsyncMock, patch
    from app.models.goal import Goal
    from app.models.board import Board

    # Create test board and goal
    board = Board(
        id="test-board-4",
        name="Test Board",
        repo_root=".",
    )
    db.add(board)

    goal = Goal(
        id="test-goal-degradation",
        title="Test Goal",
        description="Test graceful degradation",
        board_id=board.id,
    )
    db.add(goal)
    await db.commit()

    service = UDARPlannerService(db)

    # Mock unexpected exception
    with patch.object(
        service.agent,
        "ainvoke",
        side_effect=RuntimeError("Unexpected error in LangGraph"),
    ):
        # With fallback enabled, should handle gracefully
        result = await service.generate_from_goal(goal.id, fallback_to_legacy=True)
        assert result["used_legacy_fallback"] is True
        assert result["fallback_reason"] == "unexpected_error"

        # With fallback disabled, should raise UDARAgentError
        with pytest.raises(UDARAgentError):
            await service.generate_from_goal(goal.id, fallback_to_legacy=False)


# Phase 5 verification checklist:
# [x] Timeout handling with fallback to legacy
# [x] Tool execution error handling with fallback
# [x] Cost tracking in AgentSession
# [x] Phase 5 configuration loads correctly
# [x] Graceful degradation on unexpected errors
# [ ] Rate limiting enforced for UDAR endpoints (requires HTTP test)
# [ ] Telemetry/monitoring metrics (requires Prometheus integration)
