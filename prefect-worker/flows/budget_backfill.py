"""Wikidata budget backfill: fills in movies.budget_usd for movies TMDb
never had a budget for - a real gap that skews heavily international
(TMDb's crowd-sourced budget data is Hollywood-centric), permanently
excluding ~a third of the corpus from every ROI-based verdict.

Partial-coverage supplement, not a complete fix: only recovers budgets
Wikidata has recorded in USD (see wikidata_client.py's docstring for why
non-USD entries are skipped rather than converted) - many of the
international titles that motivated this search still won't be covered.

Batched via Wikidata's SPARQL VALUES clause (50 imdb ids/query - trimmed
down from a planned 100 after hitting an active WDQS-outage-triggered
throttle at that size), so the whole backlog clears in one run, unlike the
OMDb critic-score backfill's multi-day trickle (no comparable daily cap
here).

Run manually (module form, see tmdb_backfill.py's docstring for why, and
for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.budget_backfill
"""

import time

from db import get_connection, get_movies_missing_budget, update_movie_budget
from wikidata_client import WikidataRateLimited, fetch_budgets

BATCH_SIZE = 50
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 65  # Wikidata's observed outage-mode throttle is 1 req/min


def budget_backfill_flow():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            movies = get_movies_missing_budget(cur)
        print(f"[budget-backfill] {len(movies)} movies missing a budget")

        by_imdb_id = {imdb_id: movie_id for movie_id, imdb_id in movies}
        imdb_ids = list(by_imdb_id)

        matched = 0
        for i in range(0, len(imdb_ids), BATCH_SIZE):
            batch = imdb_ids[i : i + BATCH_SIZE]
            budgets = None
            for attempt in range(MAX_RETRIES):
                try:
                    budgets = fetch_budgets(batch)
                    break
                except WikidataRateLimited:
                    print(
                        f"[budget-backfill] rate-limited on batch {i} "
                        f"(attempt {attempt + 1}/{MAX_RETRIES}) - waiting {RETRY_BACKOFF_SECONDS}s"
                    )
                    time.sleep(RETRY_BACKOFF_SECONDS)
                except Exception as exc:
                    print(f"[budget-backfill] error fetching batch starting at {i}: {exc}")
                    break
            if budgets is None:
                print(f"[budget-backfill] giving up on batch {i} after {MAX_RETRIES} attempts - rerun later to resume")
                continue

            with conn.cursor() as cur:
                for imdb_id, budget_usd in budgets.items():
                    update_movie_budget(cur, by_imdb_id[imdb_id], budget_usd)
                    matched += 1
            conn.commit()

            print(f"[budget-backfill] processed {min(i + BATCH_SIZE, len(imdb_ids))}/{len(imdb_ids)}")
    finally:
        conn.close()

    print(f"[budget-backfill] done - {matched} of {len(movies)} movies matched")


if __name__ == "__main__":
    budget_backfill_flow()
