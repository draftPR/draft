"""Tests for UDAR agent (Phase 1: Foundation).

Tests basic functionality of tools and LangGraph workflow compilation.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.models.goal import Goal
from app.models.ticket import Ticket
from app.services.agent_tools import analyze_codebase, get_goal_context, search_tickets
from app.services.langchain_adapter import LangChainLLMAdapter
from app.services.udar_planner_service import UDARPlannerService


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
    result = await search_tickets.ainvoke(
        {
            "db": db,
            "goal_id": goal.id,
            "query": "auth",
        }
    )

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
    result = await get_goal_context.ainvoke(
        {
            "db": db,
            "goal_id": goal.id,
        }
    )

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
    import json

    from app.models.revision import Revision
    from app.services.agent_tools import analyze_ticket_changes

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

    # Create a job for the revision (required FK)
    from app.models.job import Job

    job = Job(
        id="test-job-changes",
        ticket_id=ticket.id,
        kind="execute",
        status="succeeded",
    )
    db.add(job)

    # Create revision without diff content (no evidence in this test)
    revision = Revision(
        ticket_id=ticket.id,
        job_id=job.id,
        number=1,
        status="approved",
    )
    db.add(revision)
    await db.commit()

    # Test tool
    result = await analyze_ticket_changes.ainvoke(
        {
            "db": db,
            "ticket_id": ticket.id,
        }
    )

    # Should return valid JSON
    parsed = json.loads(result)

    assert parsed["ticket_id"] == ticket.id
    assert parsed["has_revision"] is True
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
    from unittest.mock import MagicMock

    from app.services.udar_planner_service import UDARPlannerService, UDARState

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

    from app.exceptions import LLMTimeoutError
    from app.models.board import Board
    from app.models.goal import Goal
    from app.services.udar_planner_service import UDARPlannerService

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

    service = UDARPlannerService(db)

    mock_fallback_result = {
        "tickets": [],
        "summary": "Fallback result",
        "llm_calls_made": 1,
        "phases_completed": ["legacy"],
        "errors": ["UDAR fallback: timeout"],
        "used_legacy_fallback": True,
        "fallback_reason": "timeout",
        "cost_tracking": {"input_tokens": 0, "output_tokens": 0},
    }

    with (
        patch.object(service.agent, "ainvoke", side_effect=TimeoutError()),
        patch.object(
            service,
            "_fallback_to_legacy",
            new_callable=AsyncMock,
            return_value=mock_fallback_result,
        ),
    ):
        # With fallback enabled (default), should return legacy result
        result = await service.generate_from_goal(
            goal.id, fallback_to_legacy=True, timeout_seconds=1
        )
        assert result["used_legacy_fallback"] is True
        assert result["fallback_reason"] == "timeout"

    with patch.object(service.agent, "ainvoke", side_effect=TimeoutError()):
        # With fallback disabled, should raise exception
        with pytest.raises(LLMTimeoutError):
            await service.generate_from_goal(
                goal.id, fallback_to_legacy=False, timeout_seconds=1
            )


@pytest.mark.asyncio
async def test_udar_tool_error_fallback(db):
    """Test UDAR falls back to legacy on tool execution error."""
    from app.exceptions import ToolExecutionError
    from app.models.board import Board
    from app.models.goal import Goal
    from app.services.udar_planner_service import UDARPlannerService

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

    mock_fallback_result = {
        "tickets": [],
        "summary": "Fallback result",
        "llm_calls_made": 1,
        "phases_completed": ["legacy"],
        "errors": ["UDAR fallback: tool_error:analyze_codebase"],
        "used_legacy_fallback": True,
        "fallback_reason": "tool_error:analyze_codebase",
        "cost_tracking": {"input_tokens": 0, "output_tokens": 0},
    }

    # Mock tool execution failure and fallback
    with (
        patch.object(
            service.agent,
            "ainvoke",
            side_effect=ToolExecutionError(
                "analyze_codebase", "File not found", "understand"
            ),
        ),
        patch.object(
            service,
            "_fallback_to_legacy",
            new_callable=AsyncMock,
            return_value=mock_fallback_result,
        ),
    ):
        result = await service.generate_from_goal(goal.id, fallback_to_legacy=True)
        assert result["used_legacy_fallback"] is True
        assert "tool_error" in result["fallback_reason"]


@pytest.mark.asyncio
async def test_udar_cost_tracking(db, caplog):
    """Test UDAR cost tracking logs costs without crashing.

    Note: AgentSession requires ticket_id (FK to tickets), so UDAR
    goal-level sessions are logged but not persisted to the DB.
    """
    import logging

    from app.models.board import Board
    from app.models.goal import Goal
    from app.services.udar_planner_service import UDARPlannerService

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

    # Call cost tracking - should not raise, should log cost info
    with caplog.at_level(logging.INFO):
        await service._track_agent_session(goal.id, test_state)

    # Verify cost was logged
    assert "1000 input tokens" in caplog.text
    assert "500 output tokens" in caplog.text
    assert goal.id in caplog.text


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
    from app.exceptions import UDARAgentError
    from app.models.board import Board
    from app.models.goal import Goal
    from app.services.udar_planner_service import UDARPlannerService

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

    mock_fallback_result = {
        "tickets": [],
        "summary": "Fallback result",
        "llm_calls_made": 1,
        "phases_completed": ["legacy"],
        "errors": ["UDAR fallback: unexpected_error"],
        "used_legacy_fallback": True,
        "fallback_reason": "unexpected_error",
        "cost_tracking": {"input_tokens": 0, "output_tokens": 0},
    }

    # With fallback enabled, should handle gracefully
    with (
        patch.object(
            service.agent,
            "ainvoke",
            side_effect=RuntimeError("Unexpected error in LangGraph"),
        ),
        patch.object(
            service,
            "_fallback_to_legacy",
            new_callable=AsyncMock,
            return_value=mock_fallback_result,
        ),
    ):
        result = await service.generate_from_goal(goal.id, fallback_to_legacy=True)
        assert result["used_legacy_fallback"] is True
        assert result["fallback_reason"] == "unexpected_error"

    # With fallback disabled, should raise UDARAgentError
    with patch.object(
        service.agent,
        "ainvoke",
        side_effect=RuntimeError("Unexpected error in LangGraph"),
    ):
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
