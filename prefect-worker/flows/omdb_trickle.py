"""OMDb critic-score background trickle: fills in critic_scores for movies
not yet viewed (and thus not yet fetched on-demand by the API - see
api/app/routers/movies.py). OMDb's free tier caps at 1,000 requests/day with
no way through it in one sitting, so this deliberately processes at most
MAX_PER_RUN per invocation and stops immediately if OMDb signals its daily
limit, rather than treating this like the one-shot TMDb/BOM backfills.

Run manually, once per day (module form - see tmdb_backfill.py's docstring
for why, and for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.omdb_trickle

A real daily schedule is a Prefect Cloud concern once that's configured.
"""

import os

from db import get_connection, get_movies_missing_critic_scores, upsert_critic_scores
from omdb_client import OMDbRateLimited, fetch_critic_scores

# Leaves headroom under OMDb's 1,000/day cap for on-demand API traffic
# hitting the same key.
MAX_PER_RUN = 900


def omdb_trickle_flow():
    api_key = os.environ.get("OMDB_API_KEY")
    if not api_key:
        print("[omdb-trickle] OMDB_API_KEY not set, skipping")
        return

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            movies = get_movies_missing_critic_scores(cur, MAX_PER_RUN)
        print(f"[omdb-trickle] {len(movies)} movies to fetch this run (cap {MAX_PER_RUN})")

        processed = 0
        for movie_id, imdb_id in movies:
            try:
                scores = fetch_critic_scores(imdb_id, api_key)
            except OMDbRateLimited:
                print(f"[omdb-trickle] daily limit reached after {processed}/{len(movies)} - stopping")
                break
            except Exception as exc:
                print(f"[omdb-trickle] error fetching {imdb_id}: {exc}")
                continue

            if scores is not None:
                with conn.cursor() as cur:
                    upsert_critic_scores(cur, movie_id, scores)
                conn.commit()

            processed += 1
            if processed % 100 == 0:
                print(f"[omdb-trickle] processed {processed}/{len(movies)}")
    finally:
        conn.close()

    print(f"[omdb-trickle] done - {processed} processed")


if __name__ == "__main__":
    omdb_trickle_flow()
