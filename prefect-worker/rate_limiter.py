import threading
import time


class RateLimiter:
    """Blocking token-spacing limiter shared across all calls to one API.

    Not per-source config (TMDb/YouTube/Reddit each get their own instance)
    since their quota shapes differ.
    """

    def __init__(self, max_per_second: float):
        self._min_interval = 1.0 / max_per_second
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_for = self._min_interval - (now - self._last_call)
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last_call = time.monotonic()
