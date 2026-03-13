"""Tests for cleanup service safety guards.

These tests verify the most dangerous scenarios are properly handled:
- git worktree remove fails but path remains registered
- Worktree path equals main repo path (symlink attacks)
"""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EventType
from app.models.goal import Goal
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.models.workspace import Workspace
from app.services.cleanup_service import CleanupService, _sanitize_output


class TestSanitizeOutput:
    """Test the _sanitize_output helper function."""

    def test_removes_null_bytes(self):
        """Null bytes should be stripped."""
        input_text = "hello\x00world"
        result = _sanitize_output(input_text)
        assert "\x00" not in result
        assert result == "helloworld"

    def test_removes_control_characters(self):
        """Control characters (except newline/tab) should be stripped."""
        # \x01 is SOH, \x7f is DEL
        input_text = "hello\x01world\x7f!"
        result = _sanitize_output(input_text)
        assert result == "helloworld!"

    def test_preserves_newlines_and_tabs(self):
        """Newlines and tabs should be preserved."""
        input_text = "line1\nline2\ttab"
        result = _sanitize_output(input_text)
        assert result == "line1\nline2\ttab"

    def test_removes_carriage_returns(self):
        """Carriage returns should be stripped (Windows line endings)."""
        input_text = "line1\r\nline2\rline3"
        result = _sanitize_output(input_text)
        # \r should be stripped, \n should remain
        assert "\r" not in result
        assert result == "line1\nline2line3"

    def test_truncates_to_max_length(self):
        """Output should be truncated to max_length."""
        input_text = "a" * 1000
        result = _sanitize_output(input_text, max_length=100)
        assert len(result) == 100

    def test_handles_none(self):
        """None input should return None."""
        assert _sanitize_output(None) is None


class TestCleanupServicePathValidation:
    """Test path validation safety guards."""

    @pytest.mark.asyncio
    async def test_repo_path_equals_worktree_path_is_blocked(self, db: AsyncSession):
        """Test that cleanup is blocked when worktree path resolves to repo path.

        This prevents symlink attacks where .draft/worktrees/foo -> /repo
        """
        # Create test entities
        goal = Goal(id=str(uuid4()), title="Test Goal")
        db.add(goal)
        await db.flush()

        ticket = Ticket(
            id=str(uuid4()),
            goal_id=goal.id,
            title="Test ticket",
            state="done",
        )
        db.add(ticket)
        await db.flush()

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            worktrees_dir = repo_path / ".draft/worktrees"
            worktrees_dir.mkdir(parents=True)

            # Create a symlink that points back to repo root
            evil_symlink = worktrees_dir / "evil-link"
            evil_symlink.symlink_to(repo_path)

            workspace = Workspace(
                id=str(uuid4()),
                ticket_id=ticket.id,
                worktree_path=str(evil_symlink),
                branch_name="test-branch",
                created_at=datetime.now(UTC),
            )
            db.add(workspace)
            await db.commit()

            service = CleanupService(db)

            # Patch WorkspaceService.get_repo_path to return our temp repo
            with patch(
                "app.services.cleanup_service.WorkspaceService.get_repo_path",
                return_value=repo_path,
            ):
                # Execute cleanup - should be blocked
                result = await service.delete_worktree(
                    workspace=workspace,
                    ticket_id=ticket.id,
                    actor_id="test-actor",
                    force=False,
                    delete_branch=False,
                )

            # Assert: blocked
            assert result is False

            # Assert: WORKTREE_CLEANUP_FAILED event
            events_result = await db.execute(
                select(TicketEvent)
                .where(TicketEvent.ticket_id == ticket.id)
                .where(
                    TicketEvent.event_type == EventType.WORKTREE_CLEANUP_FAILED.value
                )
            )
            events = events_result.scalars().all()
            assert len(events) == 1

            payload = json.loads(events[0].payload_json)
            assert payload.get("cleanup_failed") is True

            # Assert: cleaned_up_at remains NULL
            await db.refresh(workspace)
            assert workspace.cleaned_up_at is None

    @pytest.mark.asyncio
    async def test_worktree_path_outside_draft_dir_is_blocked(self, db: AsyncSession):
        """Test that cleanup is blocked for paths outside .draft/worktrees."""
        goal = Goal(id=str(uuid4()), title="Test Goal")
        db.add(goal)
        await db.flush()

        ticket = Ticket(
            id=str(uuid4()),
            goal_id=goal.id,
            title="Test ticket",
            state="done",
        )
        db.add(ticket)
        await db.flush()

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            # Create worktrees dir but put workspace path elsewhere
            worktrees_dir = repo_path / ".draft/worktrees"
            worktrees_dir.mkdir(parents=True)

            # Path that's NOT under .draft/worktrees
            evil_path = repo_path / "src" / "evil-dir"
            evil_path.mkdir(parents=True)

            workspace = Workspace(
                id=str(uuid4()),
                ticket_id=ticket.id,
                worktree_path=str(evil_path),
                branch_name="test-branch",
                created_at=datetime.now(UTC),
            )
            db.add(workspace)
            await db.commit()

            service = CleanupService(db)

            with patch(
                "app.services.cleanup_service.WorkspaceService.get_repo_path",
                return_value=repo_path,
            ):
                result = await service.delete_worktree(
                    workspace=workspace,
                    ticket_id=ticket.id,
                    actor_id="test-actor",
                    force=False,
                    delete_branch=False,
                )

            assert result is False

            events_result = await db.execute(
                select(TicketEvent)
                .where(TicketEvent.ticket_id == ticket.id)
                .where(
                    TicketEvent.event_type == EventType.WORKTREE_CLEANUP_FAILED.value
                )
            )
            events = events_result.scalars().all()
            assert len(events) == 1
            assert "not under" in events[0].reason.lower()


