"""Cline AI assistant adapter."""

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


@ExecutorRegistry.register("cline")
class ClineAdapter(ExecutorAdapter):
    """Cline AI assistant adapter (VS Code extension CLI)."""

    def get_metadata(self) -> ExecutorMetadata:
        return ExecutorMetadata(
            name="cline",
            display_name="Cline",
            version="1.0.0",
            capabilities=[
                ExecutorCapability.STREAMING_OUTPUT,
            ],
            config_schema={
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "default": "claude-3-5-sonnet-20241022",
                        "description": "LLM model to use"
                    },
                    "api_provider": {
                        "type": "string",
                        "enum": ["anthropic", "openai", "bedrock"],
                        "default": "anthropic",
                        "description": "API provider"
                    }
                }
            },
            documentation_url="https://github.com/cline/cline",
            author="Cline",
            license="Apache-2.0"
        )

    async def is_available(self) -> bool:
        """Check if cline CLI is installed."""
        return shutil.which("cline") is not None

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute using Cline."""
        if not await self.is_available():
            raise ExecutorNotFoundError("Cline not found. Install the Cline VS Code extension with CLI support.")

        # Build command
        cmd = ["cline", "execute"]

        # Add model and provider
        model = request.config.get("model", "claude-3-5-sonnet-20241022")
        provider = request.config.get("api_provider", "anthropic")

        cmd.extend(["--model", model])
        cmd.extend(["--provider", provider])

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
            raise ExecutorTimeoutError(f"Cline execution timed out after {request.timeout_seconds}s")
        except Exception as e:
            raise ExecutorInvocationError(f"Cline execution failed: {str(e)}")

    async def stream_output(self, request: ExecutionRequest) -> AsyncIterator[str]:
        """Stream output in real-time."""
        if not await self.is_available():
            raise ExecutorNotFoundError("Cline not found")

        cmd = ["cline", "execute", "--prompt", request.prompt]

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
