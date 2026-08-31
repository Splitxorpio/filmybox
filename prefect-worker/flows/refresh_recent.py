"""Refreshes critic/audience signal for recently-released (or upcoming)
movies only - a movie fetched from OMDb right after release may predate
most reviews, and TMDb's vote_average/vote_count (a supplementary
audience-sentiment signal, not a critic score) keeps accumulating votes
over time. Older movies' RT/Metacritic gaps are inherent to OMDb's own data
(confirmed by direct spot-check against the raw API response), not
something a refresh fixes, so this deliberately stays narrow rather than
re-checking the whole corpus.

Run manually, periodically (module form - see tmdb_backfill.py's docstring
for why, and for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.refresh_recent
"""

import os

from prefect import flow

from db import (
    ensure_critic_scores_row,
    get_connection,
    get_recent_movies,
    update_tmdb_votes,
    upsert_critic_scores,
)
from omdb_client import OMDbRateLimited, fetch_critic_scores
from tmdb_client import TMDbClient

RECENT_DAYS = 90


@flow(name="filmybox-refresh-recent", log_prints=True)
def refresh_recent_flow():
    omdb_api_key = os.environ.get("OMDB_API_KEY")
    tmdb_client = TMDbClient()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            movies = get_recent_movies(cur, RECENT_DAYS)
        print(f"[refresh-recent] {len(movies)} movies released within {RECENT_DAYS} days")

        omdb_limited = False
        for movie_id, tmdb_id, imdb_id in movies:
            with conn.cursor() as cur:
                ensure_critic_scores_row(cur, movie_id)
            conn.commit()

            if not omdb_limited and omdb_api_key:
                try:
                    scores = fetch_critic_scores(imdb_id, omdb_api_key)
                    if scores is not None:
                        with conn.cursor() as cur:
                            upsert_critic_scores(cur, movie_id, scores)
                        conn.commit()
                except OMDbRateLimited:
                    omdb_limited = True
                    print("[refresh-recent] OMDb daily limit reached - skipping OMDb re-check for the rest of this run")
                except Exception as exc:
                    print(f"[refresh-recent] error fetching OMDb for {imdb_id}: {exc}")

            try:
                detail = tmdb_client.get_movie_detail(tmdb_id)
                with conn.cursor() as cur:
                    update_tmdb_votes(cur, movie_id, detail.get("vote_average"), detail.get("vote_count"))
                conn.commit()
            except Exception as exc:
                print(f"[refresh-recent] error fetching TMDb votes for tmdb_id={tmdb_id}: {exc}")
    finally:
        conn.close()

    print("[refresh-recent] done")


if __name__ == "__main__":
    refresh_recent_flow()
