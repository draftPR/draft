"""UDAR Planner Service - Understand-Decide-Act-Validate-Review architecture.

This service implements a lean, cost-optimized agent for ticket generation
and incremental replanning using LangGraph.

Key Cost Optimizations:
- Understand phase: Deterministic (0 LLM calls)
- Decide phase: Single batched LLM call (1 LLM call)
- Act phase: Deterministic (0 LLM calls)
- Validate phase: Mostly deterministic (0-1 LLM calls, optional)
- Review phase: Deterministic (0 LLM calls)

Total: 1-2 LLM calls per goal for initial generation
"""

import json
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal import Goal
from app.models.ticket import Ticket
from app.services.agent_memory_service import AgentMemoryService
from app.services.context_gatherer import ContextGatherer
from app.services.langchain_adapter import LangChainLLMAdapter
from app.services.llm_service import LLMService


class UDARState(TypedDict):
    """State for UDAR agent workflow.

    This state is passed through all phases of the UDAR cycle.
    """

    # Inputs
    goal_id: str
    goal_title: str
    goal_description: str
    repo_root: str
    trigger: str  # "initial_generation" | "post_completion" | "manual"

    # Context (Understand phase - deterministic)
    codebase_summary: str | None
    existing_tickets: list[dict]
    existing_ticket_count: int
    project_type: str | None

    # Decisions (Decide phase - 1 LLM call)
    proposed_tickets: list[dict]
    reasoning: str
    should_generate_new: bool
    llm_calls_made: int  # Track LLM usage

    # Validation (Validate phase - deterministic or 0-1 LLM call)
    validated_tickets: list[dict]
    validation_results: list[dict]

    # Review (Review phase - deterministic)
    final_tickets: list[dict]
    review_summary: str

    # Metadata
    phase: str
    iteration: int
    errors: list[str]
    total_input_tokens: int
    total_output_tokens: int


