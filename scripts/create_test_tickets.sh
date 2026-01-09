#!/bin/bash
# Script to create 4 tickets for ~/Documents/code/tests/ project via API
# Usage: ./create_test_tickets.sh [api_url] [goal_title]
# Example: ./create_test_tickets.sh http://localhost:8000 "Bootstrap Test Project"

set -e

API_URL="${1:-http://localhost:8000}"
GOAL_TITLE="${2:-Bootstrap Test Project for ~/Documents/code/tests}"
PROJECT_PATH="$HOME/Documents/code/tests"

echo "=========================================="
echo "Test Project Ticket Generator"
echo "=========================================="
echo "API URL: $API_URL"
echo "Project: $PROJECT_PATH"
echo "Goal: $GOAL_TITLE"
echo ""

# Check if API is accessible
if ! curl -s -f "$API_URL/health" > /dev/null 2>&1; then
    echo "❌ Error: Cannot connect to API at $API_URL"
    echo "   Please ensure the backend server is running:"
    echo "   cd backend && source venv/bin/activate && uvicorn app.main:app --reload"
    exit 1
fi

echo "✅ API is accessible"
echo ""

# Step 1: Create the goal
echo "📋 Step 1: Creating goal..."
GOAL_RESPONSE=$(curl -s -X POST "$API_URL/goals" \
  -H "Content-Type: application/json" \
  -d "{
    \"title\": \"$GOAL_TITLE\",
    \"description\": \"Set up and implement foundational features for the test project at $PROJECT_PATH. This includes project structure, core utilities, testing infrastructure, and documentation.\"
  }")

GOAL_ID=$(echo "$GOAL_RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$GOAL_ID" ]; then
    echo "❌ Error: Failed to create goal"
    echo "Response: $GOAL_RESPONSE"
    exit 1
fi

echo "✅ Goal created with ID: $GOAL_ID"
echo ""

# Step 2: Create tickets
echo "🎫 Step 2: Creating tickets..."
echo ""

TICKET_IDS=()

# Ticket 1: Project Structure
echo "  [1/4] Creating ticket: Set up project structure..."
TICKET1=$(curl -s -X POST "$API_URL/tickets" \
  -H "Content-Type: application/json" \
  -d "{
    \"goal_id\": \"$GOAL_ID\",
    \"title\": \"Set up project structure and dependencies\",
    \"description\": \"Initialize the test project with proper directory structure and dependency management.\\n\\nTasks:\\n1. Create main project directory structure (src/, tests/, docs/)\\n2. Initialize git repository if not already initialized\\n3. Create requirements.txt or package.json depending on project type\\n4. Set up .gitignore with common patterns\\n5. Create a basic README.md with project overview\\n6. Add a LICENSE file (MIT recommended)\\n\\nAcceptance criteria:\\n- Project has organized directory structure\\n- Dependency management file exists (requirements.txt or package.json)\\n- Git repository is initialized with proper .gitignore\\n- README.md contains project description and setup instructions\\n- LICENSE file is present\",
    \"priority\": 100,
    \"actor_type\": \"human\",
    \"actor_id\": \"script-generator\"
  }")