class TestCleanupServiceStillRegistered:
    """Test handling of worktrees that remain registered after removal attempt."""

    @pytest.mark.asyncio
    async def test_still_registered_after_remove_fails_returns_false(
        self, db: AsyncSession
    ):
        """Test: git worktree remove fails AND path still registered -> returns False."""
        goal = Goal(id=str(uuid4()), title="Test Goal")
        db.add(goal)
        await db.flush()

        ticket = Ticket(
            id=str(uuid4()),
            goal_id=goal.id,
            title="Test ticket",
            state="done",
        )
        db.add(ticket)
        await db.flush()

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            worktrees_dir = repo_path / ".draft/worktrees"
            worktrees_dir.mkdir(parents=True)

            # Create actual worktree directory
            worktree_path = worktrees_dir / "test-worktree"
            worktree_path.mkdir()

            workspace = Workspace(
                id=str(uuid4()),
                ticket_id=ticket.id,
                worktree_path=str(worktree_path),
                branch_name="test-branch",
                created_at=datetime.now(UTC),
            )
            db.add(workspace)
            await db.commit()

            service = CleanupService(db)

            # Mock subprocess: worktree remove fails, list shows still registered
            with (
                patch("app.services.cleanup_service.subprocess.run") as mock_run,
                patch("app.services.cleanup_service.shutil.rmtree") as mock_rmtree,
                patch(
                    "app.services.cleanup_service.WorkspaceService.get_repo_path",
                    return_value=repo_path,
                ),
            ):

                def run_side_effect(cmd, **kwargs):
                    result = MagicMock()
                    if cmd[:3] == ["git", "worktree", "remove"]:
                        result.returncode = 1
                        result.stderr = "error: cannot remove worktree"
                        result.stdout = ""
                    elif cmd[:3] == ["git", "worktree", "list"]:
                        # Return porcelain format showing worktree as registered
                        result.returncode = 0
                        result.stdout = f"worktree {worktree_path}\nHEAD abc123\nbranch refs/heads/test-branch\n"
                        result.stderr = ""
                    else:
                        result.returncode = 0
                        result.stdout = ""
                        result.stderr = ""
                    return result

                mock_run.side_effect = run_side_effect

                result = await service.delete_worktree(
                    workspace=workspace,
                    ticket_id=ticket.id,
                    actor_id="test-actor",
                    force=False,
                    delete_branch=False,
                )

                # Assert: Returns False
                assert result is False

                # Assert: rmtree NOT called (worktree still registered)
                mock_rmtree.assert_not_called()

            # Assert: cleaned_up_at remains NULL
            await db.refresh(workspace)
            assert workspace.cleaned_up_at is None

            # Assert: WORKTREE_CLEANUP_FAILED event with still_registered=True
            events_result = await db.execute(
                select(TicketEvent)
                .where(TicketEvent.ticket_id == ticket.id)
                .where(
                    TicketEvent.event_type == EventType.WORKTREE_CLEANUP_FAILED.value
                )
            )
            events = events_result.scalars().all()
            assert len(events) == 1

            payload = json.loads(events[0].payload_json)
            assert payload.get("cleanup_failed") is True
            assert payload.get("still_registered") is True
            assert payload.get("worktree_removed") is False

    @pytest.mark.asyncio
    async def test_force_true_still_registered_returns_false(self, db: AsyncSession):
        """Test: force=True but still registered -> still returns False.

        Even with force=True, we cannot safely proceed if the worktree
        is still registered. cleaned_up_at must remain NULL.
        """
        goal = Goal(id=str(uuid4()), title="Test Goal")
        db.add(goal)
        await db.flush()

        ticket = Ticket(
            id=str(uuid4()),
            goal_id=goal.id,
            title="Test ticket",
            state="done",
        )
        db.add(ticket)
        await db.flush()

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            worktrees_dir = repo_path / ".draft/worktrees"
            worktrees_dir.mkdir(parents=True)

            worktree_path = worktrees_dir / "test-worktree"
            worktree_path.mkdir()

            workspace = Workspace(
                id=str(uuid4()),
                ticket_id=ticket.id,
                worktree_path=str(worktree_path),
                branch_name="test-branch",
                created_at=datetime.now(UTC),
            )
            db.add(workspace)
            await db.commit()

            service = CleanupService(db)

            with (
                patch("app.services.cleanup_service.subprocess.run") as mock_run,
                patch("app.services.cleanup_service.shutil.rmtree") as mock_rmtree,
                patch(
                    "app.services.cleanup_service.WorkspaceService.get_repo_path",
                    return_value=repo_path,
                ),
            ):

                def run_side_effect(cmd, **kwargs):
                    result = MagicMock()
                    if cmd[:3] == ["git", "worktree", "remove"]:
                        result.returncode = 1
                        result.stderr = "error: cannot remove"
                        result.stdout = ""
                    elif cmd[:3] == ["git", "worktree", "list"]:
                        result.returncode = 0
                        result.stdout = f"worktree {worktree_path}\n"
                        result.stderr = ""
                    else:
                        result.returncode = 0
                        result.stdout = ""
                        result.stderr = ""
                    return result

                mock_run.side_effect = run_side_effect

                # Call with force=True
                result = await service.delete_worktree(
                    workspace=workspace,
                    ticket_id=ticket.id,
                    actor_id="test-actor",
                    force=True,  # Force flag!
                    delete_branch=False,
                )

                # Assert: STILL returns False - force cannot override "still registered"
                assert result is False

                # Assert: rmtree NOT called
                mock_rmtree.assert_not_called()

            # Assert: cleaned_up_at remains NULL (even with force!)
            await db.refresh(workspace)
            assert workspace.cleaned_up_at is None

            # Assert: Event has force_used=True + still_registered=True
            events_result = await db.execute(
                select(TicketEvent)
                .where(TicketEvent.ticket_id == ticket.id)
                .where(
                    TicketEvent.event_type == EventType.WORKTREE_CLEANUP_FAILED.value
                )
            )
            events = events_result.scalars().all()
            assert len(events) == 1

            payload = json.loads(events[0].payload_json)
            assert payload.get("force_used") is True
            assert payload.get("still_registered") is True
            assert payload.get("cleanup_failed") is True
