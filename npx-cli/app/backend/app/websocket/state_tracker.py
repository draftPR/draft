"""Board state tracker for computing JSON patches.

Tracks the last-known board state per connection and computes RFC 6902
JSON patches between states, enabling incremental updates over WebSocket.

Protocol:
  1. On connect: send full snapshot {"type": "snapshot", "data": ..., "seq": 0}
  2. On change:  send patch     {"type": "patch", "ops": [...], "seq": N}
  3. On gap:     client sends   {"type": "resync"} → server resends snapshot
"""

import copy
import logging
from typing import Any

import jsonpatch

logger = logging.getLogger(__name__)


class BoardStateTracker:
    """Tracks board state and computes JSON patches for incremental updates.

    One tracker per board; stores the last-known state and a sequence counter.
    Thread-safe for single-event-loop usage (async context).
    """

    def __init__(self) -> None:
        self._state: dict[str, Any] | None = None
        self._seq: int = 0

    @property
    def seq(self) -> int:
        return self._seq

    @property
    def has_state(self) -> bool:
        return self._state is not None

    def set_state(self, state: dict[str, Any]) -> None:
        """Set the current board state (used for initial snapshot)."""
        self._state = copy.deepcopy(state)

    def get_snapshot_message(self, state: dict[str, Any]) -> dict[str, Any]:
        """Build a snapshot message and update internal state.

        Args:
            state: Full board state dict.

        Returns:
            Message dict: {"type": "snapshot", "data": ..., "seq": 0}
        """
        self._state = copy.deepcopy(state)
        self._seq = 0
        return {
            "type": "snapshot",
            "data": state,
            "seq": self._seq,
        }

    def compute_patch(self, new_state: dict[str, Any]) -> dict[str, Any] | None:
        """Compute a JSON patch between the stored state and new_state.

        If the patch is empty (no changes), returns None.

        Args:
            new_state: The new board state dict.

        Returns:
            Patch message dict or None if no changes:
            {"type": "patch", "ops": [...], "seq": N}
        """
        if self._state is None:
            # No previous state → send snapshot instead
            return self.get_snapshot_message(new_state)

        try:
            patch = jsonpatch.make_patch(self._state, new_state)
            ops = patch.patch

            if not ops:
                return None

            self._seq += 1
            self._state = copy.deepcopy(new_state)

            return {
                "type": "patch",
                "ops": ops,
                "seq": self._seq,
            }

        except Exception as e:
            logger.warning(
                f"Failed to compute JSON patch: {e}, falling back to snapshot"
            )
            return self.get_snapshot_message(new_state)


# Per-board trackers keyed by board_id
_trackers: dict[str, BoardStateTracker] = {}


def get_tracker(board_id: str) -> BoardStateTracker:
    """Get or create a state tracker for a board."""
    if board_id not in _trackers:
        _trackers[board_id] = BoardStateTracker()
    return _trackers[board_id]


def remove_tracker(board_id: str) -> None:
    """Remove a tracker when no more connections exist for a board."""
    _trackers.pop(board_id, None)
