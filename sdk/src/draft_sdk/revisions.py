"""Revisions resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import Revision, ReviewComment, ReviewSummary, RevisionDiff

if TYPE_CHECKING:
    from ._http import HttpClient


class RevisionsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(self, ticket_id: str) -> list[Revision]:
        data = self._http.get(f"/tickets/{ticket_id}/revisions")
        items = data if isinstance(data, list) else data.get("revisions", data.get("items", []))
        return [Revision.model_validate(r) for r in items]

    def get(self, revision_id: str) -> Revision:
        return Revision.model_validate(self._http.get(f"/revisions/{revision_id}"))

    def get_diff(self, revision_id: str) -> RevisionDiff:
        """Get combined stat + patch diff."""
        return RevisionDiff.model_validate(self._http.get(f"/revisions/{revision_id}/diff"))

    def get_diff_summary(self, revision_id: str) -> dict:
        """Get file list without patch content."""
        return self._http.get(f"/revisions/{revision_id}/diff/summary")

    def get_diff_patch(self, revision_id: str) -> str:
        """Get full code diff as plain text."""
        return self._http.get_text(f"/revisions/{revision_id}/diff/patch")

    def review(
        self,
        revision_id: str,
        decision: str,
        summary: str = "",
        auto_run_fix: bool = True,
        create_pr: bool = False,
    ) -> ReviewSummary:
        """Submit a review decision: 'approved' or 'changes_requested'."""
        body: dict[str, Any] = {"decision": decision}
        if summary:
            body["summary"] = summary
        if auto_run_fix:
            body["auto_run_fix"] = True
        if create_pr:
            body["create_pr"] = True
        return ReviewSummary.model_validate(
            self._http.post(f"/revisions/{revision_id}/review", json=body)
        )

    def get_comments(self, revision_id: str) -> list[ReviewComment]:
        data = self._http.get(f"/revisions/{revision_id}/comments")
        items = data if isinstance(data, list) else data.get("comments", data.get("items", []))
        return [ReviewComment.model_validate(c) for c in items]

    def add_comment(
        self,
        revision_id: str,
        file_path: str,
        line_number: int,
        content: str,
    ) -> ReviewComment:
        body = {
            "file_path": file_path,
            "line_number": line_number,
            "content": content,
        }
        return ReviewComment.model_validate(
            self._http.post(f"/revisions/{revision_id}/comments", json=body)
        )
