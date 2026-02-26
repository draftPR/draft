"""Goose AI assistant adapter."""

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


@ExecutorRegistry.register("goose")
class GooseAdapter(ExecutorAdapter):
    """Goose AI assistant adapter."""

    def get_metadata(self) -> ExecutorMetadata:
        return ExecutorMetadata(
            name="goose",
            display_name="Goose",
            version="1.0.0",
            capabilities=[
                ExecutorCapability.STREAMING_OUTPUT,
                ExecutorCapability.SESSION_RESUME,
            ],
            config_schema={
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "default": "gpt-4",
                        "description": "LLM model to use"
                    },
                    "profile": {
                        "type": "string",
                        "description": "Goose profile to use"
                    }
                }
            },
            documentation_url="https://github.com/square/goose",
            author="Square",
            license="Apache-2.0"
        )

    async def is_available(self) -> bool:
        """Check if goose is installed."""
        return shutil.which("goose") is not None

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute using Goose."""
        if not await self.is_available():
            raise ExecutorNotFoundError("Goose not found. Install: pip install goose-ai")

        # Build command
        cmd = ["goose", "run"]

        # Add session if provided
        if request.session_id:
            cmd.extend(["--session", request.session_id])

        # Add profile if specified
        profile = request.config.get("profile")
        if profile:
            cmd.extend(["--profile", profile])

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
                session_id=request.session_id,  # Can be resumed
                duration_seconds=0.0
            )

        except TimeoutError:
            process.kill()
            raise ExecutorTimeoutError(f"Goose execution timed out after {request.timeout_seconds}s")
        except Exception as e:
            raise ExecutorInvocationError(f"Goose execution failed: {str(e)}")

    async def stream_output(self, request: ExecutionRequest) -> AsyncIterator[str]:
        """Stream output in real-time."""
        if not await self.is_available():
            raise ExecutorNotFoundError("Goose not found")

        cmd = ["goose", "run", request.prompt]
        if request.session_id:
            cmd.extend(["--session", request.session_id])

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
