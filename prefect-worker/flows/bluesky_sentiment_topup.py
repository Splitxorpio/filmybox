"""Test-range companion to bluesky_sentiment_backfill.py - see
db.get_movies_for_bluesky_backfill_recent_topup for why this exists: the
main flow's oldest-first ordering (correct for closing historical gaps
first) left the GBT test-set side of the time-split with zero Bluesky
coverage at all - the mirror image of the trailer coverage-skew problem
this same pass fixed for YouTube. This flow closes that gap, restricted to
movies released on/after the ~2021-07-29 cutoff.

Run manually (module form - see tmdb_backfill.py's docstring for why, and
for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.bluesky_sentiment_topup
"""

import os

from bluesky_client import BlueskyAuthError, BlueskyRateLimited, search_movie_mentions
from db import get_connection, get_movies_for_bluesky_backfill_recent_topup, upsert_sentiment_snapshot
from sentiment_scoring import summarize_items

MAX_PER_RUN = 250


def bluesky_sentiment_topup_flow():
    handle = os.environ.get("BLUESKY_HANDLE")
    app_password = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not app_password:
        print("[bluesky-sentiment-topup] BLUESKY_HANDLE/BLUESKY_APP_PASSWORD not set, skipping")
        return

    conn = get_connection()
    processed = 0
    try:
        with conn.cursor() as cur:
            movies = get_movies_for_bluesky_backfill_recent_topup(cur, MAX_PER_RUN)
        print(f"[bluesky-sentiment-topup] {len(movies)} post-cutoff movies to fetch this run (cap {MAX_PER_RUN})")

        for movie in movies:
            year = movie["release_date"].year if movie["release_date"] else None
            try:
                items = search_movie_mentions(movie["title"], year, handle, app_password)
            except BlueskyRateLimited:
                print(f"[bluesky-sentiment-topup] rate limited after {processed}/{len(movies)} - stopping")
                break
            except BlueskyAuthError as exc:
                print(f"[bluesky-sentiment-topup] auth error, stopping run: {exc}")
                break
            except Exception as exc:
                print(f"[bluesky-sentiment-topup] error fetching '{movie['title']}': {exc}")
                continue

            summary = summarize_items(items)
            with conn.cursor() as cur:
                upsert_sentiment_snapshot(
                    cur,
                    movie["id"],
                    stage="post_release",
                    sentiment_score=summary["sentiment_score"],
                    volume=summary["volume"],
                    avg_engagement_score=summary["avg_engagement_score"],
                    raw_sample_ids=summary["sample_ids"],
                    source="bluesky",
                )
            conn.commit()

            processed += 1
            if processed % 25 == 0:
                print(f"[bluesky-sentiment-topup] processed {processed}/{len(movies)}")
    finally:
        conn.close()

    print(f"[bluesky-sentiment-topup] done - {processed} processed")


if __name__ == "__main__":
    bluesky_sentiment_topup_flow()
