"""Request ID propagation for correlating one request across log lines."""

from __future__ import annotations

import logging
import time
import uuid

logger = logging.getLogger("stations.request")

REQUEST_ID_HEADER = "X-Request-ID"
_META_KEY = "HTTP_X_REQUEST_ID"


class RequestIDMiddleware:
    """Reads or creates an X-Request-ID, logs the request, and echoes it back.

    Placed early in the middleware stack so every downstream log line (via
    ``request.request_id``) and the response header carry the same ID.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get(_META_KEY) or str(uuid.uuid4())
        request.request_id = request_id

        started_at = time.monotonic()
        response = self.get_response(request)
        duration_ms = round((time.monotonic() - started_at) * 1000, 2)

        response[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
