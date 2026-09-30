"""
Custom DRF exception handler.
Returns consistent error envelopes for all API errors.
"""
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Wraps DRF's default exception handler.

    All errors returned as:
    {
        "error": {
            "code": "ERROR_CODE",
            "message": "Human readable message",
            "details": {...}   # optional field-level errors
        }
    }
    """
    # Let DRF handle the response first
    response = exception_handler(exc, context)

    if response is not None:
        error_payload = {
            "error": {
                "code": _get_error_code(exc, response),
                "message": _get_error_message(exc, response),
            }
        }
        # Include field-level validation errors in details
        if isinstance(response.data, dict) and any(
            isinstance(v, list) for v in response.data.values()
        ):
            error_payload["error"]["details"] = response.data

        response.data = error_payload
        return response

    # Handle Django validation errors not caught by DRF
    if isinstance(exc, DjangoValidationError):
        logger.warning("Unhandled Django validation error", exc_info=True)
        return Response(
            {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(exc),
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Unexpected error — log it
    logger.error("Unhandled exception in API view", exc_info=True)
    return None


def _get_error_code(exc, response) -> str:
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_SERVER_ERROR",
    }
    # Use detail.code if available (e.g., simplejwt sets specific codes)
    if hasattr(exc, "detail") and hasattr(exc.detail, "code"):
        return str(exc.detail.code).upper()
    return code_map.get(response.status_code, "ERROR")


def _get_error_message(exc, response) -> str:
    if hasattr(exc, "detail"):
        if isinstance(exc.detail, list):
            return str(exc.detail[0]) if exc.detail else "An error occurred"
        if isinstance(exc.detail, dict):
            # Field errors — pick first
            first_key = next(iter(exc.detail))
            first_val = exc.detail[first_key]
            return f"{first_key}: {first_val[0] if isinstance(first_val, list) else first_val}"
        return str(exc.detail)
    return str(exc)
