"""Agent registry for supporting multiple AI coding agents.

This module provides a pluggable architecture for supporting multiple
AI coding agents (Claude, Amp, Codex, Gemini, etc.) with a unified interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List
import shutil
import logging

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """Supported AI coding agents."""
    CLAUDE = "claude"
    CURSOR = "cursor"
    AMP = "amp"
    CODEX = "codex"
    GEMINI = "gemini"
    AIDER = "aider"
    CONTINUE = "continue"


@dataclass
class AgentConfig:
    """Configuration for an AI agent."""
    agent_type: AgentType
    command: str  # Base command to run
    args: List[str] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)
    timeout: int = 600  # seconds
    supports_yolo: bool = False
    supports_session_resume: bool = False
    supports_mcp: bool = False
    cost_per_1k_input: Optional[float] = None
    cost_per_1k_output: Optional[float] = None


class AgentExecutor(ABC):
    """Abstract base class for agent executors."""
    
    def __init__(self, config: AgentConfig):
        self.config = config
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this agent is available on the system."""
        pass
    
    @abstractmethod
    def build_command(
        self,
        prompt: str,
        working_dir: Path,
        yolo_mode: bool = False,
        session_id: Optional[str] = None,
        **kwargs
    ) -> List[str]:
        """Build the command to execute the agent."""
        pass
    
    @abstractmethod
    def parse_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        """Parse agent output into structured format."""
        pass


class ClaudeExecutor(AgentExecutor):
    """Executor for Claude Code CLI."""
    
    def is_available(self) -> bool:
        return shutil.which("claude") is not None
    
    def build_command(
        self,
        prompt: str,
        working_dir: Path,
        yolo_mode: bool = False,
        session_id: Optional[str] = None,
        **kwargs
    ) -> List[str]:
        cmd = [self.config.command, "--print", "--output-format", "json"]
        
        if yolo_mode and self.config.supports_yolo:
            cmd.append("--dangerously-skip-permissions")
        
        if session_id and self.config.supports_session_resume:
            cmd.extend(["--resume", session_id])
        
        cmd.extend(["--prompt", prompt])
        return cmd
    
    def parse_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        # Parse Claude's JSON output format
        import json
        try:
            return {"success": True, "data": json.loads(stdout)}
        except json.JSONDecodeError:
            return {"success": False, "raw_output": stdout, "error": stderr}


class AmpExecutor(AgentExecutor):
    """Executor for Amp CLI."""
    
    def is_available(self) -> bool:
        return shutil.which("amp") is not None
    
    def build_command(
        self,
        prompt: str,
        working_dir: Path,
        yolo_mode: bool = False,
        session_id: Optional[str] = None,
        **kwargs
    ) -> List[str]:
        cmd = [self.config.command, "run"]
        
        if session_id:
            cmd.extend(["--thread", session_id])
        
        cmd.extend(["--message", prompt])
        return cmd
    
    def parse_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        return {"success": True, "raw_output": stdout}


class CursorExecutor(AgentExecutor):
    """Executor for Cursor Agent CLI."""
    
    def is_available(self) -> bool:
        # Check common paths for cursor-agent
        paths = [
            shutil.which("cursor-agent"),
            Path.home() / ".local/bin/cursor-agent",
            Path("/usr/local/bin/cursor-agent"),
        ]
        return any(p and (isinstance(p, str) or p.exists()) for p in paths)
    
    def build_command(
        self,
        prompt: str,
        working_dir: Path,
        yolo_mode: bool = False,
        session_id: Optional[str] = None,
        **kwargs
    ) -> List[str]:
        cmd = [self.config.command]
        cmd.extend(["--prompt", prompt])
        return cmd
    
    def parse_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        return {"success": True, "raw_output": stdout, "interactive": True}


class AiderExecutor(AgentExecutor):
    """Executor for Aider CLI (open-source coding assistant)."""
    
    def is_available(self) -> bool:
        return shutil.which("aider") is not None
    
    def build_command(
        self,
        prompt: str,
        working_dir: Path,
        yolo_mode: bool = False,
        session_id: Optional[str] = None,
        **kwargs
    ) -> List[str]:
        cmd = [self.config.command, "--yes", "--no-auto-commits"]
        
        if yolo_mode:
            cmd.append("--auto-commits")
        
        cmd.extend(["--message", prompt])
        return cmd
    
    def parse_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        return {"success": True, "raw_output": stdout}


