"""Tests for TokenBucketRateLimiter and BudgetManager rate limiting."""

import threading
import time
import pytest

from cloud_bean.judge.budget import BudgetManager, ReservationStatus
from cloud_bean.judge.rate_limiter import TokenBucketRateLimiter


def test_rate_limiter_validation():
    with pytest.raises(ValueError, match="rpm_limit must be positive"):
        TokenBucketRateLimiter(rpm_limit=0)

    with pytest.raises(ValueError, match="tpm_limit must be positive"):
        TokenBucketRateLimiter(tpm_limit=-10)

    with pytest.raises(ValueError, match="burst_multiplier must be >= 1.0"):
        TokenBucketRateLimiter(burst_multiplier=0.5)


def test_rate_limiter_acquisition_and_depletion():
    limiter = TokenBucketRateLimiter(rpm_limit=60.0, tpm_limit=6000.0, burst_multiplier=1.0)
    # Starts with 60 requests and 6000 tokens
    stats = limiter.stats()
    assert stats["available_requests"] == 60.0
    assert stats["available_tokens"] == 6000.0

    # Acquire 1 request and 2000 tokens
    assert limiter.acquire(tokens=2000) is True
    stats2 = limiter.stats()
    assert stats2["available_requests"] == 59.0
    assert stats2["available_tokens"] == 4000.0

    # Acquire remaining 4000 tokens
    assert limiter.acquire(tokens=4000) is True

    # Next token acquisition should fail non-blocking
    assert limiter.acquire(tokens=500, timeout=0.0) is False
    assert limiter.get_wait_time(tokens=500) > 0.0


def test_rate_limiter_refill():
    # 60 RPM = 1 request per second, 6000 TPM = 100 tokens per second
    limiter = TokenBucketRateLimiter(rpm_limit=60.0, tpm_limit=6000.0)
    # Drain tokens
    limiter.acquire(tokens=6000)
    assert limiter.acquire(tokens=100, timeout=0.0) is False

    # Simulate elapsed time of 0.2s (+20 tokens)
    simulated_now = limiter._last_refill + 0.2
    wait = limiter.get_wait_time(tokens=10, now=simulated_now)
    assert wait == 0.0  # enough refilled


def test_rate_limiter_thread_safety():
    # 600 RPM, 60000 TPM
    limiter = TokenBucketRateLimiter(rpm_limit=600.0, tpm_limit=60000.0)
    num_threads = 10
    tokens_per_req = 100
    acquired_count = 0
    lock = threading.Lock()

    def worker():
        nonlocal acquired_count
        for _ in range(20):
            if limiter.acquire(tokens=tokens_per_req, timeout=0.1):
                with lock:
                    acquired_count += 1

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert acquired_count > 0
    stats = limiter.stats()
    assert stats["available_requests"] >= 0.0
    assert stats["available_tokens"] >= 0.0


def test_budget_manager_with_rate_limiter():
    # Strict limiter: only 1 request capacity
    limiter = TokenBucketRateLimiter(rpm_limit=1.0, tpm_limit=2000.0, burst_multiplier=1.0)
    bm = BudgetManager(max_budget_usd=10.00, rate_limiter=limiter)

    ledger = bm.get_ledger()
    assert ledger.rate_limits.rpm_limit == 1.0
    assert ledger.rate_limits.tpm_limit == 2000.0

    # First reservation succeeds
    res1 = bm.reserve(estimated_cost_usd=0.05, estimated_tokens=1500)
    assert res1.success is True
    assert res1.status == ReservationStatus.RESERVED

    # Second reservation is immediately rate-limited
    res2 = bm.reserve(estimated_cost_usd=0.05, estimated_tokens=1500, timeout=0.0)
    assert res2.success is False
    assert res2.status == ReservationStatus.RATE_LIMITED
