"""Thin LLM service - provider abstraction and JSON parsing only.

This service handles:
- LLM API calls via LiteLLM (or Bedrock directly for inference profiles)
- JSON response parsing

Business logic, prompts, and orchestration belong in higher-level services
like TicketGenerationService.
"""

import json
import logging
import re
from dataclasses import dataclass

import litellm
from litellm import completion

from app.services.config_service import ConfigService, PlannerConfig

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Raw LLM response wrapper."""

    content: str
    model: str
    usage: dict | None = None


class LLMService:
    """Thin LLM client for API calls and JSON parsing.

    Uses LiteLLM to support multiple providers (OpenAI, Anthropic, etc.)
    with a unified API. The model and settings are configured via
    draft.yaml planner_config section.

    This service is intentionally minimal - it only handles:
    1. Making LLM API calls
    2. Parsing JSON from responses

    All prompts, business logic, and orchestration should live in
    higher-level services (e.g., TicketGenerationService).
    """

    def __init__(self, config: PlannerConfig | None = None):
        """Initialize the LLM service.

        Args:
            config: Planner configuration. If None, loads from config file.
        """
        if config is None:
            config_service = ConfigService()
            config = config_service.get_planner_config()

        self.config = config

        # Disable litellm logging noise
        litellm.set_verbose = False

    def _is_bedrock_inference_profile(self) -> bool:
        """Check if the configured model is a Bedrock inference profile."""
        model = self.config.model
        is_inference_profile = "inference-profile" in model
        # Specifically check for Sonnet 4.5 (not 3.5!)
        is_sonnet_45 = "sonnet-4-5" in model or "sonnet-4.5" in model
        return is_inference_profile or is_sonnet_45

    def _get_inference_profile_arn(self) -> str:
        """Extract or construct the inference profile ARN from the model config."""
        import os

        model = self.config.model

        # If it's already a full ARN, extract it
        if "arn:aws:bedrock" in model:
            if model.startswith("bedrock/converse/"):
                return model.replace("bedrock/converse/", "")
            elif model.startswith("bedrock/"):
                return model.replace("bedrock/", "")
            return model

        # Otherwise, construct the inference profile ARN
        if model.startswith("bedrock/converse/"):
            model_id = model.replace("bedrock/converse/", "")
        elif model.startswith("bedrock/"):
            model_id = model.replace("bedrock/", "")
        else:
            model_id = model

        region = os.getenv("AWS_REGION_NAME", "us-east-2")

        # For Claude Sonnet 4.5, use the global inference profile
        if "claude-sonnet-4-5" in model_id or "claude-sonnet-4-5" in model_id.replace(
            ".", "-"
        ):
            return f"arn:aws:bedrock:{region}:486893719511:inference-profile/global.{model_id}"

        return model_id

    def call_completion(
        self,
        messages: list[dict],
        max_tokens: int,
        system_prompt: str | None = None,
        timeout: int | None = None,
        json_mode: bool = True,
    ) -> LLMResponse:
        """Make an LLM API call.

        Args:
            messages: List of message dicts with role and content.
            max_tokens: Maximum tokens in response.
            system_prompt: Optional system prompt (prepended to messages).
            timeout: Request timeout in seconds (defaults to config timeout).
            json_mode: Whether to request JSON response format.

        Returns:
            LLMResponse with the response content.

        Raises:
            Exception: If LLM API call fails.
        """
        if timeout is None:
            timeout = self.config.timeout

        # Use boto3 directly for Bedrock inference profiles
        if self._is_bedrock_inference_profile():
            content = self._call_bedrock_inference_profile(
                messages=messages,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
            )
            return LLMResponse(content=content, model=self.config.model)

        # Build messages list with system prompt
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        # Call via LiteLLM
        kwargs = {
            "model": self.config.model,
            "messages": full_messages,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = completion(**kwargs)
        content = response.choices[0].message.content

        usage = None
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=content,
            model=self.config.model,
            usage=usage,
        )

    def _call_bedrock_inference_profile(
        self,
        messages: list[dict],
        max_tokens: int,
        system_prompt: str | None = None,
    ) -> str:
        """Call Bedrock directly using boto3 for inference profiles.

        Args:
            messages: List of message dicts with role and content.
            max_tokens: Maximum tokens in response.
            system_prompt: Optional system prompt.

        Returns:
            The response content as a string.
        """
        import os

        import boto3
        from botocore.config import Config

        # Add timeouts to prevent hanging indefinitely if Bedrock is slow/unresponsive
        boto_config = Config(
            connect_timeout=30,
            read_timeout=120,  # LLM responses can be slow
            retries={"max_attempts": 2, "mode": "standard"},
        )

        client = boto3.client(
            "bedrock-runtime",
            region_name=os.getenv("AWS_REGION_NAME", "us-east-2"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            config=boto_config,
        )

        inference_profile_arn = self._get_inference_profile_arn()

        # Build the converse request
        converse_messages = []
        for msg in messages:
            if msg["role"] == "system":
                continue  # System handled separately
            converse_messages.append(
                {
                    "role": msg["role"],
                    "content": [{"text": msg["content"]}],
                }
            )

        request_params = {
            "modelId": inference_profile_arn,
            "messages": converse_messages,
            "inferenceConfig": {
                "maxTokens": max_tokens,
            },
        }

        if system_prompt:
            request_params["system"] = [{"text": system_prompt}]

        response = client.converse(**request_params)

        return response["output"]["message"]["content"][0]["text"]

    def parse_json(self, content: str) -> dict:
        """Parse JSON from LLM response content.

        Handles common LLM quirks like markdown code blocks.

        Args:
            content: Raw LLM response content.

        Returns:
            Parsed JSON as a dict.

        Raises:
            json.JSONDecodeError: If content is not valid JSON.
        """
        # Try direct parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                pass

        # Re-raise the original error
        raise json.JSONDecodeError(
            f"Failed to parse JSON from content: {content[:200]}...",
            content,
            0,
        )

    def safe_parse_json(self, content: str, default: dict | None = None) -> dict:
        """Parse JSON with fallback to default on error.

        Args:
            content: Raw LLM response content.
            default: Default value if parsing fails.

        Returns:
            Parsed JSON or default value.
        """
        try:
            return self.parse_json(content)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            return default or {}
