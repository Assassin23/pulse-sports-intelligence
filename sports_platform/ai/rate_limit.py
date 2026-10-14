"""
AI Rate Limiter — Milestone 10.

Enforces 20 requests per hour per user using Redis sliding window/counter.
"""
import time
import logging
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class AIRateLimitExceeded(Exception):
    """Raised when user exceeds the AI request rate limit."""
    pass


class AIRateLimiter:
    """
    Sliding window hourly rate limiter for the AI Assistant.
    Default limit: 20 requests / hour per user.
    """

    def __init__(self, max_requests: int = None, window_seconds: int = 3600):
        self.max_requests = max_requests or getattr(settings, "AI_RATE_LIMIT_PER_HOUR", 20)
        self.window_seconds = window_seconds

    def _get_key(self, user_id: str) -> str:
        current_hour_bucket = int(time.time() // self.window_seconds)
        return f"ai:ratelimit:{user_id}:{current_hour_bucket}"

    def check_and_increment(self, user_id: str) -> int:
        """
        Increments request count for user in current hour window.
        Returns the remaining request quota.
        Raises AIRateLimitExceeded if quota exceeded.
        """
        key = self._get_key(user_id)
        try:
            current_count = cache.get(key)
            if current_count is None:
                cache.set(key, 1, timeout=self.window_seconds + 60)
                current_count = 1
            else:
                if current_count >= self.max_requests:
                    raise AIRateLimitExceeded(
                        f"Hourly AI question quota exceeded ({self.max_requests} requests/hour). Please try again later."
                    )
                try:
                    current_count = cache.incr(key)
                except Exception:
                    current_count += 1
                    cache.set(key, current_count, timeout=self.window_seconds)

            remaining = max(0, self.max_requests - current_count)
            return remaining
        except AIRateLimitExceeded:
            raise
        except Exception as e:
            logger.warning(f"Rate limiting check failed ({e}); allowing request as graceful degradation.")
            return self.max_requests
