"""Trailer backfill for the already-released, budgeted-and-outcome-known
corpus - the exact population train_model.py trains on (see
db.get_movies_for_training). stage_scan.py deliberately only searches for
trailers on movies NOT YET post_release (to conserve YouTube's 10,000/day
search.list quota, 100 units/search - see youtube_client.py), which means
the ~2,800-movie historical corpus with both budget and box office has NEVER
had a trailer search run against it: zero movies have both trailer stats and
a known outcome, so trailer engagement can't be trained on at all (see
planning doc). This flow closes that gap directly, without touching
stage_scan.py's own behavior.

YouTube's free quota (10,000 units/day) allows roughly 90-100 search.list
calls/day; MAX_PER_RUN leaves a little headroom under that ceiling. Stops
cleanly on YouTubeQuotaExceeded rather than retrying - same shape as
critic_score_backfill.py's OMDb handling. Needs to be re-run once per day
(quota resets daily) to keep building up (trailer, known-outcome) training
pairs.

Run manually, once per day (module form - see tmdb_backfill.py's docstring
for why, and for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.trailer_backfill
"""

import os

from prefect import flow

from db import get_connection, get_released_movies_missing_trailer, insert_trailer, upsert_trailer_metrics
from youtube_client import YouTubeQuotaExceeded, get_video_stats, search_trailer

MAX_PER_RUN = 90


@flow(name="filmybox-trailer-backfill", log_prints=True)
def trailer_backfill_flow():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("[trailer-backfill] YOUTUBE_API_KEY not set, skipping")
        return

    conn = get_connection()
    processed = 0
    found_count = 0
    try:
        with conn.cursor() as cur:
            movies = get_released_movies_missing_trailer(cur, MAX_PER_RUN)
        print(f"[trailer-backfill] {len(movies)} released/budgeted/outcome-known movies missing a trailer this run (cap {MAX_PER_RUN})")

        for movie_id, title, release_date in movies:
            try:
                found = search_trailer(title, release_date.year if release_date else None, api_key)
            except YouTubeQuotaExceeded:
                print(f"[trailer-backfill] daily quota exhausted after {processed}/{len(movies)} - stopping")
                break
            except Exception as exc:
                print(f"[trailer-backfill] error searching trailer for movie_id={movie_id} ({title}): {exc}")
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

                # Grab stats immediately (videos.list is ~1 unit, cheap
                # relative to the search that already cost 100).
                try:
                    stats_by_id = get_video_stats([found["video_id"]], api_key)
                    stats = stats_by_id.get(found["video_id"])
                    if stats:
                        with conn.cursor() as cur:
                            upsert_trailer_metrics(cur, trailer_id, release_date, stats)
                        conn.commit()
                except YouTubeQuotaExceeded:
                    print(f"[trailer-backfill] quota exhausted fetching stats after {processed}/{len(movies)} - stopping")
                    processed += 1
                    break
                except Exception as exc:
                    print(f"[trailer-backfill] error fetching stats for movie_id={movie_id}: {exc}")

            processed += 1
            if processed % 20 == 0:
                print(f"[trailer-backfill] processed {processed}/{len(movies)} ({found_count} trailers found)")
    finally:
        conn.close()

    print(f"[trailer-backfill] done - {processed} processed, {found_count} trailers found")


if __name__ == "__main__":
    trailer_backfill_flow()
