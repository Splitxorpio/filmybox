"""Keeps the container running and executes flows on an interval.

This is scaffolding: it runs the healthcheck flow locally every 60s so the
container has visible, working behavior with zero external config. Once a
Prefect Cloud workspace/API key is set (PREFECT_API_KEY / PREFECT_API_URL in
.env), swap this loop for `prefect deploy` + `prefect worker start`, or add
`.serve()` calls on real flows.
"""

import time

from flows.hello_flow import healthcheck_flow

if __name__ == "__main__":
    while True:
        result = healthcheck_flow()
        print(f"[prefect-worker] healthcheck flow ran: {result}", flush=True)
        time.sleep(60)
