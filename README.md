# FilmyBox

FilmyBox predicts a movie's box-office outcome — flop, solid, hit, or blockbuster — at every stage of its lifecycle, from announcement through release, and shows how that prediction changes as real-world signal (trailers, critic reviews, social sentiment) accumulates.

## Motive

Most box-office commentary is retrospective: "we all knew this would flop" said after the numbers are in. The interesting version of this problem is forward-looking — given only what's knowable *at a given stage* (a franchise's track record before a trailer exists, a trailer's reception before reviews exist, reviews before opening weekend), how good a prediction can actually be made?

That framing drives most of the architectural decisions in this repo: predictions are versioned by lifecycle stage (`announcement` → `teaser` → `trailer` → `pre_release` → `post_release`), not just by movie, and every method's accuracy is measured honestly against a time-based holdout rather than a random split — the model is evaluated on its ability to predict the *future*, not interpolate the past.

## Architecture

| Service | What it does |
|---|---|
| `api/` | FastAPI backend — REST endpoints for movie data, comps, predictions, sentiment. Redis-cached where compute cost is real (live model inference, vector search). |
| `prefect-worker/` | All data ingestion and ML training, as plain Python scripts (`flows/`) run via `docker compose run`, not a live Prefect server — see [Data pipeline](#data-pipeline) below. |
| `frontend/` | Next.js dashboard — auth (NextAuth, credentials-based), an upcoming-movies list with live predictions, and a per-movie stage-by-stage timeline. |
| `postgres` | `pgvector/pgvector` — structured movie data plus vector embeddings for comp-similarity search, in one database. |
| `redis` | Cache only, no persistence volume — nothing authoritative lives here. |

Raw SQL throughout, no ORM (SQLAlchemy Core in `api/`, raw `psycopg` in `prefect-worker/`). The two Python services deliberately share no code — clients and query helpers are duplicated where both need the same logic, rather than introducing a shared package for two small services.

## Directory structure

```
api/app/
  routers/movies.py, auth.py   REST endpoints
  queries.py                   all SQL, SQLAlchemy Core
  gbt_predictor.py             live model inference (loads models/ at runtime)
  cache.py                     Redis get/set helpers

prefect-worker/
  *_client.py                  one thin httpx wrapper per external source
                                (tmdb, bom, omdb, youtube, wikidata, wikipedia,
                                bluesky, reddit)
  db.py                        all SQL, raw psycopg
  flows/                       one script per ingestion/training job (see below)

frontend/app/                  Next.js pages (App Router)

db/init/                       numbered schema migrations, applied on first
                                postgres start

models/                        trained LightGBM boosters + feature metadata
                                (gitignored build output, not source)

docs/box-office-analyzer-planning.md
                                the full build log - every decision, bug found,
                                and accuracy number from this project's history
```

## Data pipeline

Every `flows/*.py` script is a plain Python function (no `@flow`/`@task` — Prefect's local ephemeral server proved unreliable for long batch jobs), run manually via `docker compose run --rm --no-deps prefect-worker python -m flows.<name>`. Real scheduling (Prefect Cloud) is a known gap, not yet wired in.

| Source | What it provides | Ingestion shape |
|---|---|---|
| TMDb | Core movie/people/credit data, budgets (partial) | One-time historical backfill |
| Box Office Mojo | Box office totals + weekly breakdowns | One-time historical backfill (scraped) |
| OMDb | Critic scores (IMDb/RT/Metacritic) | Daily trickle + on-demand, both quota-limited (1,000 req/day) |
| YouTube | Trailer discovery + comment sentiment | Daily, quota-limited (~90 searches/day) |
| Wikidata / Wikipedia | Budget cross-check when TMDb has none | One-time backfill, tracks per-movie "already checked" to avoid re-scanning failures |
| Bluesky | Social sentiment (pre-release buzz + historical) | Periodic backfill, self-service auth |
| Reddit | Social sentiment | Built, blocked on Reddit's access-approval process |

Each source that can hit a rate limit has a dedicated exception type (checked *before* `raise_for_status()`, not after) so a flow stops cleanly instead of burning through a whole batch logging the same error — this specific bug recurred four separate times across different sources before becoming a standing pattern.

## The prediction system

Three methods coexist side-by-side in the `verdicts` table (`method` column), so their accuracy can be directly compared on the same holdout:

| Method | Approach | Exact-bucket accuracy* |
|---|---|---|
| `comp_heuristic_v1` | Weighted similarity to comparable movies (genre/cast/director), no ML | 36.4% |
| `gbt_v1` | LightGBM, pre-release features only (budget, cast/studio/franchise track record) | 42.0% |
| `gbt_v2` | + critic scores | 48.3% |
| `gbt_v3` | + social sentiment (Bluesky, YouTube comments), tuned hyperparameters | 49.6% |

*On the same held-out, time-based test set (movies released after the training cutoff — never seen during training). Naive baseline (always guess the most common bucket) is ~35%, for scale.

`gbt_v3` is served two ways: batch-precomputed into `verdicts` (`prefect-worker/flows/train_model.py`, run after data changes) and live via `GET /movies/{id}/predict` (`api/app/gbt_predictor.py`, in-process LightGBM inference, cached) for movies the last batch run hasn't reached yet.

## Status

Built: full ingestion pipeline across 7 sources, pgvector comp search, three-method verdict system with honest accuracy comparison, live + batch model serving, Redis caching, a working dashboard with auth.

For the full history — every decision, every bug found and fixed, every accuracy number along the way — see [`docs/box-office-analyzer-planning.md`](docs/box-office-analyzer-planning.md).
