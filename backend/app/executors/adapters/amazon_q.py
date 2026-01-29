"""Amazon Q Developer adapter."""

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


@ExecutorRegistry.register("amazon-q")
class AmazonQAdapter(ExecutorAdapter):
    """Amazon Q Developer adapter."""

    def get_metadata(self) -> ExecutorMetadata:
        return ExecutorMetadata(
            name="amazon-q",
            display_name="Amazon Q Developer",
            version="1.0.0",
            capabilities=[
                ExecutorCapability.STREAMING_OUTPUT,
            ],
            config_schema={
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "string",
                        "description": "AWS profile to use"
                    },
                    "model": {
                        "type": "string",
                        "default": "q-developer",
                        "description": "Model variant to use"
                    }
                }
            },
            documentation_url="https://aws.amazon.com/q/developer/",
            author="AWS",
            license="Proprietary"
        )

    async def is_available(self) -> bool:
        """Check if Q CLI is installed."""
        # Amazon Q can be accessed via `q` or `amazon-q` command
        return shutil.which("q") is not None or shutil.which("amazon-q") is not None

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute using Amazon Q Developer."""
        if not await self.is_available():
            raise ExecutorNotFoundError("Amazon Q not found. Install AWS CLI and Q extension.")

        # Determine which command is available
        cmd_name = "q" if shutil.which("q") else "amazon-q"

        # Build command
        cmd = [cmd_name, "chat"]

        if request.yolo_mode:
            cmd.append("--trust-all-tools")

        # Add AWS profile if specified
        profile = request.config.get("profile")
        if profile:
            cmd.extend(["--profile", profile])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=request.working_directory,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **request.environment}
            )

            # Amazon Q uses stdin for the prompt
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=request.prompt.encode()),
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
            raise ExecutorTimeoutError(f"Amazon Q execution timed out after {request.timeout_seconds}s")
        except Exception as e:
            raise ExecutorInvocationError(f"Amazon Q execution failed: {str(e)}")