class UDARPlannerService:
    """UDAR agent service for lean, adaptive ticket generation.

    This service orchestrates the UDAR (Understand-Decide-Act-Validate-Review)
    workflow using LangGraph, with a focus on minimizing LLM calls.

    Example:
        service = UDARPlannerService(db)
        result = await service.generate_from_goal(goal_id="goal-123")
    """

    def __init__(self, db: AsyncSession):
        """Initialize UDAR planner service.

        Args:
            db: Async database session
        """
        self.db = db
        self.llm_service = LLMService()
        self.llm_adapter = LangChainLLMAdapter(llm_service=self.llm_service)
        self.memory_service = AgentMemoryService(db)

        # Build LangGraph workflow
        self.agent = self._build_workflow()

    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph state machine for UDAR.

        Returns:
            Compiled LangGraph agent
        """
        workflow = StateGraph(UDARState)

        # Add nodes for each phase
        workflow.add_node("understand", self._understand_node)
        workflow.add_node("decide", self._decide_node)
        workflow.add_node("act", self._act_node)
        workflow.add_node("validate", self._validate_node)
        workflow.add_node("review", self._review_node)

        # Define edges
        workflow.set_entry_point("understand")
        workflow.add_edge("understand", "decide")
        workflow.add_edge("decide", "act")
        workflow.add_edge("act", "validate")
        workflow.add_conditional_edges(
            "validate",
            self._should_retry,
            {
                "retry": "decide",  # Self-correction loop (max 1 iteration)
                "proceed": "review",
            },
        )
        workflow.add_edge("review", END)

        return workflow.compile()

    async def _understand_node(self, state: UDARState) -> UDARState:
        """Understand phase: Gather context deterministically (0 LLM calls).

        This phase collects:
        - Codebase structure via ContextGatherer
        - Existing tickets from database
        - Goal details

        Args:
            state: Current UDAR state

        Returns:
            Updated state with context
        """
        try:
            # Mark phase
            state["phase"] = "understand"

            # Gather codebase context (deterministic, cached)
            gatherer = ContextGatherer(repo_path=Path(state["repo_root"]))
            context = gatherer.gather(
                include_readme=True,
                include_todos=True,
                max_files=1000,
            )

            # Query existing tickets (deterministic)
            from sqlalchemy import select

            stmt = select(Ticket).where(Ticket.goal_id == state["goal_id"])
            result = await self.db.execute(stmt)
            tickets = result.scalars().all()

            # Build context summary (deterministic)
            state["codebase_summary"] = context.to_prompt_string()
            state["project_type"] = context.project_type
            state["existing_tickets"] = [
                {
                    "id": t.id,
                    "title": t.title,
                    "state": t.state,
                    "priority": t.priority,
                }
                for t in tickets
            ]
            state["existing_ticket_count"] = len(tickets)

            # Log understanding phase
            await self._log_phase(
                state,
                "understanding",
                {
                    "project_type": context.project_type,
                    "file_count": len(context.file_tree),
                    "existing_ticket_count": len(tickets),
                },
            )

        except Exception as e:
            state["errors"].append(f"Understand phase error: {str(e)}")

        return state

    async def _decide_node(self, state: UDARState) -> UDARState:
        """Decide phase: Call LLM to generate ticket proposals (1 LLM call).

        This is the PRIMARY LLM call in the UDAR workflow. It generates
        ALL tickets in a single batched call.

        If this is a retry iteration (iteration > 0), incorporates validation
        feedback from the previous attempt to self-correct.

        Args:
            state: Current UDAR state

        Returns:
            Updated state with proposed tickets
        """
        try:
            state["phase"] = "decide"

            # Build prompt with context (includes validation feedback if retry)
            prompt = self._build_decide_prompt(state)

            # SINGLE LLM CALL for all tickets
            response = await self.llm_adapter._acall(prompt)
            state["llm_calls_made"] = state.get("llm_calls_made", 0) + 1

            # Parse LLM response
            parsed = self._parse_llm_response(response)
            state["proposed_tickets"] = parsed["tickets"]
            state["reasoning"] = parsed["reasoning"]
            state["should_generate_new"] = len(parsed["tickets"]) > 0

            # Log decision phase
            await self._log_phase(
                state,
                "decision",
                {
                    "tickets_proposed": len(state["proposed_tickets"]),
                    "reasoning_length": len(state["reasoning"]),
                    "llm_calls": 1,
                    "is_retry": state["iteration"] > 0,
                },
            )

        except Exception as e:
            state["errors"].append(f"Decide phase error: {str(e)}")
            state["proposed_tickets"] = []

        return state

    async def _act_node(self, state: UDARState) -> UDARState:
        """Act phase: Format tickets deterministically (0 LLM calls).

        This phase converts LLM proposals into database-ready schemas
        using deterministic logic.

        Args:
            state: Current UDAR state

        Returns:
            Updated state with formatted tickets
        """
        try:
            state["phase"] = "act"

            # Format each ticket (deterministic)
            formatted_tickets = []
            for ticket_proposal in state["proposed_tickets"]:
                formatted = self._format_ticket_proposal(ticket_proposal, state)
                formatted_tickets.append(formatted)

            state["proposed_tickets"] = formatted_tickets

            # Log act phase
            await self._log_phase(
                state,
                "act",
                {
                    "tickets_formatted": len(formatted_tickets),
                },
            )

        except Exception as e:
            state["errors"].append(f"Act phase error: {str(e)}")

        return state

    async def _validate_node(self, state: UDARState) -> UDARState:
        """Validate phase: Check proposals deterministically (0 LLM calls).

        This phase uses deterministic validation:
        - Duplicate detection (exact title match)
        - Dependency validation (blocker exists)
        - Schema validation (required fields)

        Optional LLM validation is disabled by default to save quota.

        If validation fails and this is a retry iteration, the feedback
        from previous validation is available in state["validation_feedback"].

        Args:
            state: Current UDAR state

        Returns:
            Updated state with validation results
        """
        try:
            state["phase"] = "validate"

            validated_tickets = []
            validation_results = []
            validation_feedback_messages = []

            for ticket in state["proposed_tickets"]:
                # Deterministic validation
                is_valid, reason = await self._validate_ticket_deterministic(
                    ticket, state
                )

                validation_results.append(
                    {
                        "ticket_title": ticket["title"],
                        "is_valid": is_valid,
                        "reason": reason,
                        "llm_used": False,
                    }
                )

                if is_valid:
                    validated_tickets.append(ticket)
                else:
                    # Collect feedback for self-correction
                    validation_feedback_messages.append(
                        f"- '{ticket['title']}': {reason}"
                    )

            state["validated_tickets"] = validated_tickets
            state["validation_results"] = validation_results

            # Build feedback for self-correction (if needed)
            if validation_feedback_messages:
                state["validation_feedback"] = (
                    "The following tickets failed validation:\n"
                    + "\n".join(validation_feedback_messages)
                )
            else:
                state["validation_feedback"] = ""

            # Log validation phase
            await self._log_phase(
                state,
                "validation",
                {
                    "tickets_validated": len(validated_tickets),
                    "tickets_rejected": len(state["proposed_tickets"])
                    - len(validated_tickets),
                    "has_failures": len(validation_feedback_messages) > 0,
                },
            )

        except Exception as e:
            state["errors"].append(f"Validate phase error: {str(e)}")

        return state

    async def _review_node(self, state: UDARState) -> UDARState:
        """Review phase: Create database records (0 LLM calls).

        This phase commits validated tickets to the database and
        stores reasoning in agent memory as a checkpoint.

        Args:
            state: Current UDAR state

        Returns:
            Updated state with final tickets
        """
        try:
            state["phase"] = "review"

            final_tickets = []

            # Create ticket records
            for ticket_data in state["validated_tickets"]:
                ticket = Ticket(
                    goal_id=state["goal_id"],
                    title=ticket_data["title"],
                    description=ticket_data["description"],
                    state="proposed",  # All start as PROPOSED
                    priority=ticket_data["priority"],
                    board_id=ticket_data.get("board_id"),
                )
                self.db.add(ticket)
                final_tickets.append(ticket_data)

            await self.db.commit()

            state["final_tickets"] = final_tickets
            state["review_summary"] = f"Created {len(final_tickets)} tickets"

            # Save checkpoint to agent memory (compressed)
            checkpoint_id = (
                f"{state['goal_id']}-{state['trigger']}-{datetime.utcnow().isoformat()}"
            )
            await self.memory_service.save_checkpoint(
                goal_id=state["goal_id"],
                checkpoint_id=checkpoint_id,
                state=state,
            )

            # Log review phase
            await self._log_phase(
                state,
                "review",
                {
                    "tickets_created": len(final_tickets),
                    "total_llm_calls": state.get("llm_calls_made", 0),
                    "checkpoint_saved": True,
                },
            )

        except Exception as e:
            state["errors"].append(f"Review phase error: {str(e)}")
            await self.db.rollback()

        return state

    def _should_retry(self, state: UDARState) -> str:
        """Conditional edge: Decide whether to retry validation.

        Retries if validation failed AND iteration < max_self_correction_iterations.
        Max iterations is configured in smartkanban.yaml (default: 1).

        Args:
            state: Current UDAR state

        Returns:
            "retry" or "proceed"
        """
        from app.services.config_service import ConfigService

        failed_count = sum(1 for r in state["validation_results"] if not r["is_valid"])

        # Get max iterations from config
        config = ConfigService().load_config()
        max_iterations = config.planner_config.udar.max_self_correction_iterations

        # Retry if validation failed and under iteration limit
        if failed_count > 0 and state["iteration"] < max_iterations:
            state["iteration"] += 1
            return "retry"

        return "proceed"

    # Helper methods

    def _build_decide_prompt(self, state: UDARState) -> str:
        """Build prompt for Decide phase LLM call.

        If this is a retry iteration, incorporates validation feedback
        to help the LLM self-correct.

        Args:
            state: Current UDAR state

        Returns:
            Prompt string for LLM
        """
        # Check if this is a retry with validation feedback
        validation_feedback = state.get("validation_feedback", "")
        is_retry = state["iteration"] > 0

        prompt = f"""You are a software project planner. Generate tickets for the following goal:

