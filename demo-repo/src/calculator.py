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
        """Raise base to the power of exponent.

        Args:
            base: The base number.
            exponent: The exponent to raise the base to.

        Returns:
            base raised to the power of exponent.

        Raises:
            ValueError: If the result would be infinity (e.g. 0 ** -1).
        """
        try:
            result = base ** exponent
        except ZeroDivisionError:
            raise ValueError("Result is infinity")
        if result == float('inf') or result == float('-inf'):
            raise ValueError("Result is infinity")
        return result

    def square_root(self, x: float) -> float:
        """Calculate square root of x.

        Args:
            x: The number to compute the square root of (must be >= 0).

        Returns:
            The square root of x.

        Raises:
            ValueError: If x is negative.
        """
        if x < 0:
            raise ValueError("x must be non-negative")
        return math.sqrt(x)

    def modulo(self, a: float, b: float) -> float:
        """Return remainder of a divided by b.

        BUG: No error handling for modulo by zero!
        """
        # TODO: Add error handling
        return a % b

    def percentage(self, value: float, percent: float) -> float:
        """Return the given percentage of a value.

        Args:
            value: The base value.
            percent: The percentage to compute (must be non-negative).

        Returns:
            value * percent / 100

        Raises:
            ValueError: If percent is negative.
        """
        if percent < 0:
            raise ValueError("percent must be non-negative")
        return value * percent / 100

    def factorial(self, n: int) -> int:
        """Compute n! iteratively.

        Args:
            n: A non-negative integer.

        Returns:
            n factorial (1 for n=0).

        Raises:
            ValueError: If n is negative or not an integer.
        """
        if not isinstance(n, int):
            raise ValueError("n must be an integer")
        if n < 0:
            raise ValueError("n must be non-negative")
        result = 1
        for i in range(2, n + 1):
            result *= i
        return result

    def logarithm(self, x: float, base: float) -> float:
        """Compute log_base(x).

        Args:
            x: The argument (must be > 0).
            base: The logarithm base (must be > 0 and != 1).

        Returns:
            Logarithm of x with the given base.

        Raises:
            ValueError: If x <= 0, base <= 0, or base == 1.
        """
        if x <= 0:
            raise ValueError("x must be greater than 0")
        if base <= 0:
            raise ValueError("base must be greater than 0")
        if base == 1:
            raise ValueError("base must not be 1")
        return math.log(x, base)


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
