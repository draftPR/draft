"""Qwen CLI adapter."""

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


@ExecutorRegistry.register("qwen")
class QwenAdapter(ExecutorAdapter):
    """Qwen Code CLI adapter for automated code changes."""

    def get_metadata(self) -> ExecutorMetadata:
        return ExecutorMetadata(
            name="qwen",
            display_name="Qwen Code CLI",
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
                        "default": "qwen-coder",
                        "description": "Qwen model to use",
                    }
                },
            },
            documentation_url="https://github.com/QwenLM/qwen-agent",
            author="Alibaba Cloud",
            license="Apache-2.0",
        )

    async def is_available(self) -> bool:
        """Check if qwen CLI is installed."""
        return shutil.which("qwen") is not None

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute using Qwen CLI."""
        if not await self.is_available():
            raise ExecutorNotFoundError(
                "Qwen CLI not found. Install from https://github.com/QwenLM/qwen-agent"
            )

        cmd = ["qwen", "--print"]

        if request.yolo_mode:
            cmd.append("--yolo")

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
                f"Qwen execution timed out after {request.timeout_seconds}s"
            ) from None
        except Exception as e:
            raise ExecutorInvocationError(f"Qwen execution failed: {e!s}") from e

    async def stream_output(self, request: ExecutionRequest) -> AsyncIterator[str]:
        """Stream output in real-time."""
        if not await self.is_available():
            raise ExecutorNotFoundError("Qwen CLI not found")

        cmd = ["qwen", "--print"]
        if request.yolo_mode:
            cmd.append("--yolo")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=request.working_directory,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, **request.environment},
        )

        process.stdin.write(request.prompt.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            yield line.decode("utf-8", errors="replace")

        await process.wait()
