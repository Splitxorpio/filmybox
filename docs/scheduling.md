# Scheduling

The 6 recurring maintenance flows plus `train_model.py` run automatically once a day via a `scheduler` service (`docker compose up -d scheduler` — included by default in `docker compose up -d`). It runs [supercronic](https://github.com/aptible/supercronic) against `prefect-worker/crontab`, invoking each flow exactly as `docker compose run --rm --no-deps prefect-worker python -m flows.<name>` already did manually.

## The schedule

All times UTC, staggered 5 minutes apart so the flows don't all hit their external APIs (OMDb/YouTube/Bluesky/TMDb) at once — each has consistently finished in well under a minute in practice, so tighter spacing than the original 15 minutes is safe. `train_model` gets 20 minutes of buffer after the last of the 6 (its hyperparameter grid search is the one genuinely heavier job) and runs last so it retrains on the day's freshly-landed data.

| Time (UTC) | Flow |
|---|---|
| 07:00 | `refresh_recent` |
| 07:05 | `omdb_trickle` |
| 07:10 | `stage_scan` |
| 07:15 | `youtube_comment_sentiment` |
| 07:20 | `bluesky_buzz_upcoming` |
| 07:25 | `trailer_backfill` |
| 07:45 | `train_model` |

Edit `prefect-worker/crontab` to change the schedule, then `docker compose up -d --build scheduler` to pick it up (supercronic reads the crontab once at container start, not live).

## Watching it run

```
docker compose logs -f scheduler
```

Each job's stdout/stderr goes straight to the container's own log stream — the same `print()` output you'd see running it manually.

## Running a flow ad-hoc (without waiting for its scheduled time)

Nothing changes here — the manual invocation still works exactly as before, independent of the scheduler:

```
docker compose run --rm --no-deps prefect-worker python -m flows.stage_scan
```

You can also exec directly into the running `scheduler` container to test the exact command a crontab line runs:

```
docker compose exec scheduler sh -c "cd /app && python -m flows.omdb_trickle"
```

## Validating the crontab

```
docker compose run --rm --no-deps scheduler supercronic -test /app/crontab
```

Prints `crontab is valid` or a parse error with the offending line — useful after editing `prefect-worker/crontab`.

## Why not Prefect Cloud

`prefect>=3.0,<4.0` is in `requirements.txt` and was tried first — `@flow`-decorating each flow and registering deployments via `prefect deploy`. That approach was reverted after confirming live against a real Prefect Cloud workspace that the free tier only supports `prefect:managed` work pools, not `process` (hybrid/self-hosted-worker) pools (`prefect work-pool create --type process` returns "Your plan does not support hybrid or push work pools"). `prefect:managed` runs flow code on Prefect's own infrastructure, which has no network path to this project's Postgres/Redis — both local-only, inside the Docker Compose network — so it's a structural mismatch, not just a free-tier inconvenience. Revisiting this would need either a paid Prefect Cloud plan (for a real hybrid work pool) or exposing the database to the internet, neither of which this project does.
