"""Token bucket rate limiter for Cloud LLM judge APIs (RPM & TPM).

Grounding:
- Token Bucket Algorithm (RFC 5405 / Turner 1986): Standard rate control
  algorithm in distributed cloud systems regulating bursty ingress against quotas.
- Cloud AI Provider Quotas (OpenAI / Vertex AI): Enforce dual constraints on
  Requests Per Minute (RPM) and Tokens Per Minute (TPM) to prevent HTTP 429 cascades.
"""

import threading
import time
from typing import Any, Dict, Optional


class TokenBucketRateLimiter:
    """Thread-safe dual-token bucket regulating requests and token throughput."""

    def __init__(
        self,
        rpm_limit: float = 120.0,
        tpm_limit: float = 120_000.0,
        burst_multiplier: float = 1.0,
    ) -> None:
        if rpm_limit <= 0.0:
            raise ValueError("rpm_limit must be positive")
        if tpm_limit <= 0.0:
            raise ValueError("tpm_limit must be positive")
        if burst_multiplier < 1.0:
            raise ValueError("burst_multiplier must be >= 1.0")

        self.rpm_limit = float(rpm_limit)
        self.tpm_limit = float(tpm_limit)
        self.max_requests = self.rpm_limit * burst_multiplier
        self.max_tokens = self.tpm_limit * burst_multiplier

        self.request_fill_rate = self.rpm_limit / 60.0  # requests per second
        self.token_fill_rate = self.tpm_limit / 60.0    # tokens per second

        self._lock = threading.Lock()
        self._available_requests = float(self.max_requests)
        self._available_tokens = float(self.max_tokens)
        self._last_refill = time.monotonic()

    def _refill(self, now: Optional[float] = None) -> None:
        """Add tokens proportional to elapsed time since last refill."""
        current_time = now if now is not None else time.monotonic()
        elapsed = max(0.0, current_time - self._last_refill)
        self._last_refill = current_time

        self._available_requests = min(
            self.max_requests, self._available_requests + (elapsed * self.request_fill_rate)
        )
        self._available_tokens = min(
            self.max_tokens, self._available_tokens + (elapsed * self.token_fill_rate)
        )

    def get_wait_time(self, tokens: int = 1, now: Optional[float] = None) -> float:
        """Calculate seconds to wait before the requested capacity becomes available."""
        with self._lock:
            self._refill(now)
            req_deficit = max(0.0, 1.0 - self._available_requests)
            token_deficit = max(0.0, float(tokens) - self._available_tokens)

            time_for_req = req_deficit / self.request_fill_rate if self.request_fill_rate > 0 else 0.0
            time_for_tokens = token_deficit / self.token_fill_rate if self.token_fill_rate > 0 else 0.0

            return max(time_for_req, time_for_tokens)

    def acquire(self, tokens: int = 1, timeout: float = 0.0) -> bool:
        """Attempt to acquire 1 request unit and the specified number of tokens.

        Args:
            tokens: Estimated token count required for this LLM check.
            timeout: Maximum seconds to block waiting for capacity (0.0 = non-blocking).

        Returns:
            bool: True if capacity was acquired, False if throttled/timed out.
        """
        if tokens < 0:
            raise ValueError("tokens must be non-negative")

        deadline = time.monotonic() + timeout

        while True:
            with self._lock:
                self._refill()
                if self._available_requests >= 1.0 and self._available_tokens >= float(tokens):
                    self._available_requests -= 1.0
                    self._available_tokens -= float(tokens)
                    return True

                req_deficit = max(0.0, 1.0 - self._available_requests)
                token_deficit = max(0.0, float(tokens) - self._available_tokens)
                wait_needed = max(
                    req_deficit / self.request_fill_rate,
                    token_deficit / self.token_fill_rate,
                )

            remaining_timeout = deadline - time.monotonic()
            if remaining_timeout <= 0.0 or wait_needed > remaining_timeout:
                return False

            sleep_duration = min(wait_needed, remaining_timeout)
            if sleep_duration > 0.001:
                time.sleep(sleep_duration)

    def stats(self) -> Dict[str, Any]:
        """Return snapshot statistics of the current bucket state."""
        with self._lock:
            self._refill()
            return {
                "available_requests": round(self._available_requests, 2),
                "max_requests": round(self.max_requests, 2),
                "available_tokens": round(self._available_tokens, 2),
                "max_tokens": round(self.max_tokens, 2),
                "rpm_limit": self.rpm_limit,
                "tpm_limit": self.tpm_limit,
            }
