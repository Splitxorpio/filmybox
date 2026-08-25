"""One-time poster_path backfill for movies ingested before that field was
captured. TMDb's /movie/{id} response has always included poster_path -
tmdb_backfill.py just never stored it until now, and does capture it
automatically for every future run. This flow only needs to run once to
catch up the existing ~4,400 movies.

Unlike the YouTube/Wikipedia/OMDb sources, TMDb's rate limit (20 req/sec,
already what tmdb_client.py uses) makes this fast enough to run in a single
pass - no quota-throttled multi-day pacing needed here.

Run manually, once (module form - see tmdb_backfill.py's docstring for why,
and for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.poster_backfill
"""

from db import get_connection, get_movies_missing_poster, update_movie_poster
from tmdb_client import TMDbClient


def poster_backfill_flow():
    client = TMDbClient()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            movies = get_movies_missing_poster(cur)
        print(f"[poster-backfill] {len(movies)} movies missing a poster")

        found = 0
        for i, (movie_id, tmdb_id) in enumerate(movies, start=1):
            try:
                detail = client.get_movie_detail(tmdb_id)
            except Exception as exc:
                print(f"[poster-backfill] error fetching tmdb_id={tmdb_id}: {exc}")
                continue

            poster_path = detail.get("poster_path")
            if poster_path:
                with conn.cursor() as cur:
                    update_movie_poster(cur, movie_id, poster_path)
                conn.commit()
                found += 1

            if i % 200 == 0:
                print(f"[poster-backfill] processed {i}/{len(movies)}")
    finally:
        conn.close()

    print(f"[poster-backfill] done - {found} of {len(movies)} matched")


if __name__ == "__main__":
    poster_backfill_flow()
