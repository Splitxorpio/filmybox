"""Cron wrapper that runs a flow module and posts a webhook alert if it fails.

Usage (from the crontab):
    python run_job.py flows.omdb_trickle

Output is streamed straight through to this process's stdout so
`docker compose logs scheduler` looks the same as before. The alert fires on
a nonzero exit or a crash; a flow that stops cleanly on a rate limit (exit 0)
is not treated as a failure. Alerts go to an ntfy.sh topic (NTFY_TOPIC, on
the server at NTFY_URL, default https://ntfy.sh); if unset, failures are just
logged.
"""

import collections
import os
import subprocess
import sys

import httpx

TAIL_LINES = 15


def send_alert(job, code, tail):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print(f"[run_job] {job} failed (exit {code}); NTFY_TOPIC not set, no alert sent")
        return
    base = os.environ.get("NTFY_URL", "https://ntfy.sh").rstrip("/")
    try:
        httpx.post(
            f"{base}/{topic}",
            content=tail[-3000:].encode(),
            headers={
                "Title": f"filmybox: {job} failed (exit {code})",
                "Priority": "high",
                "Tags": "rotating_light",
            },
            timeout=10,
        ).raise_for_status()
    except httpx.HTTPError as e:
        print(f"[run_job] could not send alert for {job}: {e}")


def main():
    job = sys.argv[1]
    tail = collections.deque(maxlen=TAIL_LINES)
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", job],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in proc.stdout:
        print(line, end="", flush=True)
        tail.append(line.rstrip())
    code = proc.wait()
    if code != 0:
        send_alert(job, code, "\n".join(tail))
    sys.exit(code)


if __name__ == "__main__":
    main()