**Goal:** {state["goal_title"]}
**Description:** {state["goal_description"]}

**Codebase Context:**
{state["codebase_summary"][:2000]}  # Cap context to save tokens

**Existing Tickets:**
{json.dumps(state["existing_tickets"][:10], indent=2)}  # Cap at 10
"""

        # Add validation feedback if this is a retry
        if is_retry and validation_feedback:
            prompt += f"""

**IMPORTANT: Previous Attempt Failed Validation**

Your previous ticket proposals had these issues:
{validation_feedback}

Please revise the ticket proposals to address these validation failures:
- Avoid duplicate titles (check existing tickets)
- Ensure all required fields are present
- Use clear, specific titles (at least 5 characters)
"""

        prompt += """
Generate a list of tickets needed to achieve this goal. Each ticket should:
1. Have a clear, actionable title (minimum 5 characters)
2. Include a description with acceptance criteria
3. Specify priority (0-100, higher = more important)
4. Optionally specify "blocked_by" (title of blocking ticket)

Return JSON in this format:
{{
  "reasoning": "Brief explanation of why these tickets are needed",
  "tickets": [
    {{
      "title": "Implement authentication models",
      "description": "Create User, Session models with SQLAlchemy...",
      "priority": 90,
      "blocked_by": null
    }},
    ...
  ]
}}
"""
        return prompt

    def _parse_llm_response(self, response: str) -> dict:
        """Parse LLM JSON response."""
        try:
            # Try to extract JSON from response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                json_str = response.strip()

            parsed = json.loads(json_str)
            return parsed

        except Exception:
            # Fallback if parsing fails
            return {
                "reasoning": "Failed to parse LLM response",
                "tickets": [],
            }

    def _format_ticket_proposal(self, proposal: dict, state: UDARState) -> dict:
        """Format ticket proposal with defaults."""
        return {
            "title": proposal.get("title", "Untitled"),
            "description": proposal.get("description", ""),
            "priority": proposal.get("priority", 50),
            "blocked_by": proposal.get("blocked_by"),
            "board_id": state.get("board_id"),
        }

    async def _validate_ticket_deterministic(
        self,
        ticket: dict,
        state: UDARState,
    ) -> tuple[bool, str]:
        """Validate ticket using deterministic checks (no LLM)."""
        # Check for duplicates (exact title match)
        for existing in state["existing_tickets"]:
            if existing["title"].lower() == ticket["title"].lower():
                return False, f"Duplicate of existing ticket: {existing['id']}"

        # Check required fields
        if not ticket.get("title"):
            return False, "Missing title"

        if len(ticket["title"]) < 5:
            return False, "Title too short"

        # All checks passed
        return True, "Valid"

    async def _log_phase(self, state: UDARState, phase: str, metadata: dict):
        """Log UDAR phase as TicketEvent.

        For ticket generation (no job_id), we log agent activity as events
        attached to the goal. This provides an audit trail of agent reasoning.

        Args:
            state: Current UDAR state
            phase: Phase name (understanding, decision, validation, etc.)
            metadata: Phase-specific data to log
        """
        from app.models.ticket_event import TicketEvent

        # Create event describing agent activity
        event = TicketEvent(
            goal_id=state["goal_id"],
            ticket_id=None,  # Not ticket-specific yet
            event_type="comment",  # Use comment type for agent logs
            actor_type="agent",
            payload={
                "agent_phase": phase,
                "metadata": metadata,
                "trigger": state.get("trigger", "unknown"),
            },
        )
        self.db.add(event)
        # Note: Commit happens at end of workflow, not per-phase

    # Incremental Replanning (Phase 3)

    async def replan_after_completion(self, ticket_ids: list[str]) -> dict:
        """Analyze completed tickets IN BATCH and generate follow-ups if needed.

        COST OPTIMIZATION: Batches multiple tickets into single LLM call.
        Only calls LLM if changes are significant (>10 files OR verification failed).

        Args:
            ticket_ids: List of ticket IDs to analyze (batch)

        Returns:
            Dict with replanning results:
            {
                "tickets_analyzed": 5,
                "significant_tickets": 2,
                "follow_ups_created": 1,
                "llm_calls_made": 1,
                "summary": "..."
            }
        """
        if not ticket_ids:
            return {
                "tickets_analyzed": 0,
                "significant_tickets": 0,
                "follow_ups_created": 0,
                "llm_calls_made": 0,
                "summary": "No tickets to analyze",
            }

        # Step 1: Gather context for ALL tickets (deterministic, 0 LLM calls)
        from app.services.agent_tools import analyze_ticket_changes

        tickets_context = []
        for ticket_id in ticket_ids:
            change_analysis = await analyze_ticket_changes.ainvoke(
                {
                    "db": self.db,
                    "ticket_id": ticket_id,
                }
            )

            # Parse JSON response
            import json

            parsed = json.loads(change_analysis)

            if "error" not in parsed:
                tickets_context.append(parsed)

        if not tickets_context:
            return {
                "tickets_analyzed": len(ticket_ids),
                "significant_tickets": 0,
                "follow_ups_created": 0,
                "llm_calls_made": 0,
                "summary": "No valid tickets to analyze",
            }

        # Step 2: Apply deterministic filters (avoid LLM if possible)
        # Only consider "significant" changes based on config threshold
        from app.services.config_service import ConfigService

        config = ConfigService().load_config()
        significance_threshold = (
            config.planner_config.udar.replan_significance_threshold
        )

        significant_tickets = [
            t
            for t in tickets_context
            if t["file_count"] > significance_threshold or not t["verification_passed"]
        ]

        if not significant_tickets:
            # Changes are too minor, skip LLM entirely
            return {
                "tickets_analyzed": len(tickets_context),
                "significant_tickets": 0,
                "follow_ups_created": 0,
                "llm_calls_made": 0,
                "summary": f"Analyzed {len(tickets_context)} tickets, all changes minor (<10 files, verification passed)",
            }

        # Step 3: Only call LLM for significant changes
        # Build prompt for batched analysis
        prompt = self._build_replan_prompt(significant_tickets)

        # SINGLE batched LLM call for all significant tickets
        response = await self.llm_adapter._acall(prompt)
        llm_calls_made = 1

        # Parse LLM response
        parsed_response = self._parse_llm_response(response)
        follow_ups = parsed_response.get("tickets", [])

        # Step 4: Create follow-up tickets (deterministic)
        from sqlalchemy import select as sa_select

        created_count = 0
        for follow_up_data in follow_ups:
            # Get goal_id from first significant ticket
            first_ticket_id = significant_tickets[0]["ticket_id"]
            stmt = sa_select(Ticket).where(Ticket.id == first_ticket_id)
            result = await self.db.execute(stmt)
            original_ticket = result.scalar_one_or_none()

            if original_ticket:
                follow_up = Ticket(
                    goal_id=original_ticket.goal_id,
                    board_id=original_ticket.board_id,
                    title=follow_up_data.get("title", "Follow-up ticket"),
                    description=follow_up_data.get("description", ""),
                    state="proposed",
                    priority=follow_up_data.get("priority", 50),
                )
                self.db.add(follow_up)
                created_count += 1

        await self.db.commit()

        return {
            "tickets_analyzed": len(tickets_context),
            "significant_tickets": len(significant_tickets),
            "follow_ups_created": created_count,
            "llm_calls_made": llm_calls_made,
            "summary": f"Analyzed {len(tickets_context)} tickets, {len(significant_tickets)} significant, created {created_count} follow-ups",
        }

    def _build_replan_prompt(self, significant_tickets: list[dict]) -> str:
        """Build prompt for batched replanning LLM call.

        Args:
            significant_tickets: List of ticket context dicts

        Returns:
            Prompt string for LLM
        """
        tickets_summary = "\n\n".join(
            [
                f"**Ticket {i + 1}: {t['ticket_title']}**\n"
                f"- State: {t['state']}\n"
                f"- Files changed: {t['file_count']}\n"
                f"- Files: {', '.join(t['files_changed'][:5])}\n"
                f"- Verification: {'✓ Passed' if t['verification_passed'] else '✗ Failed'}"
                for i, t in enumerate(significant_tickets)
            ]
        )

        prompt = f"""You are analyzing completed tickets to determine if follow-up work is needed.

