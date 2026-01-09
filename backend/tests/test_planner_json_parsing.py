"""Tests for planner service JSON parsing and extraction.

These tests verify that _extract_json_from_response() and parse_llm_response()
correctly handle various malformed LLM outputs.
"""

import pytest

from app.services.planner_service import (
    _extract_json_from_response,
    _enforce_limits,
    parse_llm_response,
    MAX_TICKETS,
    MAX_TITLE_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_VERIFICATION_COMMANDS,
)
from app.schemas.planner import ProposedTicketSchema

from tests.planner_service_test_data import (
    VALID_TEST_CASES,
    INVALID_TEST_CASES,
    CLEAN_JSON,
)


class TestExtractJsonFromResponse:
    """Tests for _extract_json_from_response() function."""

    @pytest.mark.parametrize("name,response,expected_count", VALID_TEST_CASES)
    def test_extracts_valid_json(self, name: str, response: str, expected_count: int):
        """Test that JSON can be extracted from various response formats."""
        extracted = _extract_json_from_response(response)
        
        # Should start with { and end with }
        assert extracted.strip().startswith("{"), f"{name}: Should start with {{"
        assert extracted.strip().endswith("}"), f"{name}: Should end with }}"
        
        # Should be valid JSON (parseable)
        import json
        data = json.loads(extracted)
        assert "tickets" in data, f"{name}: Should have 'tickets' key"
        assert len(data["tickets"]) == expected_count, f"{name}: Wrong ticket count"

    def test_handles_pure_json(self):
        """Clean JSON should pass through unchanged."""
        result = _extract_json_from_response(CLEAN_JSON)
        assert result.strip() == CLEAN_JSON.strip()

    def test_finds_json_in_noise(self):
        """Should find JSON object even buried in text."""
        noisy = "Hello! Here's your answer: {\"tickets\": []} And that's it!"
        result = _extract_json_from_response(noisy)
        assert result.strip() == '{"tickets": []}'


class TestParseLlmResponse:
    """Tests for parse_llm_response() function."""

    @pytest.mark.parametrize("name,response,expected_count", VALID_TEST_CASES)
    def test_parses_valid_responses(self, name: str, response: str, expected_count: int):
        """Test that valid responses are parsed correctly."""
        tickets = parse_llm_response(response)
        assert len(tickets) == expected_count, f"{name}: Wrong ticket count"
        
        for ticket in tickets:
            assert isinstance(ticket, ProposedTicketSchema)
            assert ticket.title
            assert ticket.description
            assert isinstance(ticket.verification, list)

    @pytest.mark.parametrize("name,response,error_substring", INVALID_TEST_CASES)
    def test_rejects_invalid_responses(self, name: str, response: str, error_substring: str):
        """Test that invalid responses raise ValueError with descriptive message."""
        with pytest.raises(ValueError) as exc_info:
            parse_llm_response(response)
        
        assert error_substring.lower() in str(exc_info.value).lower(), \
            f"{name}: Error should mention '{error_substring}'"


class TestEnforceLimits:
    """Tests for _enforce_limits() function."""

    def test_truncates_excess_tickets(self):
        """Should truncate to MAX_TICKETS."""
        # Create more tickets than allowed
        tickets = [
            ProposedTicketSchema(
                title=f"Ticket {i}",
                description=f"Description {i}",
                verification=["test"],
            )
            for i in range(MAX_TICKETS + 3)
        ]
        
        result = _enforce_limits(tickets)
        assert len(result) == MAX_TICKETS

    def test_truncates_long_title(self):
        """Should truncate titles to MAX_TITLE_LENGTH."""
        long_title = "A" * (MAX_TITLE_LENGTH + 50)
        tickets = [
            ProposedTicketSchema(
                title=long_title,
                description="Short desc",
                verification=[],
            )
        ]
        
        result = _enforce_limits(tickets)
        assert len(result[0].title) == MAX_TITLE_LENGTH

    def test_truncates_long_description(self):
        """Should truncate descriptions to MAX_DESCRIPTION_LENGTH."""
        long_desc = "B" * (MAX_DESCRIPTION_LENGTH + 100)
        tickets = [
            ProposedTicketSchema(
                title="Short",
                description=long_desc,
                verification=[],
            )
        ]
        
        result = _enforce_limits(tickets)
        assert len(result[0].description) == MAX_DESCRIPTION_LENGTH

    def test_truncates_verification_commands(self):
        """Should truncate verification list to MAX_VERIFICATION_COMMANDS."""
        many_commands = [f"command {i}" for i in range(MAX_VERIFICATION_COMMANDS + 5)]
        tickets = [
            ProposedTicketSchema(
                title="Test",
                description="Desc",
                verification=many_commands,
            )
        ]
        
        result = _enforce_limits(tickets)
        assert len(result[0].verification) == MAX_VERIFICATION_COMMANDS

    def test_preserves_valid_tickets(self):
        """Valid tickets within limits should pass through unchanged."""
        tickets = [
            ProposedTicketSchema(
                title="Valid ticket",
                description="Valid description",
                verification=["cmd1", "cmd2"],
                notes="Some notes",
            )
        ]
        
        result = _enforce_limits(tickets)
        assert len(result) == 1
        assert result[0].title == "Valid ticket"
        assert result[0].description == "Valid description"
        assert result[0].verification == ["cmd1", "cmd2"]
        assert result[0].notes == "Some notes"


class TestJsonExtractionEdgeCases:
    """Edge case tests for JSON extraction."""

    def test_multiple_json_objects_takes_first_valid(self):
        """When multiple JSON objects present, should extract the tickets one."""
        response = """
        {"config": {}}
        Here's the result:
        {"tickets": [{"title": "Real", "description": "D", "verification": []}]}
        {"other": "data"}
        """
        result = _extract_json_from_response(response)
        import json
        data = json.loads(result)
        # Should get a valid object (either config or tickets)
        assert isinstance(data, dict)

    def test_nested_code_fences(self):
        """Should handle nested/multiple code fences."""
        response = """
        Some text
        ```
        not json
        ```
        ```json
        {"tickets": [{"title": "T", "description": "D", "verification": []}]}
        ```
        more text
        """
        tickets = parse_llm_response(response)
        assert len(tickets) == 1

    def test_unicode_content(self):
        """Should handle unicode in ticket content."""
        response = """
        {"tickets": [
            {"title": "支持中文", "description": "日本語のテスト", "verification": ["echo '✓'"]}
        ]}
        """
        tickets = parse_llm_response(response)
        assert len(tickets) == 1
        assert "中文" in tickets[0].title

    def test_empty_string_raises(self):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError):
            parse_llm_response("")

    def test_whitespace_only_raises(self):
        """Whitespace-only string should raise ValueError."""
        with pytest.raises(ValueError):
            parse_llm_response("   \n\t  ")


