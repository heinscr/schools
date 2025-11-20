"""
Tests for serialization utilities
"""
import sys
from pathlib import Path
from decimal import Decimal
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.serialization import decimal_to_float


class TestDecimalToFloat:
    """Tests for decimal_to_float function"""

    def test_decimal_to_float_conversion(self):
        """Test converting Decimal to float"""
        decimal_value = Decimal("123.45")
        result = decimal_to_float(decimal_value)

        assert isinstance(result, float)
        assert result == 123.45

    def test_decimal_to_float_integer_decimal(self):
        """Test converting integer Decimal to float"""
        decimal_value = Decimal("100")
        result = decimal_to_float(decimal_value)

        assert isinstance(result, float)
        assert result == 100.0

    def test_decimal_to_float_small_value(self):
        """Test converting small Decimal to float"""
        decimal_value = Decimal("0.001")
        result = decimal_to_float(decimal_value)

        assert isinstance(result, float)
        assert result == 0.001

    def test_decimal_to_float_large_value(self):
        """Test converting large Decimal to float"""
        decimal_value = Decimal("999999.99")
        result = decimal_to_float(decimal_value)

        assert isinstance(result, float)
        assert result == 999999.99

    def test_decimal_to_float_negative(self):
        """Test converting negative Decimal to float"""
        decimal_value = Decimal("-50.25")
        result = decimal_to_float(decimal_value)

        assert isinstance(result, float)
        assert result == -50.25

    def test_decimal_to_float_zero(self):
        """Test converting zero Decimal to float"""
        decimal_value = Decimal("0")
        result = decimal_to_float(decimal_value)

        assert isinstance(result, float)
        assert result == 0.0

    def test_decimal_to_float_raises_for_non_decimal(self):
        """Test that TypeError is raised for non-Decimal objects"""
        with pytest.raises(TypeError):
            decimal_to_float(123.45)

        with pytest.raises(TypeError):
            decimal_to_float("123.45")

        with pytest.raises(TypeError):
            decimal_to_float(123)

        with pytest.raises(TypeError):
            decimal_to_float(None)