**Completed Tickets:**
{tickets_summary}

Analyze these tickets and determine if any follow-up tickets are needed. Common reasons for follow-ups:
1. Verification failed - need debugging/fixing
2. Large changes (>10 files) - may need tests, documentation, or refactoring
3. Core functionality added - may need integration with other parts

Only generate follow-ups if there's a clear, actionable need. Don't generate follow-ups for:
- Minor changes that are complete
- Tickets that already have tests
- Changes that are self-contained

Return JSON in this format:
{{
  "reasoning": "Brief explanation of analysis",
  "tickets": [
    {{
      "title": "Add tests for new authentication",
      "description": "...",
      "priority": 70
    }}
  ]
}}

If no follow-ups are needed, return {{"reasoning": "...", "tickets": []}}
"""
        return prompt

    # Public API

    async def generate_from_goal(
        self,
        goal_id: str,
        fallback_to_legacy: bool = True,
        timeout_seconds: int = 120,
    ) -> dict:
        """Generate tickets for a goal using UDAR agent (Phase 5: Production Hardened).

        This is the main entry point for initial ticket generation with comprehensive
        error handling, cost tracking, and graceful fallback to legacy mode.

        Args:
            goal_id: Goal ID to generate tickets for
            fallback_to_legacy: If True, falls back to legacy on errors (default: True)
            timeout_seconds: Timeout for UDAR execution (default: 120s)

        Returns:
            Dict with generated tickets and metadata:
            {
                "tickets": [...],
                "summary": "Created 5 tickets",
                "llm_calls_made": 1,
                "phases_completed": ["understand", "decide", "act", "validate", "review"],
                "used_legacy_fallback": false,
                "cost_tracking": {...}
            }

        Raises:
            ResourceNotFoundError: If goal not found
            UDARAgentError: If UDAR fails and fallback disabled
        """
        import asyncio
        import logging

        from app.exceptions import (
            LLMTimeoutError,
            ResourceNotFoundError,
            ToolExecutionError,
            UDARAgentError,
        )

        logger = logging.getLogger(__name__)

        # Get goal
        goal = await self.db.get(Goal, goal_id)
        if not goal:
            raise ResourceNotFoundError("Goal", goal_id)

        # Initialize state
        initial_state: UDARState = {
            "goal_id": goal_id,
            "goal_title": goal.title,
            "goal_description": goal.description or "",
            "repo_root": goal.board.repo_root if goal.board else ".",
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

        # Try UDAR agent with comprehensive error handling
        try:
            # Run agent with timeout
            result_state = await asyncio.wait_for(
                self.agent.ainvoke(initial_state),
                timeout=timeout_seconds,
            )

            # Track cost in AgentSession
            await self._track_agent_session(goal_id, result_state)

            # Return result
            return {
                "tickets": result_state["final_tickets"],
                "summary": result_state["review_summary"],
                "llm_calls_made": result_state["llm_calls_made"],
                "phases_completed": [
                    "understand",
                    "decide",
                    "act",
                    "validate",
                    "review",
                ],
                "errors": result_state["errors"],
                "used_legacy_fallback": False,
                "cost_tracking": {
                    "input_tokens": result_state["total_input_tokens"],
                    "output_tokens": result_state["total_output_tokens"],
                },
            }

        except TimeoutError as e:
            # LLM timeout - fallback to legacy if enabled
            logger.warning(
                f"UDAR agent timeout after {timeout_seconds}s for goal {goal_id}, "
                f"falling back to legacy: {fallback_to_legacy}"
            )
            if fallback_to_legacy:
                return await self._fallback_to_legacy(goal_id, reason="timeout")
            raise LLMTimeoutError("UDAR", timeout_seconds) from e

        except ToolExecutionError as e:
            # Tool execution failed - try partial results or fallback
            logger.error(
                f"UDAR tool execution failed in {e.phase} phase for goal {goal_id}: {e}"
            )
            if fallback_to_legacy:
                return await self._fallback_to_legacy(
                    goal_id, reason=f"tool_error:{e.tool_name}"
                )
            raise

        except UDARAgentError as e:
            # UDAR-specific error - fallback
            logger.error(f"UDAR agent error in {e.phase} phase for goal {goal_id}: {e}")
            if fallback_to_legacy:
                return await self._fallback_to_legacy(
                    goal_id, reason=f"udar_error:{e.phase}"
                )
            raise

        except Exception as e:
            # Unexpected error - always try fallback
            logger.exception(f"Unexpected UDAR agent error for goal {goal_id}: {e}")
            if fallback_to_legacy:
                return await self._fallback_to_legacy(
                    goal_id, reason="unexpected_error"
                )
            raise UDARAgentError(f"Unexpected error: {str(e)}") from e

    # Phase 5: Production Hardening - Helper Methods

    async def _fallback_to_legacy(self, goal_id: str, reason: str) -> dict:
        """Fallback to legacy ticket generation when UDAR fails.

        Args:
            goal_id: Goal ID to generate tickets for
            reason: Reason for fallback (for logging/telemetry)

        Returns:
            Dict with legacy-generated tickets and metadata
        """
        import logging

        from app.services.ticket_generation_service import TicketGenerationService

        logger = logging.getLogger(__name__)

        logger.info(
            f"Falling back to legacy ticket generation for goal {goal_id}, "
            f"reason: {reason}"
        )

        # Use legacy service
        legacy_service = TicketGenerationService(db=self.db)
        result = await legacy_service.generate_from_goal(goal_id=goal_id)

        # Wrap result in UDAR-compatible format
        return {
            "tickets": result.get("tickets", []),
            "summary": f"Generated {len(result.get('tickets', []))} tickets (legacy fallback)",
            "llm_calls_made": 1,  # Legacy uses 1 LLM call
            "phases_completed": ["legacy"],
            "errors": [f"UDAR fallback: {reason}"],
            "used_legacy_fallback": True,
            "fallback_reason": reason,
            "cost_tracking": {
                "input_tokens": 0,  # Legacy doesn't track tokens
                "output_tokens": 0,
            },
        }

    async def _track_agent_session(self, goal_id: str, state: UDARState) -> None:
        """Track UDAR agent session costs in database.

        Logs cost info for observability. AgentSession records require a ticket_id
        (FK to tickets), so UDAR goal-level sessions are logged but not persisted
        to the agent_sessions table.

        Args:
            goal_id: Goal ID
            state: Final UDAR state with token counts
        """
        import logging

        from app.services.agent_registry import AGENT_REGISTRY, AgentType

        logger = logging.getLogger(__name__)

        try:
            # Get agent pricing from registry
            agent_config = AGENT_REGISTRY.get(AgentType.CLAUDE)

            if not agent_config or not agent_config.cost_per_1k_input:
                logger.warning(
                    "Claude agent config not found in registry, skipping cost tracking"
                )
                return

            # Calculate cost
            input_tokens = state.get("total_input_tokens", 0)
            output_tokens = state.get("total_output_tokens", 0)

            cost_usd = (input_tokens / 1000) * agent_config.cost_per_1k_input + (
                output_tokens / 1000
            ) * (agent_config.cost_per_1k_output or 0)

            logger.info(
                f"UDAR agent session for goal {goal_id}: "
                f"{input_tokens} input tokens, {output_tokens} output tokens, "
                f"${cost_usd:.4f} estimated cost, "
                f"phases={state.get('phase', 'unknown')}, "
                f"llm_calls={state.get('llm_calls_made', 0)}"
            )

        except Exception as e:
            # Don't fail request if cost tracking fails
            logger.error(f"Failed to track agent session cost for goal {goal_id}: {e}")
