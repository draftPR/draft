"""GitHub Copilot CLI adapter."""

import asyncio
import shutil
import os
from typing import AsyncIterator

from app.executors.spec import (
    ExecutorAdapter,
    ExecutorMetadata,
    ExecutorCapability,
    ExecutionRequest,
    ExecutionResult,
    ExecutorNotFoundError,
    ExecutorInvocationError,
    ExecutorTimeoutError
)
from app.executors.registry import ExecutorRegistry


@ExecutorRegistry.register("copilot")
class CopilotAdapter(ExecutorAdapter):
    """GitHub Copilot CLI adapter."""

    def get_metadata(self) -> ExecutorMetadata:
        return ExecutorMetadata(
            name="copilot",
            display_name="GitHub Copilot CLI",
            version="1.0.0",
            capabilities=[
                ExecutorCapability.STREAMING_OUTPUT,
            ],
            config_schema={
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "default": "gpt-4",
                        "description": "OpenAI model used by Copilot"
                    }
                }
            },
            documentation_url="https://githubnext.com/projects/copilot-cli/",
            author="GitHub",
            license="Proprietary"
        )

    async def is_available(self) -> bool:
        """Check if copilot CLI is installed."""
        # GitHub Copilot CLI is accessed via `gh copilot` or dedicated `copilot` command
        has_gh = shutil.which("gh") is not None
        has_copilot = shutil.which("copilot") is not None

        if has_gh:
            # Check if copilot extension is installed
            try:
                process = await asyncio.create_subprocess_exec(
                    "gh", "extension", "list",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await process.communicate()
                return b"copilot" in stdout.lower()
            except:
                return False

        return has_copilot

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute using GitHub Copilot CLI."""
        if not await self.is_available():
            raise ExecutorNotFoundError(
                "GitHub Copilot CLI not found. Install: gh extension install github/gh-copilot"
            )

        # Determine command structure
        if shutil.which("gh"):
            cmd = ["gh", "copilot", "suggest"]
        else:
            cmd = ["copilot", "suggest"]

        # Add the prompt
        cmd.append(request.prompt)

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
                duration_seconds=0.0
            )

        except asyncio.TimeoutError:
            process.kill()
            raise ExecutorTimeoutError(f"Copilot execution timed out after {request.timeout_seconds}s")
        except Exception as e:
            raise ExecutorInvocationError(f"Copilot execution failed: {str(e)}")

    async def stream_output(self, request: ExecutionRequest) -> AsyncIterator[str]:
        """Stream output in real-time."""
        if not await self.is_available():
            raise ExecutorNotFoundError("GitHub Copilot CLI not found")

        if shutil.which("gh"):
            cmd = ["gh", "copilot", "suggest", request.prompt]
        else:
            cmd = ["copilot", "suggest", request.prompt]

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
