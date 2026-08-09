"""Pre-release Reddit "buzz" snapshot for every movie that hasn't released
yet. Separate from reddit_sentiment_backfill.py (the historical/training
batch job) on purpose: this population is small (only unreleased titles -
typically low hundreds at most) and the whole point of pre-release buzz is
that it changes as a movie gets closer to release, so it's meant to be
re-run often (e.g. daily) and cheaply re-upserts every movie's snapshot in
place, rather than skipping ones already covered. The historical backfill,
by contrast, is a large one-time-ish quota-throttled catchup job that skips
movies it's already done.

Run manually (module form - see tmdb_backfill.py's docstring for why, and
for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.reddit_buzz_upcoming
"""

import os

from db import get_connection, get_upcoming_movies_for_sentiment, upsert_sentiment_snapshot
from reddit_client import RedditAuthError, RedditRateLimited, search_movie_mentions
from sentiment_scoring import summarize_items


def reddit_buzz_upcoming_flow():
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT", "filmybox/0.1")
    if not client_id or not client_secret:
        print("[reddit-buzz-upcoming] REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET not set, skipping")
        return

    conn = get_connection()
    processed = 0
    try:
        with conn.cursor() as cur:
            movies = get_upcoming_movies_for_sentiment(cur)
        print(f"[reddit-buzz-upcoming] {len(movies)} upcoming movies to refresh")

        for movie in movies:
            year = movie["release_date"].year if movie["release_date"] else None
            try:
                posts = search_movie_mentions(
                    movie["title"], year, client_id, client_secret, user_agent
                )
            except RedditRateLimited:
                print(f"[reddit-buzz-upcoming] rate limited after {processed}/{len(movies)} - stopping")
                break
            except RedditAuthError as exc:
                print(f"[reddit-buzz-upcoming] auth error, stopping run: {exc}")
                break
            except Exception as exc:
                print(f"[reddit-buzz-upcoming] error fetching '{movie['title']}': {exc}")
                continue

            items = [
                {"id": p["id"], "text": f"{p['title']} {p.get('selftext', '')}", "engagement": p.get("score", 0)}
                for p in posts
            ]
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
                )
            conn.commit()

            processed += 1
            if processed % 25 == 0:
                print(f"[reddit-buzz-upcoming] processed {processed}/{len(movies)}")
    finally:
        conn.close()

    print(f"[reddit-buzz-upcoming] done - {processed} processed")


if __name__ == "__main__":
    reddit_buzz_upcoming_flow()