class GeminiExecutor(AgentExecutor):
    """Executor for Gemini CLI."""
    
    def is_available(self) -> bool:
        return shutil.which("gemini") is not None
    
    def build_command(
        self,
        prompt: str,
        working_dir: Path,
        yolo_mode: bool = False,
        session_id: Optional[str] = None,
        **kwargs
    ) -> List[str]:
        cmd = [self.config.command]
        
        if yolo_mode:
            cmd.extend(["--sandbox=false"])
        
        cmd.extend(["--prompt", prompt])
        return cmd
    
    def parse_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        return {"success": True, "raw_output": stdout}


class CodexExecutor(AgentExecutor):
    """Executor for OpenAI Codex CLI."""
    
    def is_available(self) -> bool:
        return shutil.which("codex") is not None
    
    def build_command(
        self,
        prompt: str,
        working_dir: Path,
        yolo_mode: bool = False,
        session_id: Optional[str] = None,
        **kwargs
    ) -> List[str]:
        cmd = [self.config.command]
        
        if yolo_mode:
            cmd.extend(["--approval-mode", "full-auto"])
        
        cmd.extend([prompt])
        return cmd
    
    def parse_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        return {"success": True, "raw_output": stdout}


# Agent registry with default configurations
AGENT_REGISTRY: Dict[AgentType, AgentConfig] = {
    AgentType.CLAUDE: AgentConfig(
        agent_type=AgentType.CLAUDE,
        command="claude",
        supports_yolo=True,
        supports_session_resume=True,
        supports_mcp=True,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
    ),
    AgentType.CURSOR: AgentConfig(
        agent_type=AgentType.CURSOR,
        command="cursor-agent",
        supports_yolo=False,
        supports_session_resume=False,
    ),
    AgentType.AMP: AgentConfig(
        agent_type=AgentType.AMP,
        command="amp",
        supports_yolo=False,
        supports_session_resume=True,
    ),
    AgentType.AIDER: AgentConfig(
        agent_type=AgentType.AIDER,
        command="aider",
        supports_yolo=True,
        supports_session_resume=False,
        cost_per_1k_input=0.003,  # Depends on model used
        cost_per_1k_output=0.015,
    ),
    AgentType.GEMINI: AgentConfig(
        agent_type=AgentType.GEMINI,
        command="gemini",
        supports_yolo=True,
        supports_session_resume=False,
        supports_mcp=False,
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.002,
    ),
    AgentType.CODEX: AgentConfig(
        agent_type=AgentType.CODEX,
        command="codex",
        supports_yolo=True,
        supports_session_resume=False,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03,
    ),
}

EXECUTOR_CLASSES: Dict[AgentType, type] = {
    AgentType.CLAUDE: ClaudeExecutor,
    AgentType.CURSOR: CursorExecutor,
    AgentType.AMP: AmpExecutor,
    AgentType.AIDER: AiderExecutor,
    AgentType.GEMINI: GeminiExecutor,
    AgentType.CODEX: CodexExecutor,
}


class AgentRegistry:
    """Registry for managing multiple AI coding agents."""
    
    def __init__(self):
        self._executors: Dict[AgentType, AgentExecutor] = {}
    
    def get_executor(self, agent_type: AgentType) -> Optional[AgentExecutor]:
        """Get an executor for the specified agent type."""
        if agent_type not in self._executors:
            config = AGENT_REGISTRY.get(agent_type)
            executor_class = EXECUTOR_CLASSES.get(agent_type)
            if config and executor_class:
                self._executors[agent_type] = executor_class(config)
        
        return self._executors.get(agent_type)
    
    def get_available_agents(self) -> List[AgentType]:
        """Get list of agents available on this system."""
        available = []
        for agent_type in AgentType:
            executor = self.get_executor(agent_type)
            if executor and executor.is_available():
                available.append(agent_type)
        return available
    
    def get_agent_info(self, agent_type: AgentType) -> Optional[Dict[str, Any]]:
        """Get information about an agent."""
        config = AGENT_REGISTRY.get(agent_type)
        if not config:
            return None
        
        executor = self.get_executor(agent_type)
        return {
            "type": agent_type.value,
            "available": executor.is_available() if executor else False,
            "supports_yolo": config.supports_yolo,
            "supports_session_resume": config.supports_session_resume,
            "supports_mcp": config.supports_mcp,
            "cost_per_1k_input": config.cost_per_1k_input,
            "cost_per_1k_output": config.cost_per_1k_output,
        }


# Global registry instance
agent_registry = AgentRegistry()
