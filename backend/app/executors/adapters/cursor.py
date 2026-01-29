"""Cursor AI IDE adapter."""

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


@ExecutorRegistry.register("cursor")
class CursorAdapter(ExecutorAdapter):
    """Cursor AI IDE adapter."""

    def get_metadata(self) -> ExecutorMetadata:
        return ExecutorMetadata(
            name="cursor",
            display_name="Cursor",
            version="1.0.0",
            capabilities=[
                ExecutorCapability.INTERACTIVE,  # Opens IDE
                ExecutorCapability.MCP_SERVERS,
            ],
            config_schema={
                "type": "object",
                "properties": {
                    "auto_apply": {
                        "type": "boolean",
                        "default": False,
                        "description": "Auto-apply suggestions without confirmation"
                    }
                }
            },
            documentation_url="https://cursor.sh/",
            author="Cursor",
            license="Proprietary"
        )

    async def is_available(self) -> bool:
        """Check if cursor is installed."""
        return shutil.which("cursor") is not None

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute using Cursor.

        Note: Cursor is primarily interactive, so this opens the IDE
        and requires human interaction to complete the task.
        """
        if not await self.is_available():
            raise ExecutorNotFoundError("Cursor not found. Install from https://cursor.sh/")

        # Build command - opens Cursor in the working directory
        cmd = ["cursor", request.working_directory]

        # Note: Cursor doesn't have a headless mode for autonomous execution
        # This will open the IDE and the human must complete the work

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **request.environment}
            )

            # For Cursor, we just launch it and return immediately
            # The actual work happens interactively

            return ExecutionResult(
                exit_code=0,
                stdout=f"Opened Cursor in {request.working_directory}\\nPrompt: {request.prompt}",
                stderr="",
                metadata={
                    "interactive": True,
                    "requires_human": True
                }
            )

        except Exception as e:
            raise ExecutorInvocationError(f"Cursor execution failed: {str(e)}")
