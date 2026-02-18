"""Ticket generation service - orchestrates context gathering, agent calls, and validation.

This service is responsible for:
1. Collecting repository context via ContextGatherer
2. Building prompts for ticket generation
3. Calling the agent CLI (cursor-agent/claude) to generate tickets
4. Validating, capping, and sanitizing output
5. De-duplicating against existing tickets
6. Caching analysis results

Ticket generation uses the same agent infrastructure as execution for consistency.
"""

import asyncio
import hashlib
import json
import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_cache import AnalysisCache
from app.models.goal import Goal
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.schemas.planner import (
    AnalyzeCodebaseResponse,
    ContextStats,
    CreatedTicketSchema,
    ExcludedMatch,
    FiletypeCount,
    GeneratedTicket,
    PriorityBucket,
    ReflectionResult,
    SimilarTicketWarning,
    SuggestedPriorityChange,
    bucket_to_priority,
    priority_to_bucket,
)
from app.services.config_service import ConfigService, PlannerConfig
from app.services.context_gatherer import ContextGatherer, RepoContext
from app.services.executor_service import ExecutorService, ExecutorType
from app.services.llm_service import LLMService
from app.state_machine import ActorType, EventType, TicketState

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Cache TTL for analysis results
ANALYSIS_CACHE_TTL_MINUTES = 10

# Max tickets to generate in one call
MAX_TICKETS_PER_GENERATION = 10

# Similarity threshold for dedup (token overlap)
DEDUP_SIMILARITY_THRESHOLD = 0.6


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class GenerationResult:
    """Result of ticket generation."""

    tickets: list[CreatedTicketSchema]
    goal_id: str | None
    from_cache: bool = False


# =============================================================================
# Service
# =============================================================================


