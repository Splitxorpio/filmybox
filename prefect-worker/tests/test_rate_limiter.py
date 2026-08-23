import time

from rate_limiter import RateLimiter


def test_wait_enforces_minimum_spacing():
    limiter = RateLimiter(max_per_second=10)  # 100ms min interval

    limiter.wait()
    start = time.monotonic()
    limiter.wait()
    elapsed = time.monotonic() - start

    assert elapsed >= 0.1


def test_wait_does_not_delay_when_interval_already_elapsed():
    limiter = RateLimiter(max_per_second=10)

    limiter.wait()
    time.sleep(0.15)  # already past the 100ms min interval
    start = time.monotonic()
    limiter.wait()
    elapsed = time.monotonic() - start

    assert elapsed < 0.05
