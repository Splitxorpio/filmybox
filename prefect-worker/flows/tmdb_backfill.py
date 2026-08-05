"""TMDb backbone backfill: populates movies, studios, franchises, people,
and movie_credits for wide theatrical releases in a date range.

Run manually (module form, so sibling imports of db.py/tmdb_client.py resolve):
    docker compose run --rm --no-deps prefect-worker python -m flows.tmdb_backfill \
        --start-date 2010-01-01 --end-date 2026-07-31 --min-vote-count 50

This is a one-time/on-demand backfill, not part of the 60s healthcheck loop
in worker_entrypoint.py — running it on a schedule would re-hit the same
movies repeatedly for no benefit (upserts are idempotent, but wasteful).

Deliberately plain Python, not @flow/@task: Prefect's local ephemeral
server (used when no PREFECT_API_URL/PREFECT_API_KEY is configured) proved
flaky under `docker compose run` for a long single-shot batch - repeated
"database is locked" / timeout crashes on its own SQLite-backed state, with
nothing to do with our code. Retry/skip-on-error logic below is handled by
hand instead. Revisit once a real Prefect Cloud workspace is wired in.
"""

import argparse
from datetime import date

from db import (
    get_connection,
    upsert_franchise,
    upsert_movie,
    upsert_movie_credit,
    upsert_person,
    upsert_studio,
)
from tmdb_client import TMDbClient

CAST_LIMIT = 15  # billing order matters (1st vs 8th billed), so cap the long tail


def _extract_us_certification(release_dates: dict) -> str | None:
    for country in release_dates.get("results", []):
        if country.get("iso_3166_1") != "US":
            continue
        entries = country.get("release_dates", [])
        theatrical = [r for r in entries if r.get("type") == 3 and r.get("certification")]
        if theatrical:
            return theatrical[0]["certification"]
        any_cert = [r for r in entries if r.get("certification")]
        if any_cert:
            return any_cert[0]["certification"]
    return None


def _crew_role_type(crew_member: dict) -> str | None:
    job = crew_member.get("job", "")
    department = crew_member.get("department", "")
    if job == "Director":
        return "director"
    if job == "Producer":
        return "producer"
    if department == "Writing":
        return "writer"
    return None


def _get_or_create_person(cur, client: TMDbClient, tmdb_person_id: int, fallback_name: str) -> int:
    cur.execute("SELECT id FROM people WHERE tmdb_id = %s", (tmdb_person_id,))
    row = cur.fetchone()
    if row:
        return row[0]
    detail = client.get_person_detail(tmdb_person_id)
    birth_year = int(detail["birthday"][:4]) if detail.get("birthday") else None
    return upsert_person(
        cur, tmdb_person_id, detail.get("name") or fallback_name, detail.get("imdb_id") or None, birth_year
    )


def process_movie(client: TMDbClient, tmdb_id: int) -> None:
    detail = client.get_movie_detail(tmdb_id)

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                studio_id = None
                companies = detail.get("production_companies") or []
                if companies:
                    primary = companies[0]
                    studio_id = upsert_studio(cur, primary["id"], primary["name"])

                franchise_id = None
                collection = detail.get("belongs_to_collection")
                if collection:
                    franchise_id = upsert_franchise(cur, collection["id"], collection["name"])

                # TMDb sometimes stores clearly-bogus placeholder budgets ($1, $5,
                # $117...) rather than nulling them - no wide theatrical release
                # is actually made for under $1k, so treat those as unknown, not
                # "estimated" (real ultra-low-budget indies like Birdemic's
                # documented $10k sit safely above this floor).
                budget = detail.get("budget") or 0
                if budget < 1000:
                    budget = 0
                movie_row = {
                    "tmdb_id": detail["id"],
                    "imdb_id": detail.get("imdb_id") or None,
                    "title": detail.get("title"),
                    "release_date": detail.get("release_date") or None,
                    "genres": [g["name"] for g in detail.get("genres", [])],
                    "runtime_minutes": detail.get("runtime"),
                    "mpaa_rating": _extract_us_certification(detail.get("release_dates", {})),
                    "original_language": detail.get("original_language"),
                    "budget_usd": budget or None,
                    "budget_confidence": "estimated" if budget else "unknown",
                    "franchise_id": franchise_id,
                    "studio_id": studio_id,
                }
                movie_id = upsert_movie(cur, movie_row)

                credits = detail.get("credits", {})
                for cast_member in credits.get("cast", [])[:CAST_LIMIT]:
                    person_id = _get_or_create_person(cur, client, cast_member["id"], cast_member["name"])
                    upsert_movie_credit(
                        cur, movie_id, person_id, "actor", cast_member.get("order"), cast_member.get("character")
                    )

                for crew_member in credits.get("crew", []):
                    role_type = _crew_role_type(crew_member)
                    if role_type is None:
                        continue
                    person_id = _get_or_create_person(cur, client, crew_member["id"], crew_member["name"])
                    upsert_movie_credit(cur, movie_id, person_id, role_type, None, None)
    finally:
        conn.close()


def tmdb_backfill_flow(start_date: str = "2010-01-01", end_date: str | None = None, min_vote_count: int = 50):
    end_date = end_date or date.today().isoformat()
    client = TMDbClient()

    movie_ids = list(client.discover_movie_ids(start_date, end_date, min_vote_count))
    print(f"[tmdb-backfill] discovered {len(movie_ids)} candidate movies")

    for i, tmdb_id in enumerate(movie_ids, start=1):
        try:
            process_movie(client, tmdb_id)
        except Exception as exc:
            # A single bad/unexpected movie payload shouldn't sink a
            # multi-thousand-movie run - log and move on.
            print(f"[tmdb-backfill] error processing tmdb_id={tmdb_id}: {exc}")
        if i % 50 == 0:
            print(f"[tmdb-backfill] processed {i}/{len(movie_ids)}")

    print("[tmdb-backfill] done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="2010-01-01")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--min-vote-count", type=int, default=50)
    args = parser.parse_args()

    tmdb_backfill_flow(args.start_date, args.end_date, args.min_vote_count)
