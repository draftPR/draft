"""Executor CLI command shapes (codex exec, model/extra_flags overrides)."""

from pathlib import Path

from app.services.executor_service import ExecutorInfo, ExecutorType


def _info(executor_type: ExecutorType) -> ExecutorInfo:
    return ExecutorInfo(executor_type=executor_type, command=executor_type.value, path="/x")


def test_codex_uses_exec_subcommand_and_stdin(tmp_path: Path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("do the thing")
    cmd, stdin = _info(ExecutorType.CODEX).get_apply_command(prompt, tmp_path)

    assert cmd[:2] == ["codex", "exec"]
    assert "-C" in cmd and str(tmp_path) in cmd
    assert "--print" not in cmd and "--auto-edit" not in cmd
    assert cmd[-2:] == ["-s", "workspace-write"]
    assert stdin == "do the thing"


def test_codex_yolo_bypasses_sandbox(tmp_path: Path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("x")
    cmd, _ = _info(ExecutorType.CODEX).get_apply_command(prompt, tmp_path, yolo_mode=True)
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    assert "-s" not in cmd


def test_model_and_extra_flags_appended_per_executor(tmp_path: Path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("x")

    claude_cmd, _ = _info(ExecutorType.CLAUDE).get_apply_command(
        prompt, tmp_path, model="claude-sonnet-5", extra_flags=["--verbose"]
    )
    assert claude_cmd[-3:] == ["--model", "claude-sonnet-5", "--verbose"]

    codex_cmd, _ = _info(ExecutorType.CODEX).get_apply_command(
        prompt, tmp_path, model="gpt-5.4-mini"
    )
    assert codex_cmd[-2:] == ["-m", "gpt-5.4-mini"]

    # "auto" and None mean no override
    auto_cmd, _ = _info(ExecutorType.CLAUDE).get_apply_command(prompt, tmp_path, model="auto")
    assert "--model" not in auto_cmd
