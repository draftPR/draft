"""OpenAI Codex CLI adapter."""

import asyncio
import os
import shutil
from collections.abc import AsyncIterator

from app.executors.registry import ExecutorRegistry
from app.executors.spec import (
    ExecutionRequest,
    ExecutionResult,
    ExecutorAdapter,
    ExecutorCapability,
    ExecutorInvocationError,
    ExecutorMetadata,
    ExecutorNotFoundError,
    ExecutorTimeoutError,
)


@ExecutorRegistry.register("codex")
class CodexAdapter(ExecutorAdapter):
    """OpenAI Codex CLI adapter."""

    def get_metadata(self) -> ExecutorMetadata:
        return ExecutorMetadata(
            name="codex",
            display_name="OpenAI Codex CLI",
            version="1.0.0",
            capabilities=[
                ExecutorCapability.STREAMING_OUTPUT,
                ExecutorCapability.YOLO_MODE,
            ],
            config_schema={
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "default": "o3",
                        "description": "OpenAI model used by Codex",
                    }
                },
            },
            documentation_url="https://github.com/openai/codex",
            author="OpenAI",
            license="Apache-2.0",
        )

    async def is_available(self) -> bool:
        """Check if codex CLI is installed."""
        return shutil.which("codex") is not None

    async def check_availability(self) -> dict:
        """Return detailed availability diagnostics."""
        cli_path = shutil.which("codex")
        issues = []
        version = None

        if not cli_path:
            issues.append("Codex CLI not found in PATH")
        else:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "codex",
                    "--version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                version = stdout.decode().strip()
            except Exception:
                issues.append("Could not detect Codex CLI version")

        return {
            "available": cli_path is not None,
            "cli_found": cli_path is not None,
            "cli_path": cli_path,
            "version": version,
            "issues": issues,
            "setup_instructions": self.get_setup_instructions(),
        }

    def get_setup_instructions(self) -> str:
        return (
            "## Install OpenAI Codex CLI\n\n"
            "```bash\n"
            "npm install -g @openai/codex\n"
            "```\n\n"
            "Then authenticate:\n"
            "```bash\n"
            "export OPENAI_API_KEY=your-key\n"
            "```\n\n"
            "Docs: https://github.com/openai/codex"
        )

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute using Codex CLI."""
        if not await self.is_available():
            raise ExecutorNotFoundError(
                "Codex CLI not found. Install from https://github.com/openai/codex"
            )

        cmd = ["codex", "--print", "--auto-edit"]

        if request.yolo_mode:
            cmd.append("--full-auto")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=request.working_directory,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **request.environment},
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=request.prompt.encode("utf-8")),
                timeout=request.timeout_seconds,
            )

            return ExecutionResult(
                exit_code=process.returncode,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                duration_seconds=0.0,
            )

        except TimeoutError:
            process.kill()
            raise ExecutorTimeoutError(
                f"Codex execution timed out after {request.timeout_seconds}s"
            ) from None
        except Exception as e:
            raise ExecutorInvocationError(f"Codex execution failed: {e!s}") from e

    async def stream_output(self, request: ExecutionRequest) -> AsyncIterator[str]:
        """Stream output in real-time."""
        if not await self.is_available():
            raise ExecutorNotFoundError("Codex CLI not found")

        cmd = ["codex", "--print", "--auto-edit"]
        if request.yolo_mode:
            cmd.append("--full-auto")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=request.working_directory,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, **request.environment},
        )

        # Send prompt via stdin then close
        process.stdin.write(request.prompt.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            yield line.decode("utf-8", errors="replace")

        await process.wait()
