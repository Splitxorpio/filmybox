"""Wikipedia infobox budget backfill - third budget source, after Wikidata's
structured claim (sparse) and a reverted Bluesky social-consensus attempt
(unreliable for common-word titles - see budget_extraction.py's docstring
and the planning doc for why that was rolled back).

Two-step, mirroring wikidata_client.py's batching pattern: resolve each
movie's exact Wikipedia article via its Wikidata sitelink (batched, cheap),
then fetch+parse each resolved article's infobox individually (no batching
possible for arbitrary page content - this is the real rate-limited step).

Run manually (module form - see tmdb_backfill.py's docstring for why, and
for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.budget_wikipedia_backfill
"""

import time

from db import get_connection, get_movies_missing_budget, update_movie_budget
from wikipedia_client import WikipediaRateLimited, fetch_infobox_budget, get_sitelinks

SITELINK_BATCH_SIZE = 50
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 30  # Wikipedia's anonymous-API burst limit (~10 req/burst,
# confirmed via a direct test this session) clears on this kind of timescale,
# not the 65s outage-mode throttle Wikidata needed earlier.


def _fetch_with_retry(article_title: str) -> int | None:
    for attempt in range(MAX_RETRIES):
        try:
            return fetch_infobox_budget(article_title)
        except WikipediaRateLimited:
            print(
                f"[budget-wikipedia-backfill] rate limited on '{article_title}' "
                f"(attempt {attempt + 1}/{MAX_RETRIES}) - waiting {RETRY_BACKOFF_SECONDS}s"
            )
            time.sleep(RETRY_BACKOFF_SECONDS)
    print(f"[budget-wikipedia-backfill] giving up on '{article_title}' after {MAX_RETRIES} attempts")
    return None


def budget_wikipedia_backfill_flow():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            movies = get_movies_missing_budget(cur)
        print(f"[budget-wikipedia-backfill] {len(movies)} movies missing a budget")

        by_imdb_id = {imdb_id: movie_id for movie_id, imdb_id in movies}
        imdb_ids = list(by_imdb_id)

        resolved = 0
        matched = 0
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

            for imdb_id, article_title in sitelinks.items():
                resolved += 1
                try:
                    budget = _fetch_with_retry(article_title)
                except Exception as exc:
                    print(f"[budget-wikipedia-backfill] error fetching '{article_title}': {exc}")
                    continue

                if budget is not None:
                    with conn.cursor() as cur:
                        update_movie_budget(cur, by_imdb_id[imdb_id], budget)
                    conn.commit()
                    matched += 1

            print(f"[budget-wikipedia-backfill] processed {min(i + SITELINK_BATCH_SIZE, len(imdb_ids))}/{len(imdb_ids)}")
    finally:
        conn.close()

    print(f"[budget-wikipedia-backfill] done - {resolved} articles resolved, {matched} matched")


if __name__ == "__main__":
    budget_wikipedia_backfill_flow()
