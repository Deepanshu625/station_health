"""Custom DRF exception handling: one error shape and code set for every
non-2xx response. Never leaks stack traces to the client.
"""

from __future__ import annotations

import logging

from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("stations.errors")


class ServiceError(drf_exceptions.APIException):
    """Base class for our own business-logic errors (as opposed to DRF's)."""

    code = "internal_error"
    default_message = "An unexpected error occurred."

    def __init__(self, message: str | None = None, details: dict | None = None):
        self.message = message or self.default_message
        self.details = details
        super().__init__(detail=self.message)


class BatchTooLarge(ServiceError):
    status_code = 400
    code = "batch_too_large"
    default_message = "Batch exceeds the maximum allowed size."


class InvalidQueryParam(ServiceError):
    status_code = 400
    code = "invalid_query_param"
    default_message = "One or more query parameters are invalid."


class StationNotFound(ServiceError):
    status_code = 404
    code = "station_not_found"
    default_message = "Station not found."


class MalformedJson(ServiceError):
    status_code = 400
    code = "malformed_json"
    default_message = "Request body is not valid JSON."


class BatchValidationError(ServiceError):
    """Raised when one or more items in a report batch fail validation."""

    status_code = 400
    code = "validation_error"
    default_message = "One or more reports are invalid; nothing was stored."


_DRF_EXCEPTION_CODES: dict[type[Exception], tuple[str, int]] = {
    drf_exceptions.ValidationError: ("validation_error", 400),
    drf_exceptions.ParseError: ("malformed_json", 400),
    drf_exceptions.NotAuthenticated: ("not_authenticated", 401),
    drf_exceptions.AuthenticationFailed: ("not_authenticated", 401),
    drf_exceptions.PermissionDenied: ("not_authenticated", 401),
    drf_exceptions.UnsupportedMediaType: ("unsupported_media_type", 415),
    drf_exceptions.NotFound: ("station_not_found", 404),
    drf_exceptions.MethodNotAllowed: ("validation_error", 400),
}


def exception_handler(exc, context):
    """Maps DRF/business exceptions to the single error envelope."""
    request = context.get("request")
    request_id = getattr(request, "request_id", None)

    if isinstance(exc, ServiceError):
        code = exc.code
        message = exc.message
        details = exc.details
        status_code = exc.status_code
    elif type(exc) in _DRF_EXCEPTION_CODES:
        code, status_code = _DRF_EXCEPTION_CODES[type(exc)]
        message = _summarize(exc)
        details = exc.detail if isinstance(exc.detail, dict | list) else None
    elif isinstance(exc, Http404):
        code, status_code, message, details = "station_not_found", 404, "Not found.", None
    else:
        response = drf_exception_handler(exc, context)
        if response is not None:
            code = "internal_error"
            status_code = response.status_code
            message = str(exc)
            details = None
        else:
            logger.exception("unhandled exception", extra={"request_id": request_id})
            code, status_code, message, details = (
                "internal_error",
                500,
                "An unexpected error occurred.",
                None,
            )

    if code == "validation_error":
        logger.warning(
            "validation failed",
            extra={"request_id": request_id, "details": details, "error_message": message},
        )

    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return Response(body, status=status_code)


def _summarize(exc: drf_exceptions.APIException) -> str:
    detail = exc.detail
    if isinstance(detail, list) and detail:
        return str(detail[0])
    if isinstance(detail, dict) and detail:
        return "Validation failed for one or more fields."
    return str(detail)
