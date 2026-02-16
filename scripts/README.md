# Alma Kanban Scripts

This directory contains utility scripts for managing the Alma Kanban system.

## Ticket Generation Scripts

### generate_test_tickets.sh

Generates a JSON file containing 4 pre-defined tickets for the `~/Documents/code/tests/` project.

**Usage:**
```bash
./generate_test_tickets.sh [output_file]
```

**Examples:**
```bash
# Generate tickets to default file (test_project_tickets.json)
./generate_test_tickets.sh

# Generate tickets to custom file
./generate_test_tickets.sh my_tickets.json
```

**Generated Tickets:**
1. **[P0]** Set up project structure and dependencies
2. **[P1]** Implement core utility functions
3. **[P1]** Add comprehensive test suite with CI integration
4. **[P2]** Create documentation and usage examples

**Output:** A JSON file that can be used as reference for creating tickets via the API.

---

### create_test_tickets.sh

Automatically creates 4 tickets for the `~/Documents/code/tests/` project via the Alma Kanban API.

**Prerequisites:**
- Backend server must be running: `cd backend && uvicorn app.main:app --reload`
- API must be accessible (default: http://localhost:8000)

**Usage:**
```bash
./create_test_tickets.sh [api_url] [goal_title]
```

**Examples:**
```bash
# Create tickets using default settings
./create_test_tickets.sh

# Create tickets with custom API URL
./create_test_tickets.sh http://localhost:8000

# Create tickets with custom API URL and goal title
./create_test_tickets.sh http://localhost:8000 "My Custom Goal"
```

**What it does:**
1. Checks if the API is accessible
2. Creates a new goal for the test project
3. Creates 4 tickets under that goal with appropriate priorities
4. Displays ticket IDs and next steps

**Output:**
- Goal ID and URL
- 4 Ticket IDs
- Commands for next steps (viewing board, transitioning tickets, etc.)

---

## Other Scripts

### clean_slate.sh

Resets the database to a clean state. Use with caution!

### create_goal_report.sh

Generates a comprehensive report for a specific goal, including all tickets and their status.

---

## Quick Start Example

To quickly set up tickets for your test project:

```bash
# 1. Make sure backend is running
cd ../backend
source venv/bin/activate
uvicorn app.main:app --reload &

# 2. Wait a moment for server to start
sleep 3

# 3. Create tickets
cd ../scripts
./create_test_tickets.sh

# 4. View the board in your browser
# Frontend: http://localhost:5173
# API Docs: http://localhost:8000/docs
```

## Customizing Tickets

To create tickets for a different project:

1. **Option 1:** Edit `generate_test_tickets.sh` and modify the JSON content
2. **Option 2:** Edit `create_test_tickets.sh` and modify the ticket descriptions and API calls
3. **Option 3:** Use the generated JSON as a template and manually create tickets via the API

## API Reference

### Create a Goal
```bash
curl -X POST http://localhost:8000/goals \
  -H 'Content-Type: application/json' \
  -d '{"title": "My Goal", "description": "Description here"}'
```

### Create a Ticket
```bash
curl -X POST http://localhost:8000/tickets \
  -H 'Content-Type: application/json' \
  -d '{
    "goal_id": "YOUR_GOAL_ID",
    "title": "Ticket title",
    "description": "Detailed description",
    "priority": 90,
    "actor_type": "human",
    "actor_id": "user-1"
  }'
```

### View Board
```bash
curl http://localhost:8000/board
```

For more examples, see [../backend/CURL_EXAMPLES.md](../backend/CURL_EXAMPLES.md)

---

## Troubleshooting

### "Cannot connect to API"
- Ensure the backend server is running
- Check that you're using the correct API URL (default: http://localhost:8000)
- Verify with: `curl http://localhost:8000/health`

### "Permission denied"
- Make scripts executable: `chmod +x *.sh`

### "Goal creation failed"
- Check backend logs for errors
- Verify database is initialized: `cd backend && alembic upgrade head`
- Check that all required environment variables are set

---

## Contributing

When adding new ticket generation scripts:
1. Follow the naming convention: `create_<project>_tickets.sh` or `generate_<project>_tickets.sh`
2. Include usage examples and error handling
3. Update this README with script documentation
4. Test with a clean database state


