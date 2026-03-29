"""Agent hooks service — generates Claude Code hooks for multi-agent coordination.

When agents run inside tmux sessions, hooks allow Draft to:
1. Track agent activity (PostToolUse events)
2. Detect agent completion (Stop events)
3. Nudge agents to check the message board (Notification events)

Inspired by coral's hook injection pattern: merge project hooks with
Draft-specific hooks so both work simultaneously.
"""

import json
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_hooks_config(
    api_base_url: str = "http://localhost:8000",
    board_id: str = "",
    ticket_id: str = "",
    session_id: str = "",
) -> dict:
    """Generate Claude Code hooks configuration for a team agent.

    These hooks are merged into the agent's settings.json at launch time.
    They enable:
    - Board message checking after each tool use
    - Status reporting on stop events
    """
    # Build the check command
    check_url = (
        f"{api_base_url}/boards/{board_id}/messages/check"
        f"?ticket_id={ticket_id}&session_id={session_id}"
    )
    check_cmd = (
        f'curl -s "{check_url}" '
        '| python3 -c "'
        "import json,sys; d=json.load(sys.stdin); "
        "n=d.get('unread',0); "
        "print(f'[Board] {n} unread message(s)') if n > 0 else None"
        '"'
    )

    # Build the stop notification payload
    stop_payload = json.dumps(
        {
            "ticket_id": ticket_id,
            "session_id": session_id,
            "sender_role": "system",
            "content": "Agent session ended",
        }
    )
    stop_cmd = (
        f'curl -s -X POST "{api_base_url}/boards/{board_id}/messages" '
        f'-H "Content-Type: application/json" '
        f"-d '{stop_payload}'"
    )

    return {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": check_cmd,
                        }
                    ],
                }
            ],
            "Stop": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": stop_cmd,
                        }
                    ],
                }
            ],
        }
    }


def merge_settings_with_hooks(
    existing_settings: dict,
    hooks_config: dict,
) -> dict:
    """Merge Draft hooks into existing Claude settings.

    Follows coral's pattern: hooks are deep-merged (combined per event,
    not replaced), so project hooks and Draft hooks both fire.
    """
    merged = dict(existing_settings)

    if "hooks" not in merged:
        merged["hooks"] = {}

    draft_hooks = hooks_config.get("hooks", {})
    for event_name, event_hooks in draft_hooks.items():
        if event_name not in merged["hooks"]:
            merged["hooks"][event_name] = []
        # Append Draft hooks after existing ones
        merged["hooks"][event_name].extend(event_hooks)

    return merged


def write_agent_settings(
    settings: dict,
    session_id: str,
) -> Path:
    """Write merged settings to a temp file for the agent to use.

    Returns path to the settings file, which can be passed to
    Claude CLI via --settings flag.
    """
    settings_path = Path(tempfile.gettempdir()) / f"draft_settings_{session_id}.json"
    settings_path.write_text(json.dumps(settings, indent=2))
    logger.debug("Wrote agent settings to %s", settings_path)
    return settings_path
