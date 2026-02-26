"""Google Gemini CLI adapter."""

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


@ExecutorRegistry.register("gemini")
class GeminiAdapter(ExecutorAdapter):
    """Google Gemini CLI adapter."""

    def get_metadata(self) -> ExecutorMetadata:
        return ExecutorMetadata(
            name="gemini",
            display_name="Google Gemini CLI",
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
                        "default": "gemini-2.0-flash",
                        "enum": ["gemini-2.0-flash", "gemini-pro", "gemini-ultra"],
                        "description": "Gemini model to use"
                    },
                    "sandbox": {
                        "type": "string",
                        "enum": ["docker", "local"],
                        "default": "docker",
                        "description": "Execution sandbox environment"
                    }
                }
            },
            documentation_url="https://github.com/google/gemini-cli",
            author="Google",
            license="Apache-2.0"
        )

    async def is_available(self) -> bool:
        """Check if gemini CLI is installed."""
        return shutil.which("gemini") is not None

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute using Gemini CLI."""
        if not await self.is_available():
            raise ExecutorNotFoundError("Gemini CLI not found. Install from https://github.com/google/gemini-cli")

        # Build command
        cmd = ["gemini", "--print"]

        if request.yolo_mode:
            cmd.append("--yolo")

        # Add model if specified
        model = request.config.get("model", "gemini-2.0-flash")
        cmd.extend(["--model", model])

        # Add the prompt
        cmd.extend(["--prompt", request.prompt])

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

        except TimeoutError:
            process.kill()
            raise ExecutorTimeoutError(f"Gemini execution timed out after {request.timeout_seconds}s")
        except Exception as e:
            raise ExecutorInvocationError(f"Gemini execution failed: {str(e)}")

    async def stream_output(self, request: ExecutionRequest) -> AsyncIterator[str]:
        """Stream output in real-time."""
        if not await self.is_available():
            raise ExecutorNotFoundError("Gemini CLI not found")

        cmd = ["gemini", "--print"]
        if request.yolo_mode:
            cmd.append("--yolo")
        cmd.extend(["--prompt", request.prompt])

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
