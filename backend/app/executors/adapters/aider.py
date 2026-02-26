"""Aider AI coding assistant adapter."""

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


@ExecutorRegistry.register("aider")
class AiderAdapter(ExecutorAdapter):
    """Aider AI coding assistant adapter."""

    def get_metadata(self) -> ExecutorMetadata:
        return ExecutorMetadata(
            name="aider",
            display_name="Aider",
            version="1.0.0",
            capabilities=[
                ExecutorCapability.STREAMING_OUTPUT,
                ExecutorCapability.SESSION_RESUME,
                ExecutorCapability.COST_TRACKING,
            ],
            config_schema={
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "default": "gpt-4",
                        "description": "LLM model to use"
                    },
                    "edit_format": {
                        "type": "string",
                        "enum": ["diff", "whole"],
                        "default": "diff",
                        "description": "Edit format (diff or whole file)"
                    },
                    "auto_commits": {
                        "type": "boolean",
                        "default": True,
                        "description": "Auto-commit changes"
                    }
                }
            },
            documentation_url="https://aider.chat/docs/",
            author="Aider Project",
            license="Apache-2.0"
        )

    async def is_available(self) -> bool:
        """Check if aider is installed."""
        return shutil.which("aider") is not None

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute using Aider."""
        if not await self.is_available():
            raise ExecutorNotFoundError("Aider not found. Install: pip install aider-chat")

        # Build command
        cmd = [
            "aider",
            "--yes",                    # Auto-confirm
            "--no-git",                 # We handle git ourselves
            "--message", request.prompt,
        ]

        # Add session resume if provided
        if request.session_id:
            cmd.extend(["--restore-chat-history", request.session_id])

        # Add model config
        model = request.config.get("model", "gpt-4")
        cmd.extend(["--model", model])

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
                files_changed=self._parse_changed_files(stdout.decode()),
                duration_seconds=0.0
            )

        except TimeoutError:
            process.kill()
            raise ExecutorTimeoutError(f"Aider execution timed out after {request.timeout_seconds}s")
        except Exception as e:
            raise ExecutorInvocationError(f"Aider execution failed: {str(e)}")

    async def stream_output(self, request: ExecutionRequest) -> AsyncIterator[str]:
        """Stream output in real-time."""
        if not await self.is_available():
            raise ExecutorNotFoundError("Aider not found")

        cmd = ["aider", "--yes", "--no-git", "--message", request.prompt]

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

    def _parse_changed_files(self, output: str) -> list[str]:
        """Parse changed files from Aider output.

        Aider logs lines like: "Modified path/to/file.py"
        """
        files = []
        for line in output.split('\n'):
            if line.strip().startswith("Modified "):
                file_path = line.strip()[9:].strip()  # Remove "Modified "
                files.append(file_path)
        return files
