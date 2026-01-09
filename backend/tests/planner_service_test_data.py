"""Test data for planner service JSON parsing.

Contains various malformed LLM responses to test _extract_json_from_response()
and parse_llm_response() robustness.
"""

# =============================================================================
# Test Case 1: Clean JSON (should pass)
# =============================================================================
CLEAN_JSON = """{
  "tickets": [
    {
      "title": "Add user authentication",
      "description": "Implement JWT-based auth flow",
      "verification": ["pytest tests/test_auth.py"],
      "notes": null
    }
  ]
}"""
CLEAN_JSON_EXPECTED_COUNT = 1

# =============================================================================
# Test Case 2: JSON wrapped in markdown code fences
# =============================================================================
MARKDOWN_FENCED = """```json
{
  "tickets": [
    {
      "title": "Fix database connection",
      "description": "Handle connection pooling properly",
      "verification": ["python -m pytest -v"],
      "notes": "Check connection limits"
    },
    {
      "title": "Add logging",
      "description": "Implement structured logging",
      "verification": ["grep -r 'logger' src/"],
      "notes": null
    }
  ]
}
```"""
MARKDOWN_FENCED_EXPECTED_COUNT = 2

# =============================================================================
# Test Case 3: JSON with trailing commentary
# =============================================================================
WITH_TRAILING_COMMENTARY = """{
  "tickets": [
    {
      "title": "Implement caching layer",
      "description": "Add Redis caching for API responses",
      "verification": ["redis-cli ping", "pytest tests/test_cache.py"],
      "notes": "Requires Redis running locally"
    }
  ]
}

I hope this helps! Let me know if you need any changes to these tickets.
The verification commands should work with your current setup."""
WITH_TRAILING_COMMENTARY_EXPECTED_COUNT = 1

# =============================================================================
# Test Case 4: JSON with leading commentary
# =============================================================================
WITH_LEADING_COMMENTARY = """Here are the tickets I generated based on your goal:

{
  "tickets": [
    {
      "title": "Set up CI pipeline",
      "description": "Configure GitHub Actions for automated testing",
      "verification": ["gh workflow list"],
      "notes": null
    },
    {
      "title": "Add pre-commit hooks",
      "description": "Install pre-commit with ruff and black",
      "verification": ["pre-commit run --all-files"],
      "notes": null
    }
  ]
}"""
WITH_LEADING_COMMENTARY_EXPECTED_COUNT = 2

# =============================================================================
# Test Case 5: Triple-fenced without json tag
# =============================================================================
MARKDOWN_FENCED_NO_TAG = """```
{
  "tickets": [
    {
      "title": "Refactor API routes",
      "description": "Split monolithic routes into modules",
      "verification": ["python -c 'import app.routers'"],
      "notes": "Follow REST conventions"
    }
  ]
}
```"""
MARKDOWN_FENCED_NO_TAG_EXPECTED_COUNT = 1

# =============================================================================
# Test Case 6: JSON with both leading and trailing noise
# =============================================================================
NOISY_RESPONSE = """Based on the repository structure, here are my recommendations:

```json
{
  "tickets": [
    {
      "title": "Add input validation",
      "description": "Validate all user inputs with Pydantic",
      "verification": ["pytest tests/test_validation.py -v"],
      "notes": "Focus on edge cases"
    },
    {
      "title": "Improve error handling",
      "description": "Add custom exception handlers",
      "verification": ["curl -X POST localhost:8000/bad-endpoint"],
      "notes": null
    },
    {
      "title": "Add rate limiting",
      "description": "Implement rate limiting middleware",
      "verification": ["ab -n 100 -c 10 http://localhost:8000/api/"],
      "notes": "Use sliding window algorithm"
    }
  ]
}
```

These tickets are ordered by priority. Let me know if you'd like me to adjust anything!"""
NOISY_RESPONSE_EXPECTED_COUNT = 3

# =============================================================================
# Test Case 7: Invalid JSON (should fail)
# =============================================================================
INVALID_JSON_MISSING_BRACKET = """{
  "tickets": [
    {
      "title": "Broken ticket",
      "description": "This JSON is malformed"
      "verification": ["test"],
      "notes": null
    }
  ]
}"""  # Missing comma after description

# =============================================================================
# Test Case 8: Empty tickets array (edge case - should pass but return empty)
# =============================================================================
EMPTY_TICKETS = """{"tickets": []}"""
EMPTY_TICKETS_EXPECTED_COUNT = 0

# =============================================================================
# Test Case 9: Extra whitespace and newlines
# =============================================================================
EXTRA_WHITESPACE = """


   {
  "tickets":    [
    {
      "title":    "Handle whitespace",
      "description": "Test parser handles extra spaces",
      "verification": [   "echo 'test'"   ],
      "notes":    null
    }
  ]
}

   """
EXTRA_WHITESPACE_EXPECTED_COUNT = 1

# =============================================================================
# Test Case 10: Schema violation - wrong field type (should fail validation)
# =============================================================================
WRONG_FIELD_TYPE = """{
  "tickets": [
    {
      "title": "Wrong types",
      "description": "Verification should be array",
      "verification": "not-an-array",
      "notes": null
    }
  ]
}"""

# =============================================================================
# All valid test cases for parametrized testing
# =============================================================================
VALID_TEST_CASES = [
    ("clean_json", CLEAN_JSON, CLEAN_JSON_EXPECTED_COUNT),
    ("markdown_fenced", MARKDOWN_FENCED, MARKDOWN_FENCED_EXPECTED_COUNT),
    ("trailing_commentary", WITH_TRAILING_COMMENTARY, WITH_TRAILING_COMMENTARY_EXPECTED_COUNT),
    ("leading_commentary", WITH_LEADING_COMMENTARY, WITH_LEADING_COMMENTARY_EXPECTED_COUNT),
    ("markdown_no_tag", MARKDOWN_FENCED_NO_TAG, MARKDOWN_FENCED_NO_TAG_EXPECTED_COUNT),
    ("noisy_response", NOISY_RESPONSE, NOISY_RESPONSE_EXPECTED_COUNT),
    ("empty_tickets", EMPTY_TICKETS, EMPTY_TICKETS_EXPECTED_COUNT),
    ("extra_whitespace", EXTRA_WHITESPACE, EXTRA_WHITESPACE_EXPECTED_COUNT),
]

INVALID_TEST_CASES = [
    ("invalid_json", INVALID_JSON_MISSING_BRACKET, "Invalid JSON"),
    ("wrong_field_type", WRONG_FIELD_TYPE, "validation"),
]


