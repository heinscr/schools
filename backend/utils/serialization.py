"""
Serialization utilities for converting Python objects to JSON-compatible formats
"""
from decimal import Decimal


def decimal_to_float(obj):
    """
    Convert Decimal objects to float for JSON serialization

    Args:
        obj: Object to convert (if it's a Decimal)

    Returns:
        float: Converted value if obj is Decimal

    Raises:
        TypeError: If obj is not a Decimal
    """
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError
