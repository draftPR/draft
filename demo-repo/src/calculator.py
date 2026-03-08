"""Simple calculator with some bugs to demonstrate Draft.

This module contains several issues:
- No error handling for division by zero
- Negative number validation missing
- TODO: Add more operations
"""

import math


class Calculator:
    """A basic calculator with some bugs."""

    def add(self, a: float, b: float) -> float:
        """Add two numbers."""
        return a + b

    def subtract(self, a: float, b: float) -> float:
        """Subtract b from a."""
        return a - b

    def multiply(self, a: float, b: float) -> float:
        """Multiply two numbers."""
        return a * b

    def divide(self, a: float, b: float) -> float:
        """Divide a by b.

        BUG: No error handling for division by zero!
        """
        # TODO: Add error handling for division by zero
        return a / b

    def power(self, base: float, exponent: float) -> float:
        """Raise base to the power of exponent."""
        return base ** exponent

    def square_root(self, n: float) -> float:
        """Calculate square root of n.

        BUG: No validation for negative numbers!
        """
        # TODO: Validate that n is not negative
        return math.sqrt(n)

    def modulo(self, a: float, b: float) -> float:
        """Return remainder of a divided by b.

        BUG: No error handling for modulo by zero!
        """
        # TODO: Add error handling
        return a % b

    # TODO: Add percentage calculation
    # TODO: Add factorial calculation
    # TODO: Add logarithm calculation


def main():
    """Demo the calculator (has bugs!)."""
    calc = Calculator()

    print("Calculator Demo")
    print("=" * 40)

    # This works fine
    print(f"5 + 3 = {calc.add(5, 3)}")
    print(f"10 - 4 = {calc.subtract(10, 4)}")
    print(f"6 * 7 = {calc.multiply(6, 7)}")

    # This will crash! (division by zero)
    # print(f"8 / 0 = {calc.divide(8, 0)}")  # Commented to prevent crash

    # This will crash! (negative square root)
    # print(f"sqrt(-9) = {calc.square_root(-9)}")  # Commented to prevent crash

    print(f"2^8 = {calc.power(2, 8)}")
    print(f"17 % 5 = {calc.modulo(17, 5)}")


if __name__ == "__main__":
    main()
