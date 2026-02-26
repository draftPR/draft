"""Claude Code CLI executor adapter."""

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


@ExecutorRegistry.register("claude")
class ClaudeAdapter(ExecutorAdapter):
    """Built-in Claude Code CLI adapter."""

    def get_metadata(self) -> ExecutorMetadata:
        return ExecutorMetadata(
            name="claude",
            display_name="Claude Code",
            version="1.0.0",
            capabilities=[
                ExecutorCapability.STREAMING_OUTPUT,
                ExecutorCapability.YOLO_MODE,
                ExecutorCapability.MCP_SERVERS,
                ExecutorCapability.COST_TRACKING,
            ],
            config_schema={
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "default": "claude-sonnet-4-5",
                        "description": "Claude model to use"
                    },
                    "mcp_config": {
                        "type": "string",
                        "description": "Path to MCP config file"
                    }
                }
            },
            documentation_url="https://docs.anthropic.com/claude-code",
            author="Anthropic",
            license="Proprietary"
        )

    async def is_available(self) -> bool:
        """Check if claude CLI is installed."""
        return shutil.which("claude") is not None

    async def check_availability(self) -> dict:
        """Return detailed availability diagnostics."""
        cli_path = shutil.which("claude")
        issues = []
        version = None

        if not cli_path:
            issues.append("Claude Code CLI not found in PATH")
        else:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "claude", "--version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                version = stdout.decode().strip()
            except Exception:
                issues.append("Could not detect Claude Code version")

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
            "## Install Claude Code\n\n"
            "```bash\n"
            "npm install -g @anthropic-ai/claude-code\n"
            "```\n\n"
            "Then authenticate:\n"
            "```bash\n"
            "claude auth login\n"
            "```\n\n"
            "Docs: https://docs.anthropic.com/claude-code"
        )

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute using Claude Code CLI."""
        if not await self.is_available():
            raise ExecutorNotFoundError("Claude Code CLI not found. Install: npm install -g @anthropic-ai/claude-code")

        # Build command
        cmd = ["claude", "--print"]

        if request.yolo_mode:
            cmd.append("--dangerously-skip-permissions")

        # Add MCP servers if configured
        if request.mcp_servers:
            for server in request.mcp_servers:
                cmd.extend(["--mcp-server", server["name"]])

        # Add the prompt
        cmd.append(request.prompt)

        # Execute
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=request.working_directory,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **request.environment}
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=request.timeout_seconds
            )

            return ExecutionResult(
                exit_code=process.returncode,
                stdout=stdout.decode('utf-8', errors='replace'),
                stderr=stderr.decode('utf-8', errors='replace'),
                files_changed=[],  # TODO: Parse from output
                duration_seconds=0.0  # TODO: Track duration
            )

        except TimeoutError:
            process.kill()
            raise ExecutorTimeoutError(f"Claude execution timed out after {request.timeout_seconds}s")
        except Exception as e:
            raise ExecutorInvocationError(f"Claude execution failed: {str(e)}")

    async def stream_output(self, request: ExecutionRequest) -> AsyncIterator[str]:
        """Stream output in real-time."""
        if not await self.is_available():
            raise ExecutorNotFoundError("Claude Code CLI not found")

        cmd = ["claude", "--print"]
        if request.yolo_mode:
            cmd.append("--dangerously-skip-permissions")
        cmd.append(request.prompt)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=request.working_directory,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, **request.environment}
        )

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            yield line.decode('utf-8', errors='replace')

        await process.wait()
