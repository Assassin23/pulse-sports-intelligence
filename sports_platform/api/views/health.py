"""
Health check views.
These endpoints are unauthenticated and used by load balancers and monitoring.
"""
import logging

from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """
    Lightweight liveness probe.
    Returns 200 immediately if the process is running.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class ReadinessView(APIView):
    """
    Readiness probe — checks all critical dependencies.
    Returns 200 only when the service is ready to handle traffic.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        checks: dict[str, str] = {}
        overall = True

        # PostgreSQL
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            checks["postgresql"] = "ok"
        except Exception as e:
            checks["postgresql"] = f"error: {e}"
            overall = False
            logger.error("PostgreSQL health check failed", exc_info=True)

        # Redis
        try:
            from django.core.cache import cache

            cache.set("health_check", "ok", 5)
            value = cache.get("health_check")
            if value == "ok":
                checks["redis"] = "ok"
            else:
                checks["redis"] = "error: unexpected value"
                overall = False
        except Exception as e:
            checks["redis"] = f"error: {e}"
            overall = False
            logger.error("Redis health check failed", exc_info=True)

        status_code = 200 if overall else 503
        return Response(
            {
                "status": "ready" if overall else "degraded",
                "checks": checks,
            },
            status=status_code,
        )
