"""Box Office Mojo backfill: populates box_office_totals and box_office_weekly
for every movie already in the database that has an imdb_id but no box
office data yet (backbone must be populated first via tmdb_backfill.py).

Run manually (module form — see tmdb_backfill.py's docstring for why):
    docker compose run --rm --no-deps prefect-worker python -m flows.bom_backfill

No official BOM API exists (scraping, per the planning doc's flagged risk),
so this stays deliberately slow (1 req/sec, see bom_client.py) and treats a
missing/unparseable page as a skip, not a fatal error, so one bad movie
doesn't stop the whole run.
"""

from prefect import flow, task
from prefect.cache_policies import NO_CACHE

import httpx

from bom_client import BOMClient, MovieNotFoundOnBOM
from db import get_connection, get_movies_missing_box_office, upsert_box_office_totals, upsert_box_office_weekly

SOURCE = "boxofficemojo"


def process_movie_box_office(client: BOMClient, movie_id: int, imdb_id: str) -> str:
    try:
        data = client.get_box_office(imdb_id)
    except MovieNotFoundOnBOM:
        return "not_found"
    except httpx.HTTPError as exc:
        # A single bad/unavailable page (5xx, timeout, etc.) shouldn't sink
        # the whole batch - log and move on, same as a 404.
        print(f"[bom-backfill] error fetching {imdb_id}: {exc}")
        return "error"

    opening_weekend_domestic = next(
        (row["weekend_gross"] for row in data["weekly"] if row["weekend_number"] == 1), None
    )

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                upsert_box_office_totals(
                    cur,
                    movie_id,
                    data["domestic"],
                    data["international"],
                    data["worldwide"],
                    opening_weekend_domestic,
                    SOURCE,
                )
                for row in data["weekly"]:
                    upsert_box_office_weekly(
                        cur,
                        movie_id,
                        row["weekend_number"],
                        row["weekend_gross"],
                        row["theater_count"],
                        SOURCE,
                    )
    finally:
        conn.close()

    return "ok"


@task(cache_policy=NO_CACHE)
def discover_movies_task() -> list[tuple[int, str]]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            return get_movies_missing_box_office(cur)
    finally:
        conn.close()


@task(retries=2, retry_delay_seconds=10, cache_policy=NO_CACHE)
def process_movie_task(client: BOMClient, movie_id: int, imdb_id: str) -> str:
    return process_movie_box_office(client, movie_id, imdb_id)


@flow(name="bom-backfill")
def bom_backfill_flow():
    client = BOMClient()
    movies = discover_movies_task()
    print(f"[bom-backfill] {len(movies)} movies need box office data")

    results = {"ok": 0, "not_found": 0}
    for i, (movie_id, imdb_id) in enumerate(movies, start=1):
        outcome = process_movie_task(client, movie_id, imdb_id)
        results[outcome] = results.get(outcome, 0) + 1
        if i % 25 == 0:
            print(f"[bom-backfill] processed {i}/{len(movies)} — {results}")

    print(f"[bom-backfill] done — {results}")


if __name__ == "__main__":
    bom_backfill_flow()
