"""Direct LLM provider API clients with error handling."""

import json
import logging
import os
from typing import Any

import httpx

from app.exceptions import ConfigurationError, LLMAPIError

logger = logging.getLogger(__name__)

# Provider constants
LLM_PROVIDER_OPENROUTER = "openrouter"
LLM_PROVIDER_ANTHROPIC = "anthropic"
LLM_PROVIDER_OPENAI = "openai"

# Default model per provider
DEFAULT_MODELS = {
    LLM_PROVIDER_OPENROUTER: "anthropic/claude-3.5-sonnet",
    LLM_PROVIDER_ANTHROPIC: "claude-3-5-sonnet-20241022",
    LLM_PROVIDER_OPENAI: "gpt-4o",
}

TIMEOUT_SECONDS = 90


def get_llm_provider() -> str:
    """Get configured LLM provider from environment."""
    return os.getenv("LLM_PROVIDER", LLM_PROVIDER_OPENROUTER)


def get_api_key(provider: str) -> str | None:
    """Get API key for the specified provider."""
    key_map = {
        LLM_PROVIDER_OPENROUTER: "OPENROUTER_API_KEY",
        LLM_PROVIDER_ANTHROPIC: "ANTHROPIC_API_KEY",
        LLM_PROVIDER_OPENAI: "OPENAI_API_KEY",
    }
    env_var = key_map.get(provider)
    if not env_var:
        return None
    return os.getenv(env_var)


async def call_openrouter(prompt: str, api_key: str, model: str | None = None) -> str:
    """
    Call OpenRouter API.
    
    Args:
        prompt: The prompt to send to the LLM.
        api_key: OpenRouter API key.
        model: Model to use (defaults to claude-3.5-sonnet via OpenRouter).
    
    Returns:
        Response text from the LLM.
    
    Raises:
        LLMAPIError: If the API call fails.
    """
    model = model or DEFAULT_MODELS[LLM_PROVIDER_OPENROUTER]
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code != 200:
                error_detail = _extract_error_message(response)
                raise LLMAPIError(
                    f"OpenRouter API error: {error_detail}",
                    provider=LLM_PROVIDER_OPENROUTER,
                    status_code=response.status_code,
                )
            
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if not content:
                raise LLMAPIError(
                    "OpenRouter returned empty response",
                    provider=LLM_PROVIDER_OPENROUTER,
                    status_code=200,
                )
            
            return content
    
    except httpx.TimeoutException as e:
        raise LLMAPIError(
            f"Request timed out after {TIMEOUT_SECONDS}s: {e}",
            provider=LLM_PROVIDER_OPENROUTER,
        )
    except httpx.ConnectError as e:
        raise LLMAPIError(
            f"Network connection failed: {e}",
            provider=LLM_PROVIDER_OPENROUTER,
        )
    except httpx.HTTPError as e:
        raise LLMAPIError(
            f"HTTP error occurred: {e}",
            provider=LLM_PROVIDER_OPENROUTER,
        )
    except Exception as e:
        if isinstance(e, LLMAPIError):
            raise
        raise LLMAPIError(
            f"Unexpected error calling OpenRouter: {e}",
            provider=LLM_PROVIDER_OPENROUTER,
        )


async def call_anthropic(prompt: str, api_key: str, model: str | None = None) -> str:
    """
    Call Anthropic API directly.
    
    Args:
        prompt: The prompt to send to the LLM.
        api_key: Anthropic API key.
        model: Model to use (defaults to claude-3.5-sonnet).
    
    Returns:
        Response text from the LLM.
    
    Raises:
        LLMAPIError: If the API call fails.
    """
    model = model or DEFAULT_MODELS[LLM_PROVIDER_ANTHROPIC]
    url = "https://api.anthropic.com/v1/messages"
    
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    
    payload = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code != 200:
                error_detail = _extract_error_message(response)
                raise LLMAPIError(
                    f"Anthropic API error: {error_detail}",
                    provider=LLM_PROVIDER_ANTHROPIC,
                    status_code=response.status_code,
                )
            
            data = response.json()
            content_blocks = data.get("content", [])
            
            if not content_blocks:
                raise LLMAPIError(
                    "Anthropic returned empty content array",
                    provider=LLM_PROVIDER_ANTHROPIC,
                    status_code=200,
                )
            
            # Extract text from first content block
            content = content_blocks[0].get("text", "")
            
            if not content:
                raise LLMAPIError(
                    "Anthropic content block has no text",
                    provider=LLM_PROVIDER_ANTHROPIC,
                    status_code=200,
                )
            
            return content
    
    except httpx.TimeoutException as e:
        raise LLMAPIError(
            f"Request timed out after {TIMEOUT_SECONDS}s: {e}",
            provider=LLM_PROVIDER_ANTHROPIC,
        )
    except httpx.ConnectError as e:
        raise LLMAPIError(
            f"Network connection failed: {e}",
            provider=LLM_PROVIDER_ANTHROPIC,
        )
    except httpx.HTTPError as e:
        raise LLMAPIError(
            f"HTTP error occurred: {e}",
            provider=LLM_PROVIDER_ANTHROPIC,
        )
    except Exception as e:
        if isinstance(e, LLMAPIError):
            raise
        raise LLMAPIError(
            f"Unexpected error calling Anthropic: {e}",
            provider=LLM_PROVIDER_ANTHROPIC,
        )


async def call_openai(prompt: str, api_key: str, model: str | None = None) -> str:
    """
    Call OpenAI API directly.
    
    Args:
        prompt: The prompt to send to the LLM.
        api_key: OpenAI API key.
        model: Model to use (defaults to gpt-4o).
    
    Returns:
        Response text from the LLM.
    
    Raises:
        LLMAPIError: If the API call fails.
    """
    model = model or DEFAULT_MODELS[LLM_PROVIDER_OPENAI]
    url = "https://api.openai.com/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code != 200:
                error_detail = _extract_error_message(response)
                raise LLMAPIError(
                    f"OpenAI API error: {error_detail}",
                    provider=LLM_PROVIDER_OPENAI,
                    status_code=response.status_code,
                )
            
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if not content:
                raise LLMAPIError(
                    "OpenAI returned empty response",
                    provider=LLM_PROVIDER_OPENAI,
                    status_code=200,
                )
            
            return content
    
    except httpx.TimeoutException as e:
        raise LLMAPIError(
            f"Request timed out after {TIMEOUT_SECONDS}s: {e}",
            provider=LLM_PROVIDER_OPENAI,
        )
    except httpx.ConnectError as e:
        raise LLMAPIError(
            f"Network connection failed: {e}",
            provider=LLM_PROVIDER_OPENAI,
        )
    except httpx.HTTPError as e:
        raise LLMAPIError(
            f"HTTP error occurred: {e}",
            provider=LLM_PROVIDER_OPENAI,
        )
    except Exception as e:
        if isinstance(e, LLMAPIError):
            raise
        raise LLMAPIError(
            f"Unexpected error calling OpenAI: {e}",
            provider=LLM_PROVIDER_OPENAI,
        )


async def call_llm(prompt: str, provider: str | None = None, max_retries: int = 2) -> str:
    """
    Call LLM with automatic provider selection and retry logic.
    
    Args:
        prompt: The prompt to send.
        provider: Provider to use (defaults to LLM_PROVIDER env var).
        max_retries: Maximum number of retries for JSON parsing failures.
    
    Returns:
        Response text from the LLM.
    
    Raises:
        ConfigurationError: If API key is missing or provider is unknown.
        LLMAPIError: If all retry attempts fail.
    """
    provider = provider or get_llm_provider()
    api_key = get_api_key(provider)
    
    if not api_key:
        env_var_map = {
            LLM_PROVIDER_OPENROUTER: "OPENROUTER_API_KEY",
            LLM_PROVIDER_ANTHROPIC: "ANTHROPIC_API_KEY",
            LLM_PROVIDER_OPENAI: "OPENAI_API_KEY",
        }
        env_var = env_var_map.get(provider, f"{provider.upper()}_API_KEY")
        raise ConfigurationError(
            f"LLM API key not configured. Set {env_var} environment variable."
        )
    
    # Select provider function
    if provider == LLM_PROVIDER_OPENROUTER:
        call_func = call_openrouter
    elif provider == LLM_PROVIDER_ANTHROPIC:
        call_func = call_anthropic
    elif provider == LLM_PROVIDER_OPENAI:
        call_func = call_openai
    else:
        raise ConfigurationError(
            f"Unknown LLM provider: {provider}. "
            f"Supported: {LLM_PROVIDER_OPENROUTER}, {LLM_PROVIDER_ANTHROPIC}, {LLM_PROVIDER_OPENAI}"
        )
    
    # Call with retries (handled by caller for JSON parsing)
    return await call_func(prompt, api_key)


def _extract_error_message(response: httpx.Response) -> str:
    """Extract error message from API response."""
    try:
        data = response.json()
        if isinstance(data, dict):
            # Try common error message paths
            error = data.get("error", {})
            if isinstance(error, dict):
                return error.get("message", str(error))
            return str(error)
        return str(data)
    except Exception:
        return response.text[:200] if response.text else f"Status {response.status_code}"


