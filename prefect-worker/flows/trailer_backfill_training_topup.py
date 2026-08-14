"""Training-range companion to trailer_backfill.py - see
db.get_released_movies_missing_trailer_training_topup for why this exists:
the main flow's recency-first ordering (correct for its own purpose) left
the GBT training-set side of the time-split with zero trailer coverage at
all, the same coverage-skew shape already hit and fixed for critic scores.
This flow closes that gap, restricted to movies released before the
~2021-07-29 cutoff. Once trailers land here, the existing (unordered)
youtube_comment_sentiment.py flow will pick them up on its next run - no
changes needed there.

Same quota shape as trailer_backfill.py - re-run once per day.

Run manually (module form - see tmdb_backfill.py's docstring for why, and
for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.trailer_backfill_training_topup
"""

import os

from db import get_connection, get_released_movies_missing_trailer_training_topup, insert_trailer, upsert_trailer_metrics
from youtube_client import YouTubeQuotaExceeded, get_video_stats, search_trailer

MAX_PER_RUN = 90


def trailer_backfill_training_topup_flow():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("[trailer-backfill-training-topup] YOUTUBE_API_KEY not set, skipping")
        return

    conn = get_connection()
    processed = 0
    found_count = 0
    try:
        with conn.cursor() as cur:
            movies = get_released_movies_missing_trailer_training_topup(cur, MAX_PER_RUN)
        print(f"[trailer-backfill-training-topup] {len(movies)} pre-cutoff movies missing a trailer this run (cap {MAX_PER_RUN})")

        for movie_id, title, release_date in movies:
            try:
                found = search_trailer(title, release_date.year if release_date else None, api_key)
            except YouTubeQuotaExceeded:
                print(f"[trailer-backfill-training-topup] daily quota exhausted after {processed}/{len(movies)} - stopping")
                break
            except Exception as exc:
                print(f"[trailer-backfill-training-topup] error searching trailer for movie_id={movie_id} ({title}): {exc}")
                processed += 1
                continue

            if found:
                with conn.cursor() as cur:
                    trailer_id = insert_trailer(
                        cur,
                        movie_id,
                        found["video_id"],
                        f"https://www.youtube.com/watch?v={found['video_id']}",
                        "teaser" if "teaser" in found["title"].lower() else "trailer",
                        found["published_at"],
                    )
                conn.commit()
                found_count += 1

                try:
                    stats_by_id = get_video_stats([found["video_id"]], api_key)
                    stats = stats_by_id.get(found["video_id"])
                    if stats:
                        with conn.cursor() as cur:
                            upsert_trailer_metrics(cur, trailer_id, release_date, stats)
                        conn.commit()
                except YouTubeQuotaExceeded:
                    print(f"[trailer-backfill-training-topup] quota exhausted fetching stats after {processed}/{len(movies)} - stopping")
                    processed += 1
                    break
                except Exception as exc:
                    print(f"[trailer-backfill-training-topup] error fetching stats for movie_id={movie_id}: {exc}")

            processed += 1
            if processed % 20 == 0:
                print(f"[trailer-backfill-training-topup] processed {processed}/{len(movies)} ({found_count} trailers found)")
    finally:
        conn.close()

    print(f"[trailer-backfill-training-topup] done - {processed} processed, {found_count} trailers found")


if __name__ == "__main__":
    trailer_backfill_training_topup_flow()
