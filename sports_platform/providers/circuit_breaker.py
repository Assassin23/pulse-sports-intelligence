"""
Circuit breaker implementation for provider fault isolation.

States:
  CLOSED   → Normal: requests flow through.
  OPEN     → Failing: requests fail fast with ProviderCircuitOpenError.
  HALF_OPEN → Recovery probe: one request allowed; success → CLOSED, failure → OPEN.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import Lock
from typing import Optional

from sports_platform.providers.base import ProviderCircuitOpenError

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """
    Per-provider circuit breaker with thread-safe state transitions.

    Usage:
        cb = CircuitBreaker(name="api_football")
        result = cb.call(provider.fetch_upcoming_fixtures, sport="football")
    """

    name: str
    failure_threshold: int = 5
    recovery_timeout: timedelta = field(default_factory=lambda: timedelta(minutes=5))

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False, repr=False)
    _failure_count: int = field(default=0, init=False, repr=False)
    _last_failure_at: Optional[datetime] = field(default=None, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def call(self, func, *args, **kwargs):
        """
        Execute func through the circuit breaker.
        Raises ProviderCircuitOpenError if circuit is OPEN and recovery window
        has not yet elapsed.
        """
        with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = datetime.now(tz=timezone.utc) - self._last_failure_at
                if elapsed >= self.recovery_timeout:
                    logger.info(
                        "Circuit breaker probing recovery",
                        extra={"provider": self.name},
                    )
                    self._state = CircuitState.HALF_OPEN
                else:
                    raise ProviderCircuitOpenError(
                        f"Circuit OPEN for provider '{self.name}'. "
                        f"Retry in {(self.recovery_timeout - elapsed).seconds}s."
                    )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except ProviderCircuitOpenError:
            raise
        except Exception as exc:
            self._on_failure(exc)
            raise

    def _on_success(self):
        with self._lock:
            if self._state != CircuitState.CLOSED:
                logger.info(
                    "Circuit breaker CLOSED after recovery",
                    extra={"provider": self.name},
                )
            self._failure_count = 0
            self._state = CircuitState.CLOSED
            self._last_failure_at = None

    def _on_failure(self, exc: Exception):
        with self._lock:
            self._failure_count += 1
            self._last_failure_at = datetime.now(tz=timezone.utc)
            if self._failure_count >= self.failure_threshold:
                if self._state != CircuitState.OPEN:
                    logger.warning(
                        "Circuit breaker OPENED",
                        extra={
                            "provider": self.name,
                            "failure_count": self._failure_count,
                            "error": str(exc),
                        },
                    )
                self._state = CircuitState.OPEN
            else:
                logger.warning(
                    "Circuit breaker failure recorded",
                    extra={
                        "provider": self.name,
                        "failure_count": self._failure_count,
                        "threshold": self.failure_threshold,
                        "error": str(exc),
                    },
                )

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def reset(self):
        """Manually reset circuit to CLOSED (useful in tests)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_at = None

