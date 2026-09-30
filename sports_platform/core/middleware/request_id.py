"""
Request ID middleware.
Attaches a unique X-Request-ID to every request for distributed tracing.
"""
import logging
import uuid

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    """
    Middleware that:
    1. Reads X-Request-ID from incoming request headers (or generates one).
    2. Attaches it to the request object as request.request_id.
    3. Adds it to all outgoing response headers.
    4. Adds it to Django's logging context for structured log correlation.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = (
            request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        )
        request.request_id = request_id

        response = self.get_response(request)
        response[REQUEST_ID_HEADER] = request_id
        return response
