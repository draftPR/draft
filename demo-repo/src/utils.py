"""Utility functions for the calculator app."""


def format_result(result: float, precision: int = 2) -> str:
    """Format a calculation result for display.

    Args:
        result: The numerical result to format
        precision: Number of decimal places (default: 2)

    Returns:
        Formatted string representation
    """
    return f"{result:.{precision}f}"


def is_valid_number(value: str) -> bool:
    """Check if a string can be converted to a number.

    TODO: Add validation for edge cases (inf, nan, etc.)
    """
    try:
        float(value)
        return True
    except ValueError:
        return False


def parse_input(user_input: str) -> tuple[float, str, float]:
    """Parse calculator input like '5 + 3'.

    BUG: This is incomplete and doesn't handle all cases!

    TODO: Implement proper parsing
    TODO: Add support for parentheses
    TODO: Add support for multiple operations
    """
    parts = user_input.split()
    if len(parts) != 3:
        raise ValueError("Invalid input format. Expected: 'number operator number'")

    a = float(parts[0])
    operator = parts[1]
    b = float(parts[2])

    return a, operator, b
