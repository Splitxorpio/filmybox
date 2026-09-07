"""YouTube trailer-comment sentiment: the most directly on-topic thread-based
signal available - literal reactions to the trailer/teaser itself, not just
title mentions elsewhere. Covers every movie with a trailer regardless of
release status (unlike the Reddit flows' released-vs-upcoming split) since a
trailer's reception is relevant whether the movie has come out yet or not.

commentThreads.list costs 1 quota unit/call - far cheaper than the
search.list calls (100 units) trailer_backfill.py/stage_scan.py already use
for trailer discovery. Still shares the same 10,000/day budget as those two,
so MAX_PER_RUN is kept conservative rather than trying to drain the whole
backlog in one run.

Run manually (module form - see tmdb_backfill.py's docstring for why, and
for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.youtube_comment_sentiment
"""

import os

from db import get_connection, get_movies_needing_comment_sentiment, upsert_sentiment_snapshot
from sentiment_scoring import summarize_items
from youtube_client import YouTubeQuotaExceeded, get_top_level_comments

MAX_PER_RUN = 500


def youtube_comment_sentiment_flow():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("[youtube-comment-sentiment] YOUTUBE_API_KEY not set, skipping")
        return

    conn = get_connection()
    processed = 0
    try:
        with conn.cursor() as cur:
            trailers = get_movies_needing_comment_sentiment(cur, MAX_PER_RUN)
        print(f"[youtube-comment-sentiment] {len(trailers)} trailers to fetch this run (cap {MAX_PER_RUN})")

        for t in trailers:
            try:
                comments = get_top_level_comments(t["external_id"], api_key)
            except YouTubeQuotaExceeded:
                print(f"[youtube-comment-sentiment] quota exceeded after {processed}/{len(trailers)} - stopping")
                break
            except Exception as exc:
                print(f"[youtube-comment-sentiment] error fetching '{t['title']}': {exc}")
                continue

            summary = summarize_items(comments)
            with conn.cursor() as cur:
                upsert_sentiment_snapshot(
                    cur,
                    t["movie_id"],
                    stage=t["trailer_type"],
                    sentiment_score=summary["sentiment_score"],
                    volume=summary["volume"],
                    avg_engagement_score=summary["avg_engagement_score"],
                    raw_sample_ids=summary["sample_ids"],
                    source="youtube_comments",
                )
            conn.commit()

            processed += 1
            if processed % 50 == 0:
                print(f"[youtube-comment-sentiment] processed {processed}/{len(trailers)}")
    finally:
        conn.close()

    print(f"[youtube-comment-sentiment] done - {processed} processed")


if __name__ == "__main__":
    youtube_comment_sentiment_flow()
