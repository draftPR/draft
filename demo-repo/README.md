# Demo Calculator App

A simple calculator application with some bugs and missing features - perfect for demonstrating Smart Kanban's autonomous code delivery.

## What's Wrong?

This codebase has several issues that Smart Kanban will help fix:

1. **Division by zero crashes** - No error handling
2. **Negative number handling is broken** - Square root doesn't validate input
3. **Missing tests** - Edge cases not covered
4. **TODOs everywhere** - Features waiting to be implemented

## How to Use This Demo

1. Start Smart Kanban (it's already running if you see this!)
2. Open the UI at http://localhost:3000
3. Look at the pre-created goal: "Fix the calculator bugs and add missing tests"
4. Click "Generate Tickets" to see AI planning in action
5. Watch as Smart Kanban autonomously implements the fixes
6. Review the changes and merge when ready

## Project Structure

```
demo-repo/
├── src/
│   ├── calculator.py    # Main calculator with bugs
│   └── utils.py         # Utility functions
├── tests/
│   └── test_calculator.py  # Incomplete test suite
└── .smartkanban.yaml    # Smart Kanban configuration
```

## Running Tests

```bash
cd demo-repo
python -m pytest tests/ -v
```

## The Goal

Smart Kanban will:
- Analyze the codebase
- Generate tickets for each issue
- Execute fixes autonomously
- Verify with tests
- Present changes for your review

All without you writing a single line of code manually!
