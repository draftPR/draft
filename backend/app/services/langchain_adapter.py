"""LangChain adapter to bridge existing LLMService with LangChain's BaseLLM interface.

This adapter allows UDAR agent to use Smart Kanban's existing LLM infrastructure
(LiteLLM with multi-provider support) without refactoring.
"""

from typing import Any, Optional

from langchain_core.language_models.llms import LLM
from langchain_core.callbacks.manager import CallbackManagerForLLMRun

from app.services.llm_service import LLMService


class LangChainLLMAdapter(LLM):
    """Adapter to use existing LLMService with LangChain.

    This allows UDAR agent to leverage Smart Kanban's existing LLM infrastructure
    while using LangGraph's state machine framework.

    Example:
        llm_service = LLMService()
        adapter = LangChainLLMAdapter(llm_service=llm_service)
        response = adapter.invoke("What tickets are needed?")
    """

    llm_service: LLMService
    model: str = "claude-opus-4-6"  # Default model, can be overridden
    max_tokens: int = 2000
    temperature: float = 0.0  # Deterministic by default

    class Config:
        """Pydantic configuration."""
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        """Return identifier for this LLM type."""
        return "smart_kanban_llm"

    def _call(
        self,
        prompt: str,
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Call the LLM with a prompt and return the response.

        Args:
            prompt: The prompt to send to the LLM
            stop: Optional list of stop sequences
            run_manager: Optional callback manager
            **kwargs: Additional arguments (temperature, max_tokens, etc.)

        Returns:
            The LLM's response as a string
        """
        # Extract parameters with fallbacks
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        temperature = kwargs.get("temperature", self.temperature)

        # Call existing LLMService
        response = self.llm_service.call_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
        )

        # Track token usage if callback manager provided
        if run_manager:
            # LangChain can track tokens for monitoring
            run_manager.on_llm_end(response)

        return response.content

    async def _acall(
        self,
        prompt: str,
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Async version of _call.

        Args:
            prompt: The prompt to send to the LLM
            stop: Optional list of stop sequences
            run_manager: Optional callback manager
            **kwargs: Additional arguments

        Returns:
            The LLM's response as a string
        """
        # Extract parameters with fallbacks
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        temperature = kwargs.get("temperature", self.temperature)

        # Call existing LLMService (async)
        response = await self.llm_service.call_completion_async(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
        )

        # Track token usage if callback manager provided
        if run_manager:
            run_manager.on_llm_end(response)

        return response.content

    @property
    def _identifying_params(self) -> dict[str, Any]:
        """Return identifying parameters for this LLM."""
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
