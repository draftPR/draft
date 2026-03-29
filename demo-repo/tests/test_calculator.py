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

    def test_square_root(self):
        """Test square root."""
        assert self.calc.square_root(9) == 3
        assert self.calc.square_root(16) == 4

    def test_square_root_negative_raises(self):
        """Test that negative input raises ValueError."""
        with pytest.raises(ValueError):
            self.calc.square_root(-1)

    def test_power(self):
        """Test exponentiation."""
        assert self.calc.power(2, 3) == 8
        assert self.calc.power(5, 0) == 1
        with pytest.raises(ValueError):
            self.calc.power(0, -1)

    # TODO: Add test for modulo by zero
    def test_modulo(self):
        """Test modulo operation."""
        assert self.calc.modulo(10, 3) == 1
        # Missing: test for modulo by zero!

    def test_percentage(self):
        """Test percentage calculation."""
        assert self.calc.percentage(200, 50) == 100
        assert self.calc.percentage(100, 0) == 0
        assert self.calc.percentage(50, 10) == 5

    def test_percentage_negative_raises(self):
        """Test that negative percent raises ValueError."""
        with pytest.raises(ValueError):
            self.calc.percentage(100, -1)

    def test_factorial(self):
        """Test factorial calculation."""
        assert self.calc.factorial(0) == 1
        assert self.calc.factorial(1) == 1
        assert self.calc.factorial(5) == 120
        assert self.calc.factorial(10) == 3628800

    def test_factorial_negative_raises(self):
        """Test that negative n raises ValueError."""
        with pytest.raises(ValueError):
            self.calc.factorial(-1)

    def test_factorial_non_integer_raises(self):
        """Test that non-integer n raises ValueError."""
        with pytest.raises(ValueError):
            self.calc.factorial(2.5)

    def test_logarithm(self):
        """Test logarithm calculation."""
        assert self.calc.logarithm(100, 10) == pytest.approx(2.0)
        assert self.calc.logarithm(8, 2) == pytest.approx(3.0)
        assert self.calc.logarithm(1, 10) == pytest.approx(0.0)

    def test_logarithm_invalid_x_raises(self):
        """Test that x <= 0 raises ValueError."""
        with pytest.raises(ValueError):
            self.calc.logarithm(0, 10)
        with pytest.raises(ValueError):
            self.calc.logarithm(-1, 10)

    def test_logarithm_invalid_base_raises(self):
        """Test that base <= 0 or base == 1 raises ValueError."""
        with pytest.raises(ValueError):
            self.calc.logarithm(10, 0)
        with pytest.raises(ValueError):
            self.calc.logarithm(10, -1)
        with pytest.raises(ValueError):
            self.calc.logarithm(10, 1)
