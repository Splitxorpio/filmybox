"""Historical Reddit sentiment backfill for released movies, restricted to
the population that matters for GBT training: budget_usd present AND a
box_office_totals row (mirrors db.get_movies_for_training's core filter,
per the planning doc) - so this becomes a usable model feature, not just a
display curiosity for a handful of movies. Oldest-first, same reasoning as
critic_score_backfill.py: closes historical coverage gaps rather than
re-covering recent releases that already show up first under any other
ordering.

Separate flow from reddit_buzz_upcoming.py (see that module's docstring)
because this is the large, quota-throttled batch job - Reddit's OAuth limit
for script apps is roughly 60 requests/minute, so MAX_PER_RUN keeps a single
run to a few minutes rather than trying to drain the whole backlog in one
sitting; re-run this once per day (or whenever) until it reports 0
remaining, same pattern as critic_score_backfill.py.

Run manually (module form - see tmdb_backfill.py's docstring for why, and
for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.reddit_sentiment_backfill
"""

import os

from db import get_connection, get_movies_for_reddit_backfill, upsert_sentiment_snapshot
from reddit_client import RedditAuthError, RedditRateLimited, search_movie_mentions
from sentiment_scoring import summarize_items

MAX_PER_RUN = 250


def reddit_sentiment_backfill_flow():
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT", "filmybox/0.1")
    if not client_id or not client_secret:
        print("[reddit-sentiment-backfill] REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET not set, skipping")
        return

    conn = get_connection()
    processed = 0
    try:
        with conn.cursor() as cur:
            movies = get_movies_for_reddit_backfill(cur, MAX_PER_RUN)
        print(f"[reddit-sentiment-backfill] {len(movies)} movies to fetch this run (cap {MAX_PER_RUN})")

        for movie in movies:
            year = movie["release_date"].year if movie["release_date"] else None
            try:
                posts = search_movie_mentions(
                    movie["title"], year, client_id, client_secret, user_agent
                )
            except RedditRateLimited:
                print(
                    f"[reddit-sentiment-backfill] rate limited after "
                    f"{processed}/{len(movies)} - stopping"
                )
                break
            except RedditAuthError as exc:
                print(f"[reddit-sentiment-backfill] auth error, stopping run: {exc}")
                break
            except Exception as exc:
                print(f"[reddit-sentiment-backfill] error fetching '{movie['title']}': {exc}")
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
                    stage="post_release",
                    sentiment_score=summary["sentiment_score"],
                    volume=summary["volume"],
                    avg_engagement_score=summary["avg_engagement_score"],
                    raw_sample_ids=summary["sample_ids"],
                )
            conn.commit()

            processed += 1
            if processed % 25 == 0:
                print(f"[reddit-sentiment-backfill] processed {processed}/{len(movies)}")
    finally:
        conn.close()

    print(f"[reddit-sentiment-backfill] done - {processed} processed")


if __name__ == "__main__":
    reddit_sentiment_backfill_flow()
