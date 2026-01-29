"""Tests for calculator module.

INCOMPLETE: Many edge cases are missing!
"""

import pytest
from src.calculator import Calculator


class TestCalculator:
    """Test suite for Calculator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.calc = Calculator()

    def test_add(self):
        """Test addition."""
        assert self.calc.add(2, 3) == 5
        assert self.calc.add(-1, 1) == 0
        assert self.calc.add(0, 0) == 0

    def test_subtract(self):
        """Test subtraction."""
        assert self.calc.subtract(5, 3) == 2
        assert self.calc.subtract(3, 5) == -2

    def test_multiply(self):
        """Test multiplication."""
        assert self.calc.multiply(4, 5) == 20
        assert self.calc.multiply(-2, 3) == -6

    # TODO: Add test for division by zero
    def test_divide(self):
        """Test division."""
        assert self.calc.divide(10, 2) == 5
        assert self.calc.divide(9, 3) == 3
        # Missing: test for division by zero!

    # TODO: Add test for negative square root
    def test_square_root(self):
        """Test square root."""
        assert self.calc.square_root(9) == 3
        assert self.calc.square_root(16) == 4
        # Missing: test for negative input!

    def test_power(self):
        """Test exponentiation."""
        assert self.calc.power(2, 3) == 8
        assert self.calc.power(5, 0) == 1

    # TODO: Add test for modulo by zero
    def test_modulo(self):
        """Test modulo operation."""
        assert self.calc.modulo(10, 3) == 1
        # Missing: test for modulo by zero!

    # TODO: Add tests for new features (percentage, factorial, logarithm)
