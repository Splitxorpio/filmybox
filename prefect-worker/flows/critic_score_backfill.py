"""Historical critic-score backfill, oldest-first, restricted to movies with
a budget - fixes a real coverage gap found while training gbt_v2: the
existing recency-ordered trickle (omdb_trickle.py, for dashboard freshness)
left zero movies before the GBT time-split cutoff with a critic score, so
those features had nothing to learn from (see planning doc's GBT v2
section). Different purpose from omdb_trickle.py, so a separate flow rather
than reusing it - this is a one-time-ish backfill to unlock training signal,
not an ongoing freshness concern.

OMDb's free tier caps at 1,000 requests/day with no way through it in one
sitting - same MAX_PER_RUN/stop-on-rate-limit pattern as omdb_trickle.py.

Run manually, once per day until it reports 0 remaining (module form - see
tmdb_backfill.py's docstring for why, and for why this is plain Python, not
@flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.critic_score_backfill
"""

import os

from db import get_budgeted_movies_missing_critic_scores, get_connection, upsert_critic_scores
from omdb_client import OMDbRateLimited, fetch_critic_scores

MAX_PER_RUN = 900


def critic_score_backfill_flow():
    api_key = os.environ.get("OMDB_API_KEY")
    if not api_key:
        print("[critic-score-backfill] OMDB_API_KEY not set, skipping")
        return

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            movies = get_budgeted_movies_missing_critic_scores(cur, MAX_PER_RUN)
        print(f"[critic-score-backfill] {len(movies)} budgeted movies to fetch this run (cap {MAX_PER_RUN})")

        processed = 0
        for movie_id, imdb_id in movies:
            try:
                scores = fetch_critic_scores(imdb_id, api_key)
            except OMDbRateLimited:
                print(f"[critic-score-backfill] daily limit reached after {processed}/{len(movies)} - stopping")
                break
            except Exception as exc:
                print(f"[critic-score-backfill] error fetching {imdb_id}: {exc}")
                continue

            if scores is not None:
                with conn.cursor() as cur:
                    upsert_critic_scores(cur, movie_id, scores)
                conn.commit()

            processed += 1
            if processed % 100 == 0:
                print(f"[critic-score-backfill] processed {processed}/{len(movies)}")
    finally:
        conn.close()

    print(f"[critic-score-backfill] done - {processed} processed")


if __name__ == "__main__":
    critic_score_backfill_flow()
