"""Boards resource."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import Board

if TYPE_CHECKING:
    from ._http import HttpClient


class BoardsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(self) -> list[Board]:
        data = self._http.get("/boards")
        items = data if isinstance(data, list) else data.get("boards", data.get("items", []))
        return [Board.model_validate(b) for b in items]

    def get(self, board_id: str) -> Board:
        return Board.model_validate(self._http.get(f"/boards/{board_id}"))

    def create(
        self,
        name: str,
        repo_root: str,
        description: str | None = None,
        base_branch: str | None = None,
    ) -> Board:
        body: dict = {"name": name, "repo_root": repo_root}
        if description:
            body["description"] = description
        if base_branch:
            body["base_branch"] = base_branch
        return Board.model_validate(self._http.post("/boards", json=body))

    def delete(self, board_id: str) -> None:
        self._http.delete(f"/boards/{board_id}")

    def kanban(self, board_id: str) -> dict:
        """Get kanban board view (tickets grouped by state)."""
        return self._http.get(f"/boards/{board_id}/board")
