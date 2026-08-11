"""Bluesky-sourced budget backfill: fills in movies.budget_usd from social
post consensus, for movies still missing one after the Wikidata backfill.

Social posts are not authoritative - direct testing found real disagreement
between posts on the same movie and false positives from unrelated content
matching the search keywords. budget_extraction.py's consensus logic
deliberately trades recall for precision (requires 2+ corroborating posts,
no ambiguous ties) - most movies searched here will NOT get a match, and
that's the intended, honest behavior, not a bug. Matches are tagged
budget_confidence='social_estimate', distinct from Wikidata's 'estimated',
so nothing downstream conflates crowd chatter with a curated source.

No hard daily quota here (unlike OMDb/YouTube) - Bluesky's rate limit is
generous and bluesky_client.py already runs at a conservative fixed rate,
so the whole backlog clears in one run.

Run manually (module form, see tmdb_backfill.py's docstring for why, and
for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.budget_social_backfill
"""

import os

from budget_extraction import extract_budget_consensus
from bluesky_client import BlueskyAuthError, BlueskyRateLimited, search_budget_mentions
from db import get_connection, get_movies_missing_budget_titles, update_movie_budget


def budget_social_backfill_flow():
    handle = os.environ.get("BLUESKY_HANDLE")
    app_password = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not app_password:
        print("[budget-social-backfill] BLUESKY_HANDLE/BLUESKY_APP_PASSWORD not set, skipping")
        return

    conn = get_connection()
    processed = 0
    matched = 0
    try:
        with conn.cursor() as cur:
            movies = get_movies_missing_budget_titles(cur)
        print(f"[budget-social-backfill] {len(movies)} movies missing a budget")

        for movie_id, title, release_date in movies:
            year = release_date.year if release_date else None
            try:
                posts = search_budget_mentions(title, year, handle, app_password)
            except BlueskyRateLimited:
                print(f"[budget-social-backfill] rate limited after {processed}/{len(movies)} - stopping")
                break
            except BlueskyAuthError as exc:
                print(f"[budget-social-backfill] auth error, stopping run: {exc}")
                break
            except Exception as exc:
                print(f"[budget-social-backfill] error fetching '{title}': {exc}")
                continue

            budget_usd = extract_budget_consensus(posts, title)
            if budget_usd is not None:
                with conn.cursor() as cur:
                    update_movie_budget(cur, movie_id, budget_usd, confidence="social_estimate")
                conn.commit()
                matched += 1

            processed += 1
            if processed % 100 == 0:
                print(f"[budget-social-backfill] processed {processed}/{len(movies)} ({matched} matched so far)")
    finally:
        conn.close()

    print(f"[budget-social-backfill] done - {matched} of {processed} processed movies matched")


if __name__ == "__main__":
    budget_social_backfill_flow()