TICKET1_ID=$(echo "$TICKET1" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
TICKET_IDS+=("$TICKET1_ID")
echo "     ✅ Created: $TICKET1_ID"

# Ticket 2: Core Utilities
echo "  [2/4] Creating ticket: Implement core utility functions..."
TICKET2=$(curl -s -X POST "$API_URL/tickets" \
  -H "Content-Type: application/json" \
  -d "{
    \"goal_id\": \"$GOAL_ID\",
    \"title\": \"Implement core utility functions\",
    \"description\": \"Create a module with essential utility functions for data processing.\\n\\nFunctions to implement:\\n1. validate_input(data) - Validate input data structure and types\\n2. parse_config(filepath) - Parse configuration from JSON/YAML file\\n3. format_output(data, format_type) - Format data for different output types (json, csv, text)\\n4. log_message(level, message) - Centralized logging with levels (debug, info, warning, error)\\n5. retry_operation(func, max_attempts, delay) - Retry decorator for failing operations\\n\\nRequirements:\\n- All functions must have type hints\\n- Comprehensive docstrings with examples\\n- Error handling with custom exceptions\\n- Unit tests for each function\\n\\nAcceptance criteria:\\n- Utility module exists with all 5 functions\\n- Functions have type hints and docstrings\\n- Error cases are handled gracefully\\n- 100% test coverage for utility module\",
    \"priority\": 90,
    \"actor_type\": \"human\",
    \"actor_id\": \"script-generator\"
  }")
TICKET2_ID=$(echo "$TICKET2" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
TICKET_IDS+=("$TICKET2_ID")
echo "     ✅ Created: $TICKET2_ID"

# Ticket 3: Testing Infrastructure
echo "  [3/4] Creating ticket: Add comprehensive test suite..."
TICKET3=$(curl -s -X POST "$API_URL/tickets" \
  -H "Content-Type: application/json" \
  -d "{
    \"goal_id\": \"$GOAL_ID\",
    \"title\": \"Add comprehensive test suite with CI integration\",
    \"description\": \"Set up a complete testing infrastructure with continuous integration.\\n\\nComponents:\\n1. Unit tests for all modules (targeting 80%+ coverage)\\n2. Integration tests for key workflows\\n3. Test fixtures and mocks for external dependencies\\n4. GitHub Actions or GitLab CI configuration\\n5. Code coverage reporting (codecov or coveralls)\\n6. Pre-commit hooks for running tests\\n\\nCI Pipeline stages:\\n- Lint and format check\\n- Run all tests\\n- Generate coverage report\\n- Build artifacts (if applicable)\\n\\nAcceptance criteria:\\n- Test suite covers at least 80% of codebase\\n- CI configuration file exists and runs on push/PR\\n- Coverage reports are generated automatically\\n- Pre-commit hooks prevent committing untested code\\n- All tests pass in CI environment\",
    \"priority\": 85,
    \"actor_type\": \"human\",
    \"actor_id\": \"script-generator\"
  }")
TICKET3_ID=$(echo "$TICKET3" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
TICKET_IDS+=("$TICKET3_ID")
echo "     ✅ Created: $TICKET3_ID"

# Ticket 4: Documentation
echo "  [4/4] Creating ticket: Create documentation..."
TICKET4=$(curl -s -X POST "$API_URL/tickets" \
  -H "Content-Type: application/json" \
  -d "{
    \"goal_id\": \"$GOAL_ID\",
    \"title\": \"Create documentation and usage examples\",
    \"description\": \"Develop comprehensive documentation for the project with practical examples.\\n\\nDocumentation includes:\\n1. API reference with all public functions/classes\\n2. Getting started guide with installation instructions\\n3. Usage examples for common scenarios\\n4. Architecture overview diagram\\n5. Contributing guidelines (CONTRIBUTING.md)\\n6. Changelog template (CHANGELOG.md)\\n7. Example configurations and use cases\\n\\nFormat:\\n- Use Markdown for all documentation\\n- Include code examples with syntax highlighting\\n- Add diagrams using Mermaid or draw.io\\n- Keep examples simple and runnable\\n\\nAcceptance criteria:\\n- docs/ directory exists with organized documentation\\n- README.md links to detailed documentation\\n- At least 3 working code examples are provided\\n- CONTRIBUTING.md explains how to contribute\\n- Documentation is clear and easy to follow\",
    \"priority\": 70,
    \"actor_type\": \"human\",
    \"actor_id\": \"script-generator\"
  }")
TICKET4_ID=$(echo "$TICKET4" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
TICKET_IDS+=("$TICKET4_ID")
echo "     ✅ Created: $TICKET4_ID"

echo ""
echo "=========================================="
echo "✨ Success! Created 4 tickets"
echo "=========================================="
echo ""
echo "Goal ID: $GOAL_ID"
echo "Goal URL: $API_URL/goals/$GOAL_ID"
echo ""
echo "Ticket IDs:"
for i in "${!TICKET_IDS[@]}"; do
    echo "  $((i+1)). ${TICKET_IDS[$i]}"
done
echo ""
echo "Next steps:"
echo "  1. View your kanban board: $API_URL/board"
echo "  2. View tickets for this goal: $API_URL/goals/$GOAL_ID/tickets"
echo "  3. Transition tickets through the workflow:"
echo "     curl -X POST $API_URL/tickets/${TICKET_IDS[0]}/transition \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"to_state\": \"planned\", \"actor_type\": \"human\", \"actor_id\": \"user-1\", \"reason\": \"Ready to start\"}'"
echo ""
echo "  4. If using the frontend, open: http://localhost:5173"
echo ""


