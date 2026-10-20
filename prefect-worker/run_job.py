"""Cron wrapper that runs a flow module and posts a webhook alert if it fails.

Usage (from the crontab):
    python run_job.py flows.omdb_trickle

Output is streamed straight through to this process's stdout so
`docker compose logs scheduler` looks the same as before. The alert fires on
a nonzero exit or a crash; a flow that stops cleanly on a rate limit (exit 0)
is not treated as a failure. ALERT_WEBHOOK_URL accepts a Discord or Slack
incoming webhook; if unset, failures are just logged.
"""

import collections
import os
import subprocess
import sys

import httpx

TAIL_LINES = 15


def send_alert(job, code, tail):
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        print(f"[run_job] {job} failed (exit {code}); ALERT_WEBHOOK_URL not set, no alert sent")
        return
    text = f"filmybox job `{job}` failed (exit {code})\n```\n{tail}\n```"[:1900]
    try:
        # "content" is Discord's field, "text" is Slack's; each ignores the other.
        httpx.post(url, json={"content": text, "text": text}, timeout=10).raise_for_status()
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
