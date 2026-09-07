"""Keeps the container running and executes flows on an interval.

This is scaffolding: it runs the healthcheck flow locally every 60s so the
container has visible, working behavior with zero external config. Real
recurring flows are scheduled by the separate `scheduler` service (cron via
supercronic - see docs/scheduling.md), not by this container.
"""

import time

from flows.hello_flow import healthcheck_flow

if __name__ == "__main__":
    while True:
        result = healthcheck_flow()
        print(f"[prefect-worker] healthcheck flow ran: {result}", flush=True)
        time.sleep(60)