class TicketGenerationService:
    """Orchestrates ticket generation from goals or codebase analysis.

    This service coordinates:
    - Context gathering (ContextGatherer)
    - LLM calls (LLMService)
    - Ticket creation and validation
    - Caching and deduplication
    """

    def __init__(
        self,
        db: AsyncSession,
        llm_service: LLMService | None = None,
        config: PlannerConfig | None = None,
    ):
        """Initialize the ticket generation service.

        Args:
            db: Async database session.
            llm_service: LLM service instance. If None, creates one.
            config: Planner configuration. If None, loads from config file.
        """
        self.db = db

        if config is None:
            config_service = ConfigService()
            config = config_service.get_planner_config()
        self.config = config

        if llm_service is None:
            llm_service = LLMService(config)
        self.llm = llm_service

        self.context_gatherer = ContextGatherer()

    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================

    async def generate_from_goal(
        self,
        goal_id: str,
        repo_root: Path | str | None = None,
        include_readme: bool = False,
        validate_tickets: bool = False,
        stream_callback=None,
    ) -> GenerationResult:
        """Generate tickets from a goal using the agent CLI.

        Args:
            goal_id: ID of the goal to generate tickets for.
            repo_root: Optional path to repository for context.
            include_readme: Whether to include README excerpt.
            validate_tickets: Whether to validate tickets against codebase before creating.

        Returns:
            GenerationResult with created tickets.

        Raises:
            ValueError: If goal not found or no agent available.
        """
        # Fetch goal
        result = await self.db.execute(select(Goal).where(Goal.id == goal_id))
        goal = result.scalar_one_or_none()
        if not goal:
            raise ValueError(f"Goal not found: {goal_id}")

        # Determine repo_root from goal's board if not provided
        if not repo_root and goal.board_id:
            from app.models.board import Board
            board_result = await self.db.execute(select(Board).where(Board.id == goal.board_id))
            board = board_result.scalar_one_or_none()
            if board:
                repo_root = board.repo_root

        if not repo_root:
            raise ValueError("No repository path available for ticket generation")

        repo_root = Path(repo_root)

        # Build prompt for agent
        prompt = self._build_agent_ticket_generation_prompt(goal, include_readme)

        # Call agent to generate tickets (run in thread pool to avoid blocking event loop)
        logger.info(f"Calling agent CLI for goal '{goal.title}' (streaming={'yes' if stream_callback else 'no'})")
        agent_response = await asyncio.to_thread(
            self._call_agent_for_tickets,
            prompt,
            repo_root,
            stream_callback,
        )
        logger.info(f"Agent CLI completed. Response length: {len(agent_response)} chars")

        # Parse and validate response
        data = self._parse_agent_json_response(agent_response)
        raw_tickets = data.get("tickets", [])

        logger.info(f"Agent generated {len(raw_tickets)} raw tickets for goal '{goal.title}'")
        if len(raw_tickets) == 0:
            logger.warning(f"Agent returned 0 tickets. Response preview: {agent_response[:500]}")

        # Validate tickets against codebase if enabled
        filtered_count = 0
        if validate_tickets and raw_tickets:
            logger.info(f"Validating {len(raw_tickets)} tickets against codebase")

            try:
                # Gather context for validation
                context = self.context_gatherer.gather(
                    repo_root=repo_root,
                    include_readme_excerpt=include_readme,
                )
                context_summary = context.to_prompt_string()[:3000]  # Limit size for validation

                validated_tickets = []

                for raw in raw_tickets:
                    try:
                        validation = self._validate_ticket_against_codebase(
                            ticket=raw,
                            goal=goal,
                            context_summary=context_summary,
                        )

                        # Store validation result in ticket for later use in event payload
                        raw["_validation"] = validation

                        # Only include appropriate tickets
                        if validation.get("is_valid") and validation.get("validation_result") == "appropriate":
                            validated_tickets.append(raw)
                        else:
                            filtered_count += 1
                            logger.warning(
                                f"Filtered ticket '{raw.get('title')}': "
                                f"result={validation.get('validation_result')}, "
                                f"reason={validation.get('reasoning')}"
                            )
                    except Exception as e:
                        # If validation fails for a ticket, include it anyway (fail open)
                        logger.error(f"Validation failed for ticket '{raw.get('title')}': {e}")
                        validated_tickets.append(raw)

                if filtered_count > 0:
                    logger.warning(f"Filtered {filtered_count}/{len(raw_tickets)} tickets during validation")

                raw_tickets = validated_tickets
            except Exception as e:
                # If entire validation process fails, proceed with all tickets (fail open)
                logger.error(f"Validation process failed, proceeding with all {len(raw_tickets)} tickets: {e}")
                filtered_count = 0
        else:
            if not validate_tickets:
                logger.debug(f"Ticket validation disabled, skipping for {len(raw_tickets)} tickets")

        # Get existing tickets for dedup
        existing_tickets = await self._get_existing_tickets(goal_id)

        # Create tickets in database
        created_tickets: list[CreatedTicketSchema] = []
        # Track title -> ticket_id for resolving blocked_by references
        title_to_ticket_id: dict[str, str] = {}
        # Track tickets that need blocked_by resolved after all are created
        pending_blocked_by: list[tuple[str, str]] = []  # (ticket_id, blocked_by_title)

        for idx, raw in enumerate(raw_tickets[:MAX_TICKETS_PER_GENERATION], 1):
            try:
                # Validate required fields
                title = raw.get("title", "").strip()
                if not title or len(title) > 255:
                    logger.warning(f"Skipping ticket with invalid title (len={len(title)})")
                    continue

                # Dedup check - only block on exact match
                status, _, _, _ = self._check_duplicate(title, existing_tickets)
                if status == "exact":
                    logger.info(f"Skipping exact duplicate ticket: {title[:50]}")
                    continue

                # Parse priority bucket
                bucket_str = raw.get("priority_bucket", "P2")
                try:
                    bucket = PriorityBucket(bucket_str)
                except ValueError:
                    bucket = PriorityBucket.P2  # Default to medium

                priority = bucket_to_priority(bucket)
                rationale = raw.get("priority_rationale", "")

                # Determine initial state: auto-approve if goal has autonomy enabled
                initial_state = TicketState.PROPOSED.value
                auto_approved_ticket = False
                if goal.autonomy_enabled and goal.auto_approve_tickets:
                    initial_state = TicketState.PLANNED.value
                    auto_approved_ticket = True

                # Create ticket
                ticket = Ticket(
                    goal_id=goal_id,
                    board_id=goal.board_id,
                    title=title,
                    description=raw.get("description", ""),
                    state=initial_state,
                    priority=priority,
                )
                self.db.add(ticket)
                await self.db.flush()
                await self.db.refresh(ticket)
                logger.info(f"Created ticket {ticket.id}: {title[:50]}")

                # Track title -> id mapping for blocked_by resolution
                title_to_ticket_id[title.lower()] = ticket.id

                # Check if this ticket has a blocked_by reference
                blocked_by_title = raw.get("blocked_by")
                if blocked_by_title:
                    pending_blocked_by.append((ticket.id, blocked_by_title))

                # Build event payload
                event_payload = {
                    "priority_bucket": bucket.value,
                    "priority_rationale": rationale,
                    "verification": raw.get("verification", []),
                    "notes": raw.get("notes"),
                    "blocked_by_title": blocked_by_title,
                }

                # Add validation result if present
                if "_validation" in raw:
                    validation = raw["_validation"]
                    event_payload["validation"] = {
                        "validated": True,
                        "confidence": validation.get("confidence"),
                        "validation_result": validation.get("validation_result"),
                        "reasoning": validation.get("reasoning"),
                    }

                # Add auto-approval info to event payload
                if auto_approved_ticket:
                    event_payload["auto_approved"] = True

                # Create event
                event = TicketEvent(
                    ticket_id=ticket.id,
                    event_type=EventType.CREATED.value,
                    from_state=None,
                    to_state=initial_state,
                    actor_type=ActorType.PLANNER.value,
                    actor_id="ticket_generation_service",
                    reason=f"Generated from goal: {goal.title}",
                    payload_json=json.dumps(event_payload),
                )
                self.db.add(event)

                # Record autonomy event if auto-approved
                if auto_approved_ticket:
                    autonomy_event = TicketEvent(
                        ticket_id=ticket.id,
                        event_type=EventType.TRANSITIONED.value,
                        from_state=TicketState.PROPOSED.value,
                        to_state=TicketState.PLANNED.value,
                        actor_type=ActorType.SYSTEM.value,
                        actor_id="autonomy_service",
                        reason="Auto-approved ticket (autonomy mode)",
                        payload_json=json.dumps({"autonomy_action": "approve_ticket"}),
                    )
                    self.db.add(autonomy_event)

                created_tickets.append(
                    CreatedTicketSchema(
                        id=ticket.id,
                        title=ticket.title,
                        description=ticket.description or "",
                        priority_bucket=bucket,
                        priority=priority,
                        priority_rationale=rationale,
                        verification=raw.get("verification", []),
                        notes=raw.get("notes"),
                    )
                )

                existing_tickets.append((ticket.id, title))  # Add to dedup list

            except Exception as e:
                logger.error(f"Error creating ticket '{raw.get('title', '')[:50]}': {e}", exc_info=True)
                # Don't re-raise, continue with next ticket
                continue

        # Resolve blocked_by references now that all tickets are created
        for ticket_id, blocked_by_title in pending_blocked_by:
            blocker_id = title_to_ticket_id.get(blocked_by_title.lower())
            if blocker_id:
                # Update the ticket with the blocker ID
                result = await self.db.execute(
                    select(Ticket).where(Ticket.id == ticket_id)
                )
                ticket = result.scalar_one_or_none()
                if ticket:
                    ticket.blocked_by_ticket_id = blocker_id
                    logger.info(f"Ticket '{ticket.title}' blocked by ticket ID {blocker_id}")
                    
                    # Update the CreatedTicketSchema with blocked_by info
                    for created in created_tickets:
                        if created.id == ticket_id:
                            created.blocked_by_ticket_id = blocker_id
                            created.blocked_by_title = blocked_by_title
                            break
            else:
                logger.warning(
                    f"Could not resolve blocked_by reference '{blocked_by_title}' "
                    f"for ticket {ticket_id}"
                )

        await self.db.commit()

        logger.info(
            f"Created {len(created_tickets)} tickets for goal '{goal.title}' "
            f"(generated: {len(data.get('tickets', []))}, filtered: {filtered_count})"
        )

        return GenerationResult(
            tickets=created_tickets,
            goal_id=goal_id,
        )

    async def analyze_codebase(
        self,
        repo_root: Path | str,
        goal_id: str | None = None,
        focus_areas: list[str] | None = None,
        include_readme: bool = False,
        board_id: str | None = None,
    ) -> AnalyzeCodebaseResponse:
        """Analyze a codebase and generate improvement tickets.

        Args:
            repo_root: Path to the repository.
            goal_id: Optional goal to attach tickets to.
            focus_areas: Optional focus hints.
            include_readme: Whether to include README excerpt.
            board_id: Board ID for scoping (required for multi-board setups).

        Returns:
            AnalyzeCodebaseResponse with generated tickets.
        """
        repo_root = Path(repo_root).resolve()

        # Get git HEAD SHA for cache invalidation
        head_sha = self._get_git_head_sha(repo_root)

        # Check cache (includes HEAD SHA so invalidates on new commits)
        cache_key = self._compute_cache_key(repo_root, focus_areas, head_sha)
        cached = await self._get_cached_analysis(cache_key)
        if cached:
            return AnalyzeCodebaseResponse(
                tickets=cached.get("tickets", []),
                goal_id=goal_id,
                analysis_summary=cached.get("analysis_summary", ""),
                cache_hit=True,
                context_stats=cached.get("context_stats"),
                similar_warnings=cached.get("similar_warnings", []),
                repo_head_sha=head_sha,
            )

        # Gather context
        context = self.context_gatherer.gather(
            repo_root=repo_root,
            include_readme_excerpt=include_readme,
        )

        # Build context stats for observability
        # Build excluded_matches (top 10 by count)
        excluded_matches = [
            ExcludedMatch(pattern=pattern, count=count)
            for pattern, count in sorted(
                context.stats.excluded_by_pattern.items(),
                key=lambda x: -x[1],
            )[:10]
        ]

        # Build filetype histogram (top 10 by count)
        filetype_histogram = [
            FiletypeCount(extension=ext, count=count)
            for ext, count in sorted(
                context.stats.extensions_scanned.items(),
                key=lambda x: -x[1],
            )[:10]
        ]

        context_stats = ContextStats(
            files_scanned=context.stats.files_scanned,
            todos_collected=context.stats.todo_lines_found,
            context_truncated=(
                context.stats.files_scanned >= self.context_gatherer.MAX_FILES_SCANNED
                or context.stats.bytes_read >= self.context_gatherer.MAX_BYTES_TOTAL
            ),
            skipped_excluded=context.stats.skipped_excluded,
            skipped_symlinks=context.stats.skipped_symlinks,
            bytes_read=context.stats.bytes_read,
            excluded_matches=excluded_matches,
            filetype_histogram=filetype_histogram,
        )

        # Build prompt for agent
        prompt = self._build_agent_analysis_prompt(focus_areas)

        # Call agent to analyze codebase
        agent_response = self._call_agent_for_tickets(prompt, repo_root)

        # Parse response
        data = self._parse_agent_json_response(agent_response)
        raw_tickets = data.get("tickets", [])
        summary = data.get("summary", "Analysis complete.")

        # Get existing tickets for dedup (across all goals if no goal specified)
        existing_tickets = await self._get_existing_tickets(goal_id)

        # Create tickets with improved dedup (exact=block, similar=warn)
        created_tickets: list[CreatedTicketSchema] = []
        similar_warnings: list[SimilarTicketWarning] = []
        # Track title -> ticket_id for resolving blocked_by references
        title_to_ticket_id: dict[str, str] = {}
        # Track tickets that need blocked_by resolved after all are created
        pending_blocked_by: list[tuple[str, str]] = []  # (ticket_id, blocked_by_title)

        for raw in raw_tickets[:MAX_TICKETS_PER_GENERATION]:
            title = raw.get("title", "").strip()
            if not title or len(title) > 255:
                continue

            # Check for duplicates
            status, existing_id, existing_title, similarity = self._check_duplicate(
                title, existing_tickets
            )

            if status == "exact":
                # Hard block on exact match
                logger.debug(f"Blocking exact duplicate ticket: {title}")
                continue
            elif status == "similar":
                # Warn but don't block on similar
                similar_warnings.append(
                    SimilarTicketWarning(
                        proposed_title=title,
                        similar_to_id=existing_id,
                        similar_to_title=existing_title,
                        similarity_score=similarity,
                    )
                )
                logger.debug(f"Warning: ticket '{title}' similar to '{existing_title}'")
                # Continue creating the ticket (warn, don't block)

            bucket_str = raw.get("priority_bucket", "P2")
            try:
                bucket = PriorityBucket(bucket_str)
            except ValueError:
                bucket = PriorityBucket.P2

            priority = bucket_to_priority(bucket)
            rationale = raw.get("priority_rationale", "")
            blocked_by_title = raw.get("blocked_by")

            # Only create in DB if goal_id provided
            if goal_id:
                ticket = Ticket(
                    goal_id=goal_id,
                    board_id=board_id,  # Scope to board for permission boundary
                    title=title,
                    description=raw.get("description", ""),
                    state=TicketState.PROPOSED.value,
                    priority=priority,
                )
                self.db.add(ticket)
                await self.db.flush()
                await self.db.refresh(ticket)
                
                # Track title -> id mapping for blocked_by resolution
                title_to_ticket_id[title.lower()] = ticket.id
                
                # Check if this ticket has a blocked_by reference
                if blocked_by_title:
                    pending_blocked_by.append((ticket.id, blocked_by_title))

                event = TicketEvent(
                    ticket_id=ticket.id,
                    event_type=EventType.CREATED.value,
                    from_state=None,
                    to_state=TicketState.PROPOSED.value,
                    actor_type=ActorType.PLANNER.value,
                    actor_id="ticket_generation_service",
                    reason="Generated from codebase analysis",
                    payload_json=json.dumps({
                        "priority_bucket": bucket.value,
                        "priority_rationale": rationale,
                        "focus_areas": focus_areas,
                        "repo_head_sha": head_sha,
                        "blocked_by_title": blocked_by_title,
                    }),
                )
                self.db.add(event)

                ticket_id = ticket.id
            else:
                # Preview mode - no DB write
                ticket_id = f"preview-{len(created_tickets)}"
                title_to_ticket_id[title.lower()] = ticket_id

            created_tickets.append(
                CreatedTicketSchema(
                    id=ticket_id,
                    title=title,
                    description=raw.get("description", ""),
                    priority_bucket=bucket,
                    priority=priority,
                    priority_rationale=rationale,
                    verification=raw.get("verification", []),
                    notes=raw.get("notes"),
                )
            )

            # Add to existing for remaining dedup checks
            existing_tickets.append((ticket_id, title))

        # Resolve blocked_by references now that all tickets are created
        if goal_id:
            for ticket_id, blocked_by_title in pending_blocked_by:
                blocker_id = title_to_ticket_id.get(blocked_by_title.lower())
                if blocker_id:
                    # Update the ticket with the blocker ID
                    result = await self.db.execute(
                        select(Ticket).where(Ticket.id == ticket_id)
                    )
                    ticket = result.scalar_one_or_none()
                    if ticket:
                        ticket.blocked_by_ticket_id = blocker_id
                        logger.info(f"Ticket '{ticket.title}' blocked by ticket ID {blocker_id}")
                        
                        # Update the CreatedTicketSchema with blocked_by info
                        for created in created_tickets:
                            if created.id == ticket_id:
                                created.blocked_by_ticket_id = blocker_id
                                created.blocked_by_title = blocked_by_title
                                break
                else:
                    logger.warning(
                        f"Could not resolve blocked_by reference '{blocked_by_title}' "
                        f"for ticket {ticket_id}"
                    )

            await self.db.commit()

        # Cache result (includes stats and warnings)
        await self._cache_analysis(
            cache_key,
            {
                "tickets": [t.model_dump() for t in created_tickets],
                "analysis_summary": summary,
                "context_stats": context_stats.model_dump(),
                "similar_warnings": [w.model_dump() for w in similar_warnings],
            },
        )

        return AnalyzeCodebaseResponse(
            tickets=created_tickets,
            goal_id=goal_id,
            analysis_summary=summary,
            cache_hit=False,
            context_stats=context_stats,
            similar_warnings=similar_warnings,
            repo_head_sha=head_sha,
        )

    async def reflect_on_proposals(self, goal_id: str) -> ReflectionResult:
        """Reflect on proposed tickets for a goal.

        Evaluates ticket quality, identifies coverage gaps, and suggests
        priority adjustments.

        Args:
            goal_id: ID of the goal whose proposals to reflect on.

        Returns:
            ReflectionResult with assessment and suggestions.
        """
        # Get goal
        result = await self.db.execute(select(Goal).where(Goal.id == goal_id))
        goal = result.scalar_one_or_none()
        if not goal:
            raise ValueError(f"Goal not found: {goal_id}")

        # Get proposed tickets
        result = await self.db.execute(
            select(Ticket).where(
                and_(
                    Ticket.goal_id == goal_id,
                    Ticket.state == TicketState.PROPOSED.value,
                )
            )
        )
        tickets = list(result.scalars().all())

        if not tickets:
            return ReflectionResult(
                overall_quality="insufficient",
                quality_notes="No proposed tickets found for this goal.",
                coverage_gaps=["No tickets have been generated yet."],
                suggested_changes=[],
            )

        # Build prompt
        system_prompt = self._build_reflection_system_prompt()
        user_prompt = self._build_reflection_user_prompt(goal, tickets)

        response = self.llm.call_completion(
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=1500,
            system_prompt=system_prompt,
        )

        # Parse response
        data = self.llm.safe_parse_json(
            response.content,
            {
                "overall_quality": "needs_work",
                "quality_notes": "Unable to analyze tickets.",
                "coverage_gaps": [],
                "suggested_changes": [],
            },
        )

        # Build suggested changes with ticket info
        suggested_changes: list[SuggestedPriorityChange] = []
        for change in data.get("suggested_changes", []):
            ticket_id = change.get("ticket_id")
            # Find the ticket
            ticket = next((t for t in tickets if t.id == ticket_id), None)
            if not ticket:
                continue

            try:
                current_bucket = priority_to_bucket(ticket.priority or 50)
                suggested_bucket = PriorityBucket(change.get("suggested_bucket", "P2"))
            except ValueError:
                continue

            suggested_changes.append(
                SuggestedPriorityChange(
                    ticket_id=ticket_id,
                    ticket_title=ticket.title,
                    current_bucket=current_bucket,
                    current_priority=ticket.priority or 50,
                    suggested_bucket=suggested_bucket,
                    suggested_priority=bucket_to_priority(suggested_bucket),
                    reason=change.get("reason", ""),
                )
            )

        return ReflectionResult(
            overall_quality=data.get("overall_quality", "needs_work"),
            quality_notes=data.get("quality_notes", ""),
            coverage_gaps=data.get("coverage_gaps", []),
            suggested_changes=suggested_changes,
        )

    # =========================================================================
    # PROMPT BUILDERS
    # =========================================================================

    def _build_goal_system_prompt(self) -> str:
        """Build system prompt for goal-based ticket generation."""
        return """You are a technical project planner. Given a goal and optional repository context, break it down into 2-5 specific, actionable tickets.

Your response MUST be valid JSON with this exact structure:
{
  "tickets": [
    {
      "title": "Short, action-oriented title (verb first)",
      "description": "Clear description with acceptance criteria",
      "priority_bucket": "P0|P1|P2|P3",
      "priority_rationale": "Brief explanation of why this priority",
      "verification": ["command1", "command2"],
      "notes": "Optional implementation notes",
      "blocked_by": "Title of another ticket in this list that must complete first (or null)"
    }
  ]
}

Priority Buckets (USE THESE EXACTLY):
- P0: Critical - security issues, blocking bugs, data loss risks
- P1: High - important features, performance issues affecting users
- P2: Medium - improvements, nice-to-haves, minor bugs
- P3: Low - cleanup, documentation, cosmetic issues

Dependencies (blocked_by):
- If a ticket depends on another ticket being completed first, set blocked_by to that ticket's exact title
- Example: A "Write unit tests for auth module" ticket should have blocked_by: "Implement auth module"
- This prevents the blocked ticket from being executed until the blocker is done
- Only specify blocked_by if there's a true dependency (code must exist, API must be ready, etc.)
- Leave blocked_by as null if the ticket can be done independently

Guidelines:
- Create 2-5 tickets that together achieve the goal
- Each ticket should be independently implementable
- Titles should be concise and action-oriented (start with a verb)
- Descriptions should clearly explain the task and acceptance criteria
- Verification commands should be shell commands that verify completion
- Order tickets by logical implementation sequence
- Be realistic with priorities - not everything is P0!"""

    def _build_goal_user_prompt(self, goal: Goal, context: RepoContext | None) -> str:
        """Build user prompt for goal-based generation."""
        parts = [
            f"Goal: {goal.title}",
        ]
        if goal.description:
            parts.append(f"Description: {goal.description}")
        if context:
            parts.append(f"\nRepository context:\n{context.to_prompt_string()}")

        parts.append("\nGenerate actionable tickets as JSON.")
        return "\n".join(parts)

    def _build_analysis_system_prompt(self, focus_areas: list[str] | None) -> str:
        """Build system prompt for codebase analysis."""
        focus_hint = ""
        if focus_areas:
            focus_hint = f"\n\nFocus on these areas: {', '.join(focus_areas)}"

        return f"""You are a technical project planner analyzing a codebase. Based on the repository structure, TODOs, and metadata, identify improvement opportunities and generate actionable tickets.

Your response MUST be valid JSON with this exact structure:
{{
  "summary": "Brief overall assessment of the codebase (2-3 sentences)",
  "tickets": [
    {{
      "title": "Short, action-oriented title",
      "description": "What needs to be done and why",
      "priority_bucket": "P0|P1|P2|P3",
      "priority_rationale": "Why this priority",
      "verification": ["command to verify"],
      "notes": "Optional notes",
      "blocked_by": "Title of another ticket in this list that must complete first (or null)"
    }}
  ]
}}

Priority Buckets:
- P0: Critical (security, data loss, blocking bugs)
- P1: High (performance, important features)  
- P2: Medium (improvements, minor issues)
- P3: Low (cleanup, docs, cosmetic){focus_hint}

Dependencies (blocked_by):
- If a ticket depends on another ticket being completed first, set blocked_by to that ticket's exact title
- Example: "Write unit tests for auth module" should have blocked_by: "Implement auth module"
- Leave blocked_by as null if the ticket can be done independently

Guidelines:
- Generate 3-7 tickets based on what you observe
- Prioritize issues found in TODOs/FIXMEs
- Look for patterns: missing tests, outdated deps, code smells
- Be specific - reference actual files/paths when relevant
- Don't generate vague tickets like "improve code quality"
- Be conservative with P0/P1 - most tickets should be P2/P3"""

    def _build_analysis_user_prompt(
        self, context: RepoContext, focus_areas: list[str] | None
    ) -> str:
        """Build user prompt for codebase analysis."""
        parts = [context.to_prompt_string()]

        if focus_areas:
            parts.append(f"\nFocus areas requested: {', '.join(focus_areas)}")

        parts.append("\nAnalyze this codebase and generate improvement tickets as JSON.")
        return "\n".join(parts)

    def _build_reflection_system_prompt(self) -> str:
        """Build system prompt for ticket reflection."""
        return """You are reviewing proposed tickets for quality and coverage. Evaluate the tickets and suggest improvements.

Your response MUST be valid JSON with this structure:
{
  "overall_quality": "good|needs_work|insufficient",
  "quality_notes": "Detailed assessment of ticket quality",
  "coverage_gaps": ["Area not covered 1", "Area not covered 2"],
  "suggested_changes": [
    {
      "ticket_id": "uuid-here",
      "suggested_bucket": "P0|P1|P2|P3",
      "reason": "Why the priority should change"
    }
  ]
}

Evaluation criteria:
- Are tickets specific and actionable?
- Do they cover the goal comprehensively?
- Are priorities realistic (not everything is critical)?
- Are there obvious gaps or missing concerns?

Only suggest priority changes when clearly warranted. Don't change priorities just for the sake of it."""

    def _build_reflection_user_prompt(self, goal: Goal, tickets: list[Ticket]) -> str:
        """Build user prompt for reflection."""
        parts = [
            f"Goal: {goal.title}",
        ]
        if goal.description:
            parts.append(f"Description: {goal.description}")

        parts.append("\nProposed tickets:")
        for t in tickets:
            bucket = priority_to_bucket(t.priority or 50)
            parts.append(
                f"- [{t.id}] {t.title} (Priority: {bucket.value})"
                f"\n  {t.description or 'No description'}"
            )

        parts.append("\nEvaluate these tickets and respond with JSON.")
        return "\n".join(parts)

    def _build_ticket_validation_system_prompt(self) -> str:
        """Build system prompt for validating generated tickets against codebase."""
        return """You are a technical code reviewer validating whether a proposed ticket is appropriate for a codebase.

Your response MUST be valid JSON with this exact structure:
{
  "is_valid": true|false,
  "confidence": "high|medium|low",
  "validation_result": "appropriate|already_implemented|not_relevant|unclear",
  "reasoning": "Brief explanation of your assessment (max 2 sentences)",
  "suggested_modification": "Optional: How to modify the ticket to make it valid (or null)"
}

Validation Results:
- appropriate: Ticket is valid and should be created
- already_implemented: Feature/fix already exists in the codebase
- not_relevant: Ticket doesn't align with goal or codebase structure
- unclear: Cannot determine validity from available context

Guidelines:
- Check if similar functionality already exists in the codebase
- Verify the ticket aligns with the stated goal
- Consider the current codebase structure and patterns
- Be conservative - flag anything suspicious as "unclear" with low confidence
- Only mark as "already_implemented" if you see clear evidence in the code
- Look for existing files, functions, or features that match the ticket's intent"""

    def _build_ticket_validation_user_prompt(
        self, ticket: dict, goal_title: str, goal_description: str | None, context_summary: str
    ) -> str:
        """Build user prompt for validating a ticket."""
        parts = [
            f"Goal: {goal_title}",
        ]
        if goal_description:
            parts.append(f"Goal Description: {goal_description}")

        parts.append(f"\nProposed Ticket:")
        parts.append(f"Title: {ticket['title']}")
        parts.append(f"Description: {ticket.get('description', 'N/A')}")
        parts.append(f"Priority: {ticket.get('priority_bucket', 'N/A')}")

        parts.append(f"\nCodebase Context:\n{context_summary}")
        parts.append("\nIs this ticket appropriate to create? Provide validation assessment as JSON.")

        return "\n".join(parts)

    # =========================================================================
    # TICKET VALIDATION
    # =========================================================================

    def _validate_ticket_against_codebase(
        self, ticket: dict, goal: Goal, context_summary: str
    ) -> dict:
        """Validate a generated ticket against the codebase.

        Args:
            ticket: Raw ticket dict from generation.
            goal: The goal the ticket was generated for.
            context_summary: Summary of repository context.

        Returns:
            Validation result dict with keys: is_valid, confidence, validation_result, reasoning.
        """
        try:
            system_prompt = self._build_ticket_validation_system_prompt()
            user_prompt = self._build_ticket_validation_user_prompt(
                ticket=ticket,
                goal_title=goal.title,
                goal_description=goal.description,
                context_summary=context_summary,
            )

            response = self.llm.call_completion(
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=300,
                system_prompt=system_prompt,
            )

            # Parse JSON response
            validation = self.llm.safe_parse_json(
                response.content,
                {
                    "is_valid": True,  # Default to valid if parsing fails
                    "confidence": "low",
                    "validation_result": "appropriate",  # Default to appropriate (fail open)
                    "reasoning": "Unable to validate ticket, accepting by default",
                    "suggested_modification": None,
                },
            )

            # If result is "unclear", treat as appropriate (fail open)
            if validation.get("validation_result") == "unclear":
                validation["is_valid"] = True
                validation["validation_result"] = "appropriate"
                logger.debug(f"Validation unclear for '{ticket.get('title')}', accepting by default")

            return validation

        except Exception as e:
            logger.error(f"Ticket validation failed: {e}")
            # On error, default to accepting the ticket (fail open)
            return {
                "is_valid": True,
                "confidence": "low",
                "validation_result": "unclear",
                "reasoning": f"Validation error: {str(e)[:100]}",
                "suggested_modification": None,
            }

    # =========================================================================
    # AGENT-BASED TICKET GENERATION
    # =========================================================================

    def _build_agent_ticket_generation_prompt(
        self, goal: Goal, include_readme: bool = False
    ) -> str:
        """Build prompt for agent-based ticket generation.

        The agent will analyze the codebase in the workspace and generate tickets.
        """
        prompt = f"""# Task: Generate Implementation Tickets

## Goal
**{goal.title}**

{goal.description or "No additional description provided."}

## Instructions

Analyze this codebase and break down the goal into 2-5 specific, actionable tickets.

**IMPORTANT**: Your response MUST include a JSON code block with the tickets. Use this exact format:

```json
{{
  "tickets": [
    {{
      "title": "Short, action-oriented title (verb first)",
      "description": "Clear description with acceptance criteria",
      "priority_bucket": "P0|P1|P2|P3",
      "priority_rationale": "Brief explanation of why this priority",
      "verification": ["shell command to verify completion"],
      "notes": "Optional implementation notes",
      "blocked_by": "Title of another ticket in this list that must complete first (or null)"
    }}
  ]
}}
```

## Priority Buckets (use these exactly)
- **P0**: Critical - security issues, blocking bugs, data loss risks
- **P1**: High - important features, performance issues affecting users
- **P2**: Medium - improvements, nice-to-haves, minor bugs
- **P3**: Low - cleanup, documentation, cosmetic issues

## Dependencies (blocked_by)
- If a ticket depends on another ticket being completed first, set `blocked_by` to that ticket's **exact title**
- Example: A "Write unit tests for feature X" ticket should have `"blocked_by": "Implement feature X"`
- The blocked ticket will NOT be executed until the blocking ticket is marked as DONE
- Leave `blocked_by` as `null` if the ticket can be done independently

## Guidelines
- Create 2-5 tickets that together achieve the goal
- Each ticket should be independently implementable
- Titles should be concise and action-oriented (start with a verb)
- Descriptions should clearly explain the task and acceptance criteria
- Be realistic with priorities - not everything is P0!
- Reference actual files/paths when relevant

Now analyze the codebase and generate the tickets JSON."""

        return prompt

    def _build_agent_analysis_prompt(self, focus_areas: list[str] | None = None) -> str:
        """Build prompt for agent-based codebase analysis.

        The agent will analyze the codebase in the workspace and generate improvement tickets.
        """
        focus_hint = ""
        if focus_areas:
            focus_hint = f"\n\n**Focus Areas**: {', '.join(focus_areas)}"

        prompt = f"""# Task: Analyze Codebase and Generate Improvement Tickets

## Instructions

Analyze this codebase and identify improvement opportunities. Generate 3-7 actionable tickets.{focus_hint}

**IMPORTANT**: Your response MUST include a JSON code block with the analysis. Use this exact format:

```json
{{
  "summary": "Brief overall assessment of the codebase (2-3 sentences)",
  "tickets": [
    {{
      "title": "Short, action-oriented title",
      "description": "What needs to be done and why",
      "priority_bucket": "P0|P1|P2|P3",
      "priority_rationale": "Why this priority",
      "verification": ["shell command to verify"],
      "notes": "Optional notes",
      "blocked_by": "Title of another ticket in this list that must complete first (or null)"
    }}
  ]
}}
```

## Priority Buckets
- **P0**: Critical (security, data loss, blocking bugs)
- **P1**: High (performance, important features)
- **P2**: Medium (improvements, minor issues)
- **P3**: Low (cleanup, docs, cosmetic)

## Dependencies (blocked_by)
- If a ticket depends on another ticket being completed first, set `blocked_by` to that ticket's **exact title**
- Example: "Write unit tests for auth module" should have `"blocked_by": "Implement auth module"`
- Leave `blocked_by` as `null` if the ticket can be done independently

## What to Look For
- TODOs and FIXMEs in the code
- Missing tests or test coverage gaps
- Security issues or potential vulnerabilities
- Performance bottlenecks
- Code duplication or refactoring opportunities
- Missing documentation
- Outdated dependencies

## Guidelines
- Be specific - reference actual files/paths
- Don't generate vague tickets like "improve code quality"
- Be conservative with P0/P1 - most tickets should be P2/P3
- Each ticket should be independently implementable

Now analyze the codebase and generate the JSON."""

        return prompt

    def _call_agent_for_tickets(
        self, prompt: str, repo_root: Path, stream_callback=None
    ) -> str:
        """Call CLI agent or LLM API to generate tickets.

        When model is "cli/claude" (or any cli/* prefix), uses CLI only.
        Otherwise tries CLI first, then falls back to LLM API.

        Args:
            prompt: The prompt for ticket generation.
            repo_root: Path to the repository.
            stream_callback: Optional callback for streaming output.

        Returns:
            The agent's response text.

        Raises:
            ValueError: If neither CLI nor LLM API is available.
        """
        # Always try CLI first, fall back to LLM API on failure
        try:
            return self._call_cli_for_tickets(prompt, repo_root, stream_callback)
        except (ValueError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.warning(f"CLI agent failed ({e}), falling back to LLM API")
            if stream_callback:
                stream_callback(f"[CLI unavailable: {e}. Using LLM API...]")
            return self._call_llm_for_tickets(prompt, repo_root, stream_callback)

    def _get_llm_for_api_fallback(self) -> "LLMService":
        """Get an LLM service suitable for API calls.

        If the current model is CLI-based (cli/*), detects available API
        credentials and creates a temporary LLMService with a real model.

        Returns:
            LLMService configured for API calls.

        Raises:
            ValueError: If no API credentials are available.
        """
        import os

        # If model is already an API model, use existing LLM service
        if not self.config.model.startswith("cli/"):
            return self.llm

        # CLI model — detect available API keys and pick a model
        if os.environ.get("ANTHROPIC_API_KEY"):
            api_model = "anthropic/claude-sonnet-4-5-20250929"
        elif os.environ.get("OPENAI_API_KEY"):
            api_model = "gpt-4o-mini"
        elif os.environ.get("AWS_ACCESS_KEY_ID"):
            api_model = "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0"
        else:
            raise ValueError(
                "CLI agent unavailable (nested session) and no LLM API credentials found. "
                "Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or AWS credentials in backend/.env, "
                "or turn off 'Same as executor' in Settings and pick an API model."
            )

        from dataclasses import replace

        fallback_config = replace(self.config, model=api_model)
        logger.info(f"CLI fallback: using API model {api_model}")
        return LLMService(fallback_config)

    def _call_llm_for_tickets(
        self, prompt: str, repo_root: Path, stream_callback=None
    ) -> str:
        """Generate tickets using LLM API (fallback when CLI unavailable).

        Args:
            prompt: The prompt for ticket generation.
            repo_root: Path to the repository.
            stream_callback: Optional callback for streaming output.

        Returns:
            The LLM's response text containing JSON tickets.

        Raises:
            ValueError: If LLM is not configured or API call fails.
        """
        llm = self._get_llm_for_api_fallback()

        if stream_callback:
            stream_callback("[Generating tickets via LLM API...]")

        # Gather repo context for the LLM
        try:
            context = self.context_gatherer.gather(repo_root=repo_root)
            context_summary = context.to_prompt_string()[:8000]
        except Exception as e:
            logger.warning(f"Failed to gather repo context: {e}")
            context_summary = f"Repository at: {repo_root}"

        system_prompt = self._build_goal_system_prompt()
        messages = [
            {"role": "user", "content": f"{context_summary}\n\n{prompt}"},
        ]

        try:
            response = llm.call_completion(
                messages=messages,
                max_tokens=4000,
                system_prompt=system_prompt,
                json_mode=True,
                timeout=60,
            )
            logger.info(f"LLM API response length: {len(response.content)} chars")
            if stream_callback:
                stream_callback("[LLM API response received]")
            return response.content
        except Exception as e:
            raise ValueError(
                f"LLM API call failed: {e}. "
                "Please verify your LLM credentials in Settings."
            )

    def _call_cli_for_tickets(
        self, prompt: str, repo_root: Path, stream_callback=None
    ) -> str:
        """Call the agent CLI to generate tickets.

        Args:
            prompt: The prompt for ticket generation.
            repo_root: Path to the repository.
            stream_callback: Optional callback for streaming output.

        Returns:
            The agent's response text.

        Raises:
            ValueError: If no agent is available or agent fails.
            FileNotFoundError: If agent command not found.
        """
        import os

        # Get agent path from config
        agent_path = self.config.get_agent_path()

        if os.path.exists(agent_path):
            logger.info(f"Using agent from config: {agent_path}")
            # Determine if it's cursor-agent style (needs --workspace) or claude style
            if "cursor-agent" in agent_path:
                cmd = [agent_path, "--print", "--workspace", str(repo_root), prompt]
            else:
                # Claude-style: doesn't need --workspace
                cmd = [agent_path, "--print", prompt]
        else:
            # Fall back to executor service detection
            logger.warning(f"Agent not found at configured path: {agent_path}, falling back to auto-detection")
            try:
                executor = ExecutorService.detect_headless_executor(agent_path=agent_path)
                if not executor:
                    executor = ExecutorService.detect_executor(agent_path=agent_path)
            except Exception as e:
                raise ValueError(f"No agent CLI available at {agent_path} and auto-detection failed: {e}")

            logger.info(f"Using agent: {executor.executor_type.value} for ticket generation")

            # Build command based on executor type
            if executor.executor_type == ExecutorType.CLAUDE:
                cmd = [executor.command, "--print", prompt]
            elif executor.executor_type == ExecutorType.CURSOR_AGENT:
                cmd = [executor.command, "--print", "--workspace", str(repo_root), prompt]
            else:
                # Cursor (interactive) - not suitable for automated generation
                raise ValueError(
                    f"Agent {executor.executor_type.value} is interactive only. "
                    "Need cursor-agent or claude CLI for automated ticket generation."
                )

        # Run the agent
        logger.info(f"Running agent command: {cmd[0]} (cwd={repo_root})")

        # Strip Claude Code session env vars to avoid "nested session" errors
        # when spawning claude CLI from within a Claude Code session
        clean_env = {
            k: v for k, v in os.environ.items()
            if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")
        }

        try:
            if stream_callback:
                # Stream output line by line for real-time feedback
                process = subprocess.Popen(
                    cmd,
                    cwd=repo_root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,  # Line buffered
                    env=clean_env,
                )

                output_lines = []
                # Read stdout line by line
                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                    if line:
                        output_lines.append(line)
                        stream_callback(line.rstrip())

                logger.info(f"Agent subprocess completed. Total lines: {len(output_lines)}")

                # Wait for process to complete
                try:
                    process.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise ValueError("Agent timed out after 120 seconds")

                if process.returncode != 0:
                    stderr = process.stderr.read()
                    logger.error(f"Agent failed with code {process.returncode}: {stderr}")
                    raise ValueError(f"Agent failed: {stderr[:500]}")

                return "".join(output_lines)
            else:
                # Non-streaming mode (original behavior)
                result = subprocess.run(
                    cmd,
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    timeout=120,  # 2 minute timeout for ticket generation
                    env=clean_env,
                )

                if result.returncode != 0:
                    logger.error(f"Agent failed with code {result.returncode}: {result.stderr}")
                    raise ValueError(f"Agent failed: {result.stderr[:500]}")

                logger.debug(f"Agent response length: {len(result.stdout)} chars")
                return result.stdout

        except subprocess.TimeoutExpired:
            raise ValueError("Agent timed out after 120 seconds")
        except FileNotFoundError:
            raise ValueError(f"Agent command not found: {cmd[0]}")

    def _parse_agent_json_response(self, response: str) -> dict:
        """Parse JSON from agent response.

        The agent may include explanatory text around the JSON.
        This method extracts and parses the JSON block.

        Args:
            response: The full agent response text.

        Returns:
            Parsed JSON dict with tickets.
        """
        # Try to find JSON in code blocks first
        json_block_pattern = r"```(?:json)?\s*(\{[\s\S]*?\})\s*```"
        matches = re.findall(json_block_pattern, response)

        for match in matches:
            try:
                data = json.loads(match)
                if "tickets" in data:
                    return data
            except json.JSONDecodeError:
                continue

        # Try to find raw JSON object
        json_pattern = r"\{[\s\S]*\"tickets\"[\s\S]*\}"
        matches = re.findall(json_pattern, response)

        for match in matches:
            try:
                data = json.loads(match)
                if "tickets" in data:
                    return data
            except json.JSONDecodeError:
                continue

        # Fallback: try to parse entire response as JSON
        try:
            data = json.loads(response)
            if "tickets" in data:
                return data
        except json.JSONDecodeError:
            pass

        logger.warning(f"Could not parse JSON from agent response: {response[:500]}")
        return {"tickets": []}

    # =========================================================================
    # HELPERS
    # =========================================================================

    async def _get_existing_tickets(self, goal_id: str | None) -> list[tuple[str, str]]:
        """Get existing ticket (id, title) pairs for deduplication."""
        query = select(Ticket.id, Ticket.title)
        if goal_id:
            query = query.where(Ticket.goal_id == goal_id)
        result = await self.db.execute(query)
        return [(row[0], row[1]) for row in result.fetchall()]

    def _check_duplicate(
        self, new_title: str, existing_tickets: list[tuple[str, str]]
    ) -> tuple[str, str | None, str | None, float]:
        """Check if a title is a duplicate.

        Returns:
            Tuple of (status, existing_id, existing_title, similarity):
            - status: "exact" (hard block), "similar" (warning only), or "ok" (no match)
            - existing_id: ID of matching ticket if any
            - existing_title: Title of matching ticket if any
            - similarity: Similarity score (0-1)
        """
        new_lower = new_title.lower().strip()
        new_tokens = set(new_lower.split())

        best_match: tuple[str, str, float] | None = None

        for existing_id, existing_title in existing_tickets:
            existing_lower = existing_title.lower().strip()

            # Exact match = hard block
            if new_lower == existing_lower:
                return ("exact", existing_id, existing_title, 1.0)

            # Token overlap for similarity
            existing_tokens = set(existing_lower.split())
            if not new_tokens or not existing_tokens:
                continue

            overlap = len(new_tokens & existing_tokens)
            similarity = overlap / min(len(new_tokens), len(existing_tokens))

            if similarity > DEDUP_SIMILARITY_THRESHOLD:
                if best_match is None or similarity > best_match[2]:
                    best_match = (existing_id, existing_title, similarity)

        if best_match:
            return ("similar", best_match[0], best_match[1], best_match[2])

        return ("ok", None, None, 0.0)

    def _get_git_head_sha(self, repo_root: Path) -> str | None:
        """Get the current git HEAD SHA (full 40-char SHA) for cache invalidation.
        
        We store the full SHA to avoid rare collision issues with short SHAs.
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()  # Full SHA (40 chars)
        except Exception as e:
            logger.debug(f"Failed to get git HEAD: {e}")
        return None

    def _get_workspace_head_sha(self, workspace_path: Path, repo_root: Path) -> str | None:
        """Get the git HEAD SHA for a workspace path if different from repo root.
        
        Worktrees may be at different SHAs than the main repo.
        Returns None if workspace_path is the same as repo_root or not a git dir.
        """
        if workspace_path.resolve() == repo_root.resolve():
            return None  # Same as repo root, no need for separate SHA
        
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()  # Full SHA
        except Exception as e:
            logger.debug(f"Failed to get workspace HEAD: {e}")
        return None

    def _compute_cache_key(
        self, repo_root: Path, focus_areas: list[str] | None, head_sha: str | None
    ) -> str:
        """Compute cache key for analysis results.

        Includes git HEAD SHA so cache invalidates on new commits.
        """
        key_parts = [str(repo_root)]
        if head_sha:
            key_parts.append(head_sha)
        if focus_areas:
            key_parts.extend(sorted(focus_areas))
        key_str = "|".join(key_parts)
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]

    async def _get_cached_analysis(self, cache_key: str) -> dict | None:
        """Get cached analysis result if valid."""
        try:
            result = await self.db.execute(
                select(AnalysisCache).where(
                    and_(
                        AnalysisCache.id == cache_key,
                        AnalysisCache.expires_at > datetime.now(UTC),
                    )
                )
            )
            cached = result.scalar_one_or_none()
            if cached:
                return json.loads(cached.result_json)
        except Exception as e:
            logger.debug(f"Cache lookup failed: {e}")
        return None

    async def _cache_analysis(self, cache_key: str, result: dict) -> None:
        """Cache analysis result."""
        try:
            expires_at = datetime.now(UTC) + timedelta(minutes=ANALYSIS_CACHE_TTL_MINUTES)

            # Upsert cache entry
            existing = await self.db.execute(
                select(AnalysisCache).where(AnalysisCache.id == cache_key)
            )
            cache_entry = existing.scalar_one_or_none()

            if cache_entry:
                cache_entry.result_json = json.dumps(result)
                cache_entry.expires_at = expires_at
            else:
                cache_entry = AnalysisCache(
                    id=cache_key,
                    result_json=json.dumps(result),
                    expires_at=expires_at,
                )
                self.db.add(cache_entry)

            await self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to cache analysis: {e}")

