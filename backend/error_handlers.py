"""
Error handling and sanitization utilities

Provides safe error handling that prevents information disclosure
while still being helpful for debugging in development.
"""
import os
import logging
from typing import Dict, Any
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError


# Configure logging
logger = logging.getLogger(__name__)

# Determine if we're in development mode
IS_DEVELOPMENT = os.getenv("ENVIRONMENT", "production").lower() in ["development", "dev", "local"]


def sanitize_error_message(error: Exception, default_message: str = "An error occurred") -> str:
    """
    Sanitize error messages to prevent information disclosure

    Args:
        error: The exception that occurred
        default_message: Fallback message for production

    Returns:
        Safe error message string
    """
    # In development, include more details for debugging
    if IS_DEVELOPMENT:
        return str(error)

    # In production, return generic messages
    error_type = type(error).__name__

    # Map known error types to safe messages
    safe_messages = {
        "ValidationError": "Invalid input data provided",
        "ValueError": "Invalid value provided",
        "KeyError": "Required field missing",
        "TypeError": "Invalid data type",
        "AttributeError": "Invalid operation",
        "PermissionError": "Access denied",
        "FileNotFoundError": "Resource not found",
        "ConnectionError": "Service temporarily unavailable",
        "TimeoutError": "Request timeout",
    }

    return safe_messages.get(error_type, default_message)


def create_error_response(
    status_code: int,
    error: Exception = None,
    message: str = None,
    error_code: str = None
) -> Dict[str, Any]:
    """
    Create a standardized error response

    Args:
        status_code: HTTP status code
        error: Optional exception object
        message: Optional custom message (overrides error sanitization)
        error_code: Optional error code for client-side handling

    Returns:
        Standardized error response dictionary
    """
    # Determine the error message
    if message:
        detail = message
    elif error:
        detail = sanitize_error_message(error)
    else:
        detail = "An error occurred"

    # Build response
    response = {"detail": detail}

    # Add error code if provided
    if error_code:
        response["error_code"] = error_code

    # In development, include error type and traceback
    if IS_DEVELOPMENT and error:
        response["error_type"] = type(error).__name__
        # Log the full error for debugging
        logger.error(f"Error occurred: {type(error).__name__}: {str(error)}", exc_info=True)

    return response


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Global exception handler for HTTPException
    Sanitizes error messages in production
    """
    # HTTPException already has a safe detail message
    # Just ensure we don't leak sensitive info
    detail = exc.detail

    # If detail is a dict or complex object, sanitize it
    if isinstance(detail, dict) and not IS_DEVELOPMENT:
        # Remove any potentially sensitive keys
        sensitive_keys = ["stack_trace", "traceback", "exception", "sql", "query"]
        detail = {k: v for k, v in detail.items() if k.lower() not in sensitive_keys}

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail}
    )


async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """
    Handle Pydantic validation errors
    Returns user-friendly validation error messages
    """
    errors = exc.errors()

    if IS_DEVELOPMENT:
        # In development, return full validation details
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": errors}
        )

    # In production, sanitize validation errors
    sanitized_errors = []
    for error in errors:
        # Only include field name and safe message
        field = " -> ".join(str(loc) for loc in error["loc"])
        sanitized_errors.append({
            "field": field,
            "message": error.get("msg", "Invalid value")
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": sanitized_errors}
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all exception handler for unexpected errors
    Prevents stack traces from leaking to clients
    """
    # Log the full error for debugging
    logger.error(
        f"Unhandled exception: {type(exc).__name__}: {str(exc)}",
        exc_info=True,
        extra={"path": request.url.path, "method": request.method}
    )

    # Return sanitized error response
    if IS_DEVELOPMENT:
        detail = f"{type(exc).__name__}: {str(exc)}"
    else:
        detail = "An internal error occurred. Please try again later."

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": detail}
    )


def safe_create_district_error(error: Exception) -> HTTPException:
    """
    Safely handle district creation errors

    Args:
        error: Exception from district creation

    Returns:
        HTTPException with sanitized message
    """
    # Log the actual error
    logger.error(f"District creation failed: {str(error)}", exc_info=True)

    # Return safe error
    if IS_DEVELOPMENT:
        message = str(error)
    else:
        message = "Failed to create district. Please check your input and try again."

    return HTTPException(status_code=400, detail=message)
