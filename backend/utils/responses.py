"""
HTTP response utilities for Lambda functions
"""
import json
from typing import Any, Dict
from .serialization import decimal_to_float


def create_response(status_code: int, body: Any, additional_headers: Dict[str, str] = None) -> Dict[str, Any]:
    """
    Create a standardized API Gateway Lambda response

    Args:
        status_code: HTTP status code
        body: Response body (will be JSON serialized)
        additional_headers: Optional additional headers to include

    Returns:
        Dict formatted for API Gateway Lambda proxy integration
    """
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
    }

    if additional_headers:
        headers.update(additional_headers)

    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps(body, default=decimal_to_float)
    }
