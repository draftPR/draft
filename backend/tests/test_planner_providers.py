"""Integration tests for LLM provider API calls with mocked responses."""

import json
from unittest.mock import patch

import httpx
import pytest

from app.exceptions import ConfigurationError, LLMAPIError
from app.services.llm_provider_clients import (
    call_anthropic,
    call_llm,
    call_openai,
    call_openrouter,
)

# Use pytest-anyio for async tests (already installed)
pytestmark = pytest.mark.anyio


class TestOpenRouterProvider:
    """Test OpenRouter API integration with mocked responses."""

    async def test_successful_response(self):
        """Test successful OpenRouter API call."""
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "tickets": [
                                {
                                    "title": "Test Ticket",
                                    "description": "Test Description",
                                    "verification": ["echo 'test'"],
                                    "notes": None,
                                }
                            ]
                        })
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                200, json=mock_response, request=httpx.Request("POST", "https://example.com")
            )
            result = await call_openrouter("test prompt", "fake-key")
            assert "Test Ticket" in result

    async def test_authentication_error(self):
        """Test OpenRouter authentication error."""
        mock_response = {"error": {"message": "Invalid API key", "code": "invalid_api_key"}}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                401, json=mock_response, request=httpx.Request("POST", "https://example.com")
            )
            with pytest.raises(LLMAPIError) as exc_info:
                await call_openrouter("test prompt", "invalid-key")

            assert "401" in str(exc_info.value)
            assert "openrouter" in str(exc_info.value).lower()

    async def test_rate_limit_error(self):
        """Test OpenRouter rate limit error."""
        mock_response = {"error": {"message": "Rate limit exceeded"}}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                429, json=mock_response, request=httpx.Request("POST", "https://example.com")
            )
            with pytest.raises(LLMAPIError) as exc_info:
                await call_openrouter("test prompt", "fake-key")

            assert "429" in str(exc_info.value) or "rate limit" in str(exc_info.value).lower()

    async def test_timeout_handled(self):
        """Test that timeouts are handled gracefully."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timed out")

            with pytest.raises(LLMAPIError) as exc_info:
                await call_openrouter("test prompt", "fake-key")

            assert "timed out" in str(exc_info.value).lower()

    async def test_network_error_handled(self):
        """Test that network errors are handled gracefully."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection failed")

            with pytest.raises(LLMAPIError) as exc_info:
                await call_openrouter("test prompt", "fake-key")

            assert "connection" in str(exc_info.value).lower() or "network" in str(exc_info.value).lower()

    async def test_invalid_json_response_returns_raw_text(self):
        """Test that invalid JSON in response body still returns text content."""
        invalid_response = {
            "choices": [{"message": {"content": "Here's some text before {invalid json"}}]
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                200, json=invalid_response, request=httpx.Request("POST", "https://example.com")
            )
            # call_openrouter extracts text content as-is (no JSON validation)
            result = await call_openrouter("test prompt", "fake-key")
            assert "invalid json" in result


class TestAnthropicProvider:
    """Test Anthropic API integration with mocked responses."""

    async def test_successful_response(self):
        """Test successful Anthropic API call."""
        mock_response = {
            "content": [
                {
                    "text": json.dumps({
                        "tickets": [
                            {
                                "title": "Anthropic Ticket",
                                "description": "Test Description",
                                "verification": ["echo 'test'"],
                            }
                        ]
                    })
                }
            ]
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                200, json=mock_response, request=httpx.Request("POST", "https://example.com")
            )
            result = await call_anthropic("test prompt", "fake-key")
            assert "Anthropic Ticket" in result

    async def test_authentication_error(self):
        """Test Anthropic authentication error."""
        mock_response = {"error": {"type": "authentication_error", "message": "Invalid API key"}}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                401, json=mock_response, request=httpx.Request("POST", "https://example.com")
            )
            with pytest.raises(LLMAPIError) as exc_info:
                await call_anthropic("test prompt", "invalid-key")

            assert "401" in str(exc_info.value)

    async def test_empty_content_array(self):
        """Test Anthropic response with empty content array."""
        mock_response = {"content": []}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                200, json=mock_response, request=httpx.Request("POST", "https://example.com")
            )
            with pytest.raises(LLMAPIError) as exc_info:
                await call_anthropic("test prompt", "fake-key")

            assert "empty" in str(exc_info.value).lower() or "content" in str(exc_info.value).lower()


class TestOpenAIProvider:
    """Test OpenAI API integration with mocked responses."""

    async def test_successful_response(self):
        """Test successful OpenAI API call."""
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "tickets": [
                                {
                                    "title": "OpenAI Ticket",
                                    "description": "Test Description",
                                    "verification": ["echo 'test'"],
                                }
                            ]
                        })
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                200, json=mock_response, request=httpx.Request("POST", "https://example.com")
            )
            result = await call_openai("test prompt", "fake-key")
            assert "OpenAI Ticket" in result

    async def test_authentication_error(self):
        """Test OpenAI authentication error."""
        mock_response = {
            "error": {
                "message": "Incorrect API key provided",
                "type": "invalid_request_error",
                "code": "invalid_api_key",
            }
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                401, json=mock_response, request=httpx.Request("POST", "https://example.com")
            )
            with pytest.raises(LLMAPIError) as exc_info:
                await call_openai("test prompt", "invalid-key")

            assert "401" in str(exc_info.value)

    async def test_timeout_handled(self):
        """Test that OpenAI timeouts are handled gracefully."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timed out")

            with pytest.raises(LLMAPIError) as exc_info:
                await call_openai("test prompt", "fake-key")

            assert "timed out" in str(exc_info.value).lower()


class TestProviderConfiguration:
    """Test provider configuration and error handling."""

    async def test_missing_api_key_raises_configuration_error(self):
        """Test that missing API key raises ConfigurationError."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                await call_llm("test prompt", provider="openrouter")

            assert "api key" in str(exc_info.value).lower()
            assert "OPENROUTER_API_KEY" in str(exc_info.value)

    async def test_unknown_provider_raises_configuration_error(self):
        """Test that unknown provider raises ConfigurationError.

        Note: call_llm checks for missing API key before checking provider,
        so an unknown provider with no matching API key raises a key error.
        """
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                await call_llm("test prompt", provider="fake_provider")

            assert "api key" in str(exc_info.value).lower()
