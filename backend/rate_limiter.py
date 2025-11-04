"""
Rate limiting configuration and utilities

Implements rate limiting to prevent abuse and DoS attacks.
Uses slowapi for FastAPI-compatible rate limiting.
"""
import os
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


# Rate limit configuration
# General API endpoints: 100 requests per minute per IP
GENERAL_RATE_LIMIT = os.getenv("RATE_LIMIT_GENERAL", "100/minute")

# Search endpoints: 30 requests per minute per IP (more restrictive)
SEARCH_RATE_LIMIT = os.getenv("RATE_LIMIT_SEARCH", "30/minute")

# Write endpoints (POST/PUT/DELETE): 20 requests per minute per IP
WRITE_RATE_LIMIT = os.getenv("RATE_LIMIT_WRITE", "20/minute")

# Create limiter instance
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[GENERAL_RATE_LIMIT],
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
    strategy="fixed-window"
)


def get_rate_limit_handler():
    """
    Get the rate limit exceeded handler

    Returns:
        Handler function for rate limit exceeded errors
    """
    return _rate_limit_exceeded_handler
