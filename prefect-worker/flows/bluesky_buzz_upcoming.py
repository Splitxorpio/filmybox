"""Pre-release Bluesky "buzz" snapshot for every movie that hasn't released
yet. Mirrors reddit_buzz_upcoming.py exactly - see that module's docstring
for the full reasoning (small population, re-run often/cheaply, upserts in
place rather than skipping already-covered movies).

Run manually (module form - see tmdb_backfill.py's docstring for why, and
for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.bluesky_buzz_upcoming
"""

import os

from bluesky_client import BlueskyAuthError, BlueskyRateLimited, search_movie_mentions
from db import get_connection, get_upcoming_movies_for_sentiment, upsert_sentiment_snapshot
from sentiment_scoring import summarize_items


def bluesky_buzz_upcoming_flow():
    handle = os.environ.get("BLUESKY_HANDLE")
    app_password = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not app_password:
        print("[bluesky-buzz-upcoming] BLUESKY_HANDLE/BLUESKY_APP_PASSWORD not set, skipping")
        return

    conn = get_connection()
    processed = 0
    try:
        with conn.cursor() as cur:
            movies = get_upcoming_movies_for_sentiment(cur)
        print(f"[bluesky-buzz-upcoming] {len(movies)} upcoming movies to refresh")

        for movie in movies:
            year = movie["release_date"].year if movie["release_date"] else None
            try:
                items = search_movie_mentions(movie["title"], year, handle, app_password)
            except BlueskyRateLimited:
                print(f"[bluesky-buzz-upcoming] rate limited after {processed}/{len(movies)} - stopping")
                break
            except BlueskyAuthError as exc:
                print(f"[bluesky-buzz-upcoming] auth error, stopping run: {exc}")
                break
            except Exception as exc:
                print(f"[bluesky-buzz-upcoming] error fetching '{movie['title']}': {exc}")
                continue

            summary = summarize_items(items)
            with conn.cursor() as cur:
                upsert_sentiment_snapshot(
                    cur,
                    movie["id"],
                    stage="pre_release",
                    sentiment_score=summary["sentiment_score"],
                    volume=summary["volume"],
                    avg_engagement_score=summary["avg_engagement_score"],
                    raw_sample_ids=summary["sample_ids"],
                    source="bluesky",
                )
            conn.commit()

            processed += 1
            if processed % 25 == 0:
                print(f"[bluesky-buzz-upcoming] processed {processed}/{len(movies)}")
    finally:
        conn.close()

    print(f"[bluesky-buzz-upcoming] done - {processed} processed")


if __name__ == "__main__":
    bluesky_buzz_upcoming_flow()
