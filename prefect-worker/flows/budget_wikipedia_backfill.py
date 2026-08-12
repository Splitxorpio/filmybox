"""Wikipedia infobox budget backfill - third budget source, after Wikidata's
structured claim (sparse) and a reverted Bluesky social-consensus attempt
(unreliable for common-word titles - see budget_extraction.py's docstring
and the planning doc for why that was rolled back).

Two-step, mirroring wikidata_client.py's batching pattern: resolve each
movie's exact Wikipedia article via its Wikidata sitelink (batched, cheap),
then fetch+parse each resolved article's infobox individually (no batching
possible for arbitrary page content - this is the real rate-limited step).

Tracks wikipedia_budget_checked per movie (see 010_wikipedia_budget_checked.sql)
so re-runs only ever look at movies that haven't gotten a *definitive* answer
yet - found a budget, confirmed no Wikipedia article exists, or confirmed the
article has no USD budget field. A movie that was merely rate-limited and
never actually resolved stays unchecked, so a future run retries it instead
of silently giving up on it forever. Without this, re-runs re-scanned the
same already-failed movies indefinitely (confirmed this session: two re-runs
processed 971 movies combined and matched 0).

Run manually (module form - see tmdb_backfill.py's docstring for why, and
for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.budget_wikipedia_backfill
"""

import time

from db import (
    get_connection,
    get_movies_missing_budget_unchecked_wikipedia,
    mark_wikipedia_budget_checked,
    update_movie_budget,
)
from wikipedia_client import WikipediaRateLimited, fetch_infobox_budget, get_sitelinks

SITELINK_BATCH_SIZE = 50
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 30  # Wikipedia's anonymous-API burst limit (~10 req/burst,
# confirmed via a direct test this session) clears on this kind of timescale,
# not the 65s outage-mode throttle Wikidata needed earlier.


def budget_wikipedia_backfill_flow():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            movies = get_movies_missing_budget_unchecked_wikipedia(cur)
        print(f"[budget-wikipedia-backfill] {len(movies)} movies missing a budget and not yet checked")

        by_imdb_id = {imdb_id: movie_id for movie_id, imdb_id in movies}
        imdb_ids = list(by_imdb_id)

        resolved = 0
        matched = 0
        checked = 0
        for i in range(0, len(imdb_ids), SITELINK_BATCH_SIZE):
            batch = imdb_ids[i : i + SITELINK_BATCH_SIZE]
            try:
                sitelinks = get_sitelinks(batch)
            except WikipediaRateLimited:
                print(f"[budget-wikipedia-backfill] rate limited resolving sitelinks at batch {i} - stopping")
                break
            except Exception as exc:
                print(f"[budget-wikipedia-backfill] error resolving sitelinks at batch {i}: {exc}")
                continue

            # Every id in this batch with no resolved article is a
            # definitive "no Wikipedia coverage" - mark checked even though
            # nothing was fetched for it.
            for imdb_id in batch:
                if imdb_id not in sitelinks:
                    with conn.cursor() as cur:
                        mark_wikipedia_budget_checked(cur, by_imdb_id[imdb_id])
                    checked += 1
            conn.commit()

            for imdb_id, article_title in sitelinks.items():
                resolved += 1
                movie_id = by_imdb_id[imdb_id]
                gave_up = False
                budget = None
                for attempt in range(MAX_RETRIES):
                    try:
                        budget = fetch_infobox_budget(article_title)
                        break
                    except WikipediaRateLimited:
                        print(
                            f"[budget-wikipedia-backfill] rate limited on '{article_title}' "
                            f"(attempt {attempt + 1}/{MAX_RETRIES}) - waiting {RETRY_BACKOFF_SECONDS}s"
                        )
                        time.sleep(RETRY_BACKOFF_SECONDS)
                    except Exception as exc:
                        print(f"[budget-wikipedia-backfill] error fetching '{article_title}': {exc}")
                        gave_up = True
                        break
                else:
                    # Loop exhausted MAX_RETRIES without a clean break - still
                    # genuinely unknown, don't mark checked so a later run
                    # retries this specific movie instead of writing it off.
                    print(f"[budget-wikipedia-backfill] giving up on '{article_title}' after {MAX_RETRIES} attempts")
                    gave_up = True

                if gave_up:
                    continue

                with conn.cursor() as cur:
                    if budget is not None:
                        update_movie_budget(cur, movie_id, budget)
                        matched += 1
                    mark_wikipedia_budget_checked(cur, movie_id)
                    checked += 1
                conn.commit()

            print(f"[budget-wikipedia-backfill] processed {min(i + SITELINK_BATCH_SIZE, len(imdb_ids))}/{len(imdb_ids)}")
    finally:
        conn.close()

    print(f"[budget-wikipedia-backfill] done - {resolved} articles resolved, {matched} matched, {checked} newly marked checked")


if __name__ == "__main__":
    budget_wikipedia_backfill_flow()
