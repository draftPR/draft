"""Agent session service — launches and manages multi-agent teams.

Orchestrates the lifecycle of agent teams for ticket execution:
1. Launch team (create tmux sessions, inject board CLI, send prompts)
2. Monitor status (parse PULSE protocol, check message board)
3. Detect completion (orchestrator DONE signal or timeout)
4. Stop team (kill tmux sessions, update DB records)

Inspired by coral's session_manager.py.
"""

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.agent_team import (
    AgentTeam,
    AgentTeamMember,
    TeamAgentSession,
)
from app.services import tmux_manager
from app.services.board_cli_service import inject_board_cli
from app.services.executor_service import ExecutorService, ExecutorType
from app.services.message_board_service import MessageBoardService

logger = logging.getLogger(__name__)

# PULSE protocol regex (same as coral)
PULSE_REGEX = re.compile(r"\|\|PULSE:(\w+)\s+(.*?)\|\|")


class TeamSessionService:
    """Manages multi-agent team sessions for ticket execution."""

    def __init__(self, db: Session):
        self.db = db
        self.board_service = MessageBoardService(db)

    def launch_team(
        self,
        ticket_id: str,
        board_id: str,
        job_id: str,
        team: AgentTeam,
        worktree_path: Path,
        ticket_title: str,
        ticket_description: str | None,
        api_base_url: str = "http://localhost:8000",
        yolo_mode: bool = False,
    ) -> list[TeamAgentSession]:
        """Launch all agents in a team for a ticket execution.

        1. Injects board CLI into worktree
        2. Launches orchestrator (team lead) first
        3. Launches worker agents
        4. Sends initial prompts

        Returns list of created TeamAgentSession records.
        """
        if not tmux_manager.is_tmux_available():
            raise RuntimeError(
                "tmux is required for multi-agent execution but is not installed. "
                "Install it with: brew install tmux (macOS) or apt install tmux (Linux)"
            )

        # Inject board CLI into the worktree
        inject_board_cli(worktree_path, api_base_url)

        # Build team roster string for env var
        roster_lines = []
        for member in team.members:
            roster_lines.append(f"  - {member.display_name} ({member.role})")
        roster_str = "\n".join(roster_lines)

        # Separate orchestrator from workers
        orchestrator = None
        workers = []
        for member in team.members:
            if member.receive_mode == "all" or member.role == "team_lead":
                orchestrator = member
            else:
                workers.append(member)

        if orchestrator is None:
            raise ValueError(
                "Team must have an orchestrator (team_lead with receive_mode='all')"
            )

        sessions = []

        # Launch orchestrator first
        orch_session = self._launch_agent(
            ticket_id=ticket_id,
            board_id=board_id,
            job_id=job_id,
            member=orchestrator,
            worktree_path=worktree_path,
            roster_str=roster_str,
            api_base_url=api_base_url,
            yolo_mode=yolo_mode,
        )
        sessions.append(orch_session)

        # Subscribe orchestrator to board
        self.board_service.subscribe(board_id, ticket_id, orch_session.session_uuid)

        # Send orchestrator its initial prompt
        orchestrator_prompt = self._build_orchestrator_prompt(
            ticket_title=ticket_title,
            ticket_description=ticket_description,
            roster_str=roster_str,
            member=orchestrator,
        )
        tmux_manager.send_text(orch_session.tmux_session_name, orchestrator_prompt)

        # Launch workers
        for worker_member in workers:
            worker_session = self._launch_agent(
                ticket_id=ticket_id,
                board_id=board_id,
                job_id=job_id,
                member=worker_member,
                worktree_path=worktree_path,
                roster_str=roster_str,
                api_base_url=api_base_url,
                yolo_mode=yolo_mode,
            )
            sessions.append(worker_session)

            # Subscribe worker to board
            self.board_service.subscribe(
                board_id, ticket_id, worker_session.session_uuid
            )

            # Send worker its initial prompt
            worker_prompt = self._build_worker_prompt(
                member=worker_member,
                roster_str=roster_str,
            )
            tmux_manager.send_text(worker_session.tmux_session_name, worker_prompt)

        self.db.commit()
        logger.info(
            "Launched team of %d agents for ticket %s",
            len(sessions),
            ticket_id,
        )
        return sessions

    def _launch_agent(
        self,
        ticket_id: str,
        board_id: str,
        job_id: str,
        member: AgentTeamMember,
        worktree_path: Path,
        roster_str: str,
        api_base_url: str,
        yolo_mode: bool,
    ) -> TeamAgentSession:
        """Launch a single agent in a tmux session."""
        session_uuid = str(uuid4())
        short_uuid = session_uuid[:8]
        session_name = tmux_manager.generate_session_name(
            ticket_id, member.role, short_uuid
        )

        # Set up log file
        import tempfile

        log_dir = Path(tempfile.gettempdir())
        log_path = log_dir / f"draft_agent_{session_uuid}.log"

        # Create tmux session
        tmux_manager.create_session(session_name, str(worktree_path))
        tmux_manager.setup_logging(session_name, log_path)

        # Export env vars in the shell
        env_exports = (
            f'export DRAFT_BOARD_ID="{board_id}" '
            f'DRAFT_TICKET_ID="{ticket_id}" '
            f'DRAFT_SESSION_ID="{session_uuid}" '
            f'DRAFT_AGENT_ROLE="{member.display_name}" '
            f'DRAFT_API_URL="{api_base_url}"'
        )
        tmux_manager.send_command(session_name, env_exports)
        # Add board CLI to PATH
        tmux_manager.send_command(
            session_name,
            f'export PATH="{worktree_path}/.draft:$PATH"',
        )

        # Detect executor for this member
        executor_info = ExecutorService.detect_executor(preferred=member.executor_type)

        # Build and send the executor launch command
        launch_cmd = self._build_launch_command(
            executor_info.executor_type,
            executor_info.command,
            worktree_path,
            yolo_mode,
        )
        tmux_manager.send_command(session_name, launch_cmd)

        # Create DB record
        agent_session = TeamAgentSession(
            ticket_id=ticket_id,
            team_member_id=member.id,
            job_id=job_id,
            tmux_session_name=session_name,
            session_uuid=session_uuid,
            status="running",
            log_path=str(log_path),
        )
        self.db.add(agent_session)
        self.db.flush()

        logger.info(
            "Launched agent: %s (%s) in tmux session %s",
            member.display_name,
            member.executor_type,
            session_name,
        )
        return agent_session

    def _build_launch_command(
        self,
        executor_type: ExecutorType,
        command: str,
        worktree_path: Path,
        yolo_mode: bool,
    ) -> str:
        """Build the CLI command to launch an agent executor."""
        if executor_type == ExecutorType.CLAUDE:
            cmd = f"env -u CLAUDECODE {command}"
            if yolo_mode:
                cmd += " --dangerously-skip-permissions"
            return cmd
        elif executor_type == ExecutorType.CURSOR_AGENT:
            cmd = (
                f"{command} --print --output-format=stream-json "
                f"--trust --workspace {worktree_path}"
            )
            if yolo_mode:
                cmd += " --force"
            return cmd
        elif executor_type == ExecutorType.CODEX:
            cmd = f"{command} --print --auto-edit"
            if yolo_mode:
                cmd += " --full-auto"
            return cmd
        elif executor_type == ExecutorType.GEMINI:
            cmd = f"{command} --print"
            if yolo_mode:
                cmd += " --yolo"
            return cmd
        else:
            # Generic fallback
            cmd = f"{command} --print"
            if yolo_mode:
                cmd += " --dangerously-skip-permissions"
            return cmd

    def _build_orchestrator_prompt(
        self,
        ticket_title: str,
        ticket_description: str | None,
        roster_str: str,
        member: AgentTeamMember,
    ) -> str:
        """Build the initial prompt for the orchestrator."""
        behavior = member.behavior_prompt or ""
        desc = ticket_description or "No additional description."

        return (
            f"{behavior}\n\n"
            f"# Ticket: {ticket_title}\n\n"
            f"## Description\n{desc}\n\n"
            f"## Your Team\n{roster_str}\n\n"
            f"## Communication\n"
            f"Use the board CLI to communicate with your team:\n"
            f'  .draft/board-cli.sh post "your message"\n'
            f"  .draft/board-cli.sh read\n"
            f"  .draft/board-cli.sh check\n"
            f"  .draft/board-cli.sh team\n\n"
            f"Address team members by role: @Developer, @CodeReviewer, @QA, etc.\n\n"
            f"## Status Reporting\n"
            f"Report status with PULSE tags in your output:\n"
            f"  ||PULSE:STATUS Working on planning||\n"
            f"  ||PULSE:SUMMARY Implementing auth feature||\n\n"
            f"## Completion\n"
            f"When ALL work is done, post:\n"
            f'  .draft/board-cli.sh post "DONE: <summary>"\n'
            f"This signals Draft to collect changes and transition the ticket.\n\n"
            f"Begin by analyzing the ticket, then delegate work to your team."
        )

    def _build_worker_prompt(
        self,
        member: AgentTeamMember,
        roster_str: str,
    ) -> str:
        """Build the initial prompt for a worker agent."""
        behavior = member.behavior_prompt or f"You are {member.display_name}."

        return (
            f"{behavior}\n\n"
            f"## Your Team\n{roster_str}\n\n"
            f"## Communication\n"
            f"Use the board CLI to communicate:\n"
            f'  .draft/board-cli.sh post "your message"\n'
            f"  .draft/board-cli.sh read\n"
            f"  .draft/board-cli.sh check\n\n"
            f"## Instructions\n"
            f"Wait for the Team Lead to assign you work.\n"
            f"Check for messages periodically: .draft/board-cli.sh check\n"
            f"When you receive an assignment, execute it and report back.\n\n"
            f"## Status Reporting\n"
            f"  ||PULSE:STATUS Waiting for assignment||\n"
            f"  ||PULSE:STATUS Working on <task>||\n"
            f"  ||PULSE:SUMMARY <one sentence>||\n\n"
            f"Start by checking the board for messages from the Team Lead."
        )

    def stop_team(self, ticket_id: str) -> int:
        """Stop all agent sessions for a ticket. Returns count stopped."""
        stmt = select(TeamAgentSession).where(
            and_(
                TeamAgentSession.ticket_id == ticket_id,
                TeamAgentSession.status.in_(["running", "waiting", "pending"]),
            )
        )
        sessions = list(self.db.execute(stmt).scalars().all())
        count = 0
        for session in sessions:
            tmux_manager.kill_session(session.tmux_session_name)
            session.status = "done"
            session.ended_at = datetime.now(UTC)
            count += 1
        self.db.commit()
        logger.info("Stopped %d agents for ticket %s", count, ticket_id)
        return count

    def stop_agent(self, session_id: str) -> bool:
        """Stop a single agent session."""
        stmt = select(TeamAgentSession).where(TeamAgentSession.id == session_id)
        session = self.db.execute(stmt).scalar_one_or_none()
        if session is None:
            return False
        tmux_manager.kill_session(session.tmux_session_name)
        session.status = "done"
        session.ended_at = datetime.now(UTC)
        self.db.commit()
        return True

    def get_team_status(self, ticket_id: str) -> list[dict]:
        """Get status of all agent sessions for a ticket."""
        stmt = select(TeamAgentSession).where(TeamAgentSession.ticket_id == ticket_id)
        sessions = list(self.db.execute(stmt).scalars().all())

        result = []
        for session in sessions:
            alive = tmux_manager.is_session_alive(session.tmux_session_name)
            if not alive and session.status in ("running", "waiting", "pending"):
                session.status = "failed"
                session.ended_at = datetime.now(UTC)

            # Parse PULSE status from log
            pulse_status = session.last_pulse_status
            pulse_summary = session.last_pulse_summary
            if alive and session.log_path:
                new_status, new_summary = self._parse_pulse_from_log(session.log_path)
                if new_status:
                    pulse_status = new_status
                    session.last_pulse_status = new_status
                if new_summary:
                    pulse_summary = new_summary
                    session.last_pulse_summary = new_summary

            result.append(
                {
                    "id": session.id,
                    "team_member_id": session.team_member_id,
                    "tmux_session_name": session.tmux_session_name,
                    "session_uuid": session.session_uuid,
                    "status": session.status,
                    "is_alive": alive,
                    "pulse_status": pulse_status,
                    "pulse_summary": pulse_summary,
                    "created_at": (
                        session.created_at.isoformat() if session.created_at else None
                    ),
                    "ended_at": (
                        session.ended_at.isoformat() if session.ended_at else None
                    ),
                }
            )

        self.db.commit()
        return result

    def check_team_completion(
        self,
        ticket_id: str,
        board_id: str,
        strategy: str = "orchestrator_done_or_timeout",
    ) -> bool:
        """Check if the team has completed its work.

        Strategies:
        - "orchestrator_done": Team lead posted a DONE message
        - "all_idle": All agents idle (tmux sessions dead)
        - "orchestrator_done_or_timeout": Either DONE or all dead
        """
        if strategy in ("orchestrator_done", "orchestrator_done_or_timeout"):
            messages = self.board_service.get_all_messages(board_id, ticket_id)
            for msg in reversed(messages):
                if msg.content.strip().upper().startswith("DONE:"):
                    if (
                        "lead" in msg.sender_role.lower()
                        or "orchestrator" in msg.sender_role.lower()
                    ):
                        return True

        if strategy in ("all_idle", "orchestrator_done_or_timeout"):
            stmt = select(TeamAgentSession).where(
                and_(
                    TeamAgentSession.ticket_id == ticket_id,
                    TeamAgentSession.status.in_(["running", "waiting", "pending"]),
                )
            )
            active_sessions = list(self.db.execute(stmt).scalars().all())
            all_dead = True
            for session in active_sessions:
                if tmux_manager.is_session_alive(session.tmux_session_name):
                    all_dead = False
                    break
            if all_dead and active_sessions:
                return True

        return False

    def send_nudge(self, session: TeamAgentSession, message: str) -> None:
        """Send a nudge message to an agent's tmux session."""
        if tmux_manager.is_session_alive(session.tmux_session_name):
            tmux_manager.send_text(session.tmux_session_name, message)

    def _parse_pulse_from_log(
        self, log_path: str, tail_lines: int = 50
    ) -> tuple[str | None, str | None]:
        """Parse PULSE status/summary from the tail of a log file."""
        try:
            log_file = Path(log_path)
            if not log_file.exists():
                return None, None

            lines = log_file.read_text().splitlines()[-tail_lines:]
            text = "\n".join(lines)

            status = None
            summary = None
            for match in PULSE_REGEX.finditer(text):
                tag = match.group(1).upper()
                value = match.group(2).strip()
                if tag == "STATUS":
                    status = value
                elif tag == "SUMMARY":
                    summary = value

            return status, summary
        except Exception:
            return None, None
