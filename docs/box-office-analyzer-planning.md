# Movie Box Office Analyzer — Project Planning Conversation

Context export for use with Claude Code. This captures the initial planning discussion for an AI/ML-driven box office prediction dashboard.

---

## Project Concept

An AI/ML system that analyzes historical box office trends of movies with similar hype/actors/directors/genre, and produces a staged prediction of a movie's box office performance based on signals available at each point in its lifecycle (announcement → news → teaser → trailer → release → post-release).

The product is envisioned as an IMDb-style dashboard, where each movie has a timeline of stages, and each stage shows a **verdict** (flop → blockbuster spectrum) with a confidence interval that narrows as more real-world signal becomes available.

### Stage-by-stage verdict concept
- **Announcement**: verdict based on cast/director/genre comps vs. current hype
- **News** (budget reveals, casting changes, etc.): verdict updates based on new info
- **Teaser**: verdict incorporates teaser reception/engagement
- **Trailer**: verdict incorporates trailer reception/engagement
- **Pre-release / opening**: verdict incorporates presales, critic scores, tracking
- **Post-release**: actual performance, legs/drop-off tracked over weekends

---

## Key Predictive Factors

### Pre-production / Announcement stage
- IP strength (sequel/franchise/remake/original, existing fanbase size)
- Studio track record (major vs. indie, historical ROI per studio)
- Release date positioning (competing releases same weekend, holiday slot vs. "dump month")
- Genre cyclicality (is the genre currently hot or fatigued)
- Star power trend (actor's last 5 films' opening weekend trend, not just career average)
- Director's genre fit (matching director's known genre vs. this project's genre)
- Budget-to-comp ratio (is budget unusual for this genre + cast tier)

### News / production stage
- Casting controversies or fan backlash (sentiment delta on announcement)
- Reshoots / delays / release date pushes (historically correlated with trouble)
- MPAA rating (changes total addressable audience)
- International pre-sales / distribution deals signed early

### Marketing stage (teaser / trailer)
- View velocity (first 24–48hr views vs. total), not just total views
- Like/dislike ratio, comment sentiment
- Engagement rate relative to channel size (context-normalized, not raw views)
- Organic fan content volume (reaction videos, memes, edits) — share of voice
- Google Trends search interest velocity
- Ticket pre-sale site traffic (Fandango, AMC app rankings)

### Near-release
- Critic embargo scores (Rotten Tomatoes / Metacritic when they drop)
- Advance ticket presales (one of the strongest predictors of opening weekend)
- Industry tracking numbers (Comscore/EDI equivalents, if reverse-engineerable from public signals)
- Theater/screen count secured
- Social sentiment in final 72 hours pre-release
- Competing film performance same weekend (cannibalization risk)

### Post-opening
- Weekend-to-weekend drop-off rate ("legs") — often more valuable to predict than opening weekend, since "flop" or "sleeper hit" narratives emerge here
- CinemaScore / PostTrak grades
- Repeat-viewing signals (social posts about rewatching)

---

## Modeling Approach

This is fundamentally a **comparable-based regression problem with staged confidence intervals** — the goal is not a single early prediction, but a *distribution* that narrows as more data arrives at each stage.

1. **Comp retrieval (similarity search)**: For a given movie, find k-nearest historical movies using embeddings of genre, cast/director vectors (trained on historical box office association), budget tier, release timing, studio. Prefer a learned embedding space over hand-engineered similarity weights, since the goal is grouping movies with similar box office trajectories.

2. **Staged models**: Train a separate model per stage (announcement, trailer, week-before-release, opening weekend), since available features change per stage. Early stages rely on categorical/historical features (wide error bars); later stages add real-time engagement signals (narrower bars). Structurally similar to a Bayesian updating pipeline — each stage refines a prior.

3. **Target definition**: Avoid predicting raw dollar figures directly (inflation/market size vary too much across decades). Instead predict a **relative multiplier vs. comps' median** or **percentile rank within genre+budget cohort**, then convert to a flop/hit/blockbuster verdict bucket (e.g. ROI multiple: <1x = flop, 1–3x = solid, 3–5x = hit, 5x+ = blockbuster). More robust than raw dollar regression.

4. **Sentiment/NLP layer**: Trailer/social scraping sentiment + engagement scoring should be a separate pipeline whose output ("hype score") feeds into the staged regressor as a feature — not a final verdict on its own.

5. **Ensemble approach**: Gradient-boosted trees (XGBoost/LightGBM) for structured/tabular features + a smaller NLP model for text sentiment, combined via stacking. GBTs are the standard choice for box office prediction over deep nets, given tabular features and limited sample size (thousands, not millions, of movies).

---

## Technical Stack

### Data ingestion
- **Movie/credits data**: TMDb API (free, well-documented) — no official IMDb API exists; TMDb or licensed IMDb datasets are the realistic path
- **Box office historicals**: Box Office Mojo (scraping, legally gray), The Numbers (some open data), Comscore (paid/enterprise)
- **Social scraping**: YouTube Data API (official, trailer views/likes/comments), Twitter/X API (paid tiers), Reddit API (still fairly open); TikTok has no good official API — scraping is fragile/ToS-risky, treat as a stretch goal
- **Search interest**: pytrends (unofficial but widely used) for Google Trends

### Backend/pipeline
- Python (pandas, scikit-learn, XGBoost/LightGBM, sentence-transformers for embeddings, HuggingFace for sentiment models)
- Airflow or Prefect for scheduled scraping/ETL jobs
- PostgreSQL for structured data + vector DB (Pinecone, Weaviate, or pgvector) for comp-similarity search
- Redis for caching frequent dashboard queries

### API/serving layer
- FastAPI to serve predictions + dashboard data
- Simple model serving (pickled sklearn/XGBoost loaded directly in FastAPI process) — no need for heavy MLOps infra (Seldon/BentoML) at MVP stage

### Frontend
- Next.js/React dashboard
- Recharts or D3 for trend visualizations
- Movie detail page shows a "stage timeline" (announcement → news → teaser → trailer → release), each with its own verdict + confidence interval — similar to a stock chart with prediction bands

### Deployment
- **MVP**: Vercel (frontend) + Railway or Render (backend/API) + managed Postgres (Supabase/Neon) — cheap, fast to stand up
- **Scraping jobs**: scheduled via Railway cron or a small dedicated VM (scraping is often IP-rate-limited, so a single server with rotating requests is simpler than serverless here)
- **If it grows**: AWS (ECS/Fargate for API, RDS for Postgres, S3 for raw scraped data/model artifacts); SageMaker only if managed training becomes worthwhile — likely overkill early

### Key risks flagged
- IMDb has no free API — TMDb is the realistic substitute; decide before building schemas around it
- TikTok/Instagram scraping is the most legally/technically fragile piece — treat YouTube+Reddit+Twitter as the reliable core
- Cold start problem: comp-based model needs a solid historical dataset (~2,000+ movies with box office + cast + budget) before predictions are meaningful — likely the biggest time sink, bigger than modeling itself

---

## Historical Data Collection Pipeline (Detailed Plan)

### Step 1: Entity/schema design

**`movies`**
- id, tmdb_id, imdb_id, title, release_date, genre(s), runtime, mpaa_rating, budget, original_language, franchise_id (nullable — links sequels/reboots), studio_id

**`people`**
- id, tmdb_id, imdb_id, name, role_type (actor/director/producer/writer), birth_year (for career-stage features)

**`movie_credits`** (join table)
- movie_id, person_id, role_type, billing_order (1st billed vs. 8th billed matters heavily for "star power" weighting), character_name (optional)

**`box_office_results`** (time series, not just final totals)
- movie_id, opening_weekend_domestic, opening_weekend_international, total_domestic, total_international, total_worldwide, weekend_number, weekend_gross, theater_count, currency, source, last_updated
- Must be weekly time series (weekend 1, 2, 3 gross), since "legs"/drop-off is a key feature

**`studios`**
- id, name, tier (major/mini-major/indie), historical_avg_roi

**`trailers`**
- id, movie_id, platform (youtube/etc.), url, publish_date, trailer_number (teaser vs. trailer 1 vs. trailer 2)

**`trailer_metrics`** (time series, pulled repeatedly)
- trailer_id, snapshot_date, view_count, like_count, comment_count

**`sentiment_snapshots`**
- movie_id, stage (announcement/casting_news/teaser/trailer/pre_release), snapshot_date, source (reddit/twitter/youtube_comments), sentiment_score, volume (mention count), raw_sample_ids (for audit)
- Store as a time series per stage, not one blended number — the product thesis depends on verdict evolving stage by stage

### Step 2: Historical backfill scope
- **Time window**: last 15–20 years of wide releases (older than that, social/trailer data doesn't exist — those fields would be null, though still usable for early-stage cast/director comp models)
- **Release scope**: theatrical wide releases only for v1 (skip limited/festival-only/straight-to-streaming — different economics)
- **Target corpus size**: ~2,000–3,000 movies — enough for GBT training, backfillable in weeks not months

### Step 3: Source-to-field mapping

| Data needed | Best source | Notes |
|---|---|---|
| Cast/director/producer credits | TMDb API | Free; has IMDb ID cross-reference — grab immediately as universal join key |
| Budget | TMDb API (inconsistent) + The Numbers (better budget data) | Budget is notoriously self-reported/unreliable; track a confidence flag per record |
| Box office (opening + weekly) | Box Office Mojo | No official API — scraping; URL structure is consistent per-movie |
| Trailer views/engagement | YouTube Data API v3 | Official, quota-limited (10k units/day free tier) — budget calls carefully |
| Social sentiment | Reddit API (PRAW) | Most durable/least fragile social source currently available |
| Critic scores | OMDb API (wraps RT/Metacritic) | Cheap, simple, avoids scraping RT directly |

**Key early decision**: Use TMDb's `external_ids` endpoint to get the IMDb ID for every movie/person immediately — use it as the universal join key across all other sources.

### Step 4: Build order
1. **Backbone**: TMDb pull for movies + credits + studios → populates `movies`, `people`, `movie_credits`, `studios`. Enables early prototyping of "comps by cast/director" while other scrapers are being built.
2. **Financial layer**: Box Office Mojo scrape (opening + weekly numbers) → populates `box_office_results`. This is the prediction **label** — get it right before feature engineering.
3. **Critic layer**: OMDb pull for RT/Metacritic, done in parallel with step 2.
4. **Trailer layer**: YouTube API search per movie for official trailer(s); pull metrics at multiple points in time relative to release where possible. Caveat: for historical backfill, only *current* view counts on old trailers are generally available, not their original velocity curve — trailer velocity features will be reliable going forward (tracked prospectively), not retroactively.
5. **Social sentiment layer**: Reddit pull, done last — most fragile/rate-limited, and least critical for v1 since velocity-dependent features are already semi-broken for historical backfill (see step 4).

### Step 5: Data quality / dedup concerns to design for now
- **Person disambiguation**: match on TMDb/IMDb person ID, never on name string (e.g., multiple people named "Michael Bay")
- **Franchise linking**: sequels explicitly linked via `franchise_id`, so comps can optionally include/exclude same-franchise entries (e.g. a *Fast & Furious 9* comp set differs a lot depending on whether prior *Fast* films are included)
- **Currency/inflation normalization**: budgets/grosses from 2005 vs. 2024 aren't directly comparable — apply CPI-adjustment or "% of genre-year median" normalization in the pipeline itself, not deferred to modeling time
- **Missing data flagging**: budget will be null/unreliable for an estimated 20–30% of movies — build a `budget_confidence` flag rather than silently imputing

### Step 6: Pipeline tooling
- **Orchestration**: Prefect (simpler than Airflow at this scale; good retry/backoff handling for API rate limits)
- **Storage**: raw pulls land in S3/local disk as JSON (immutable raw layer) → transformed into Postgres tables (raw/clean separation avoids re-scraping if a downstream schema bug appears)
- **Rate limiting**: build a shared rate-limiter utility from day one — TMDb, YouTube, and Reddit each have different quota shapes; retrofitting this later is painful

---

## Open Decision Points (Next Steps)
- Start with TMDb ingestion script (backbone layer) to get a working movie/credits/studio table, **or**
- Nail down the Postgres schema in actual DDL first

Both are reasonable starting points — the ingestion script gets data flowing sooner; the DDL-first approach avoids reworking table structure mid-scrape.

---

## Docker-Based Architecture (Decided)

### Services (docker-compose, local dev)

| Service | Image/base | Notes |
|---|---|---|
| `frontend` | `node:20-alpine` → Next.js | Dev: hot-reload volume mount. Prod: deployed to Vercel directly, not containerized for prod |
| `api` | `python:3.12-slim` + FastAPI/uvicorn | Serves predictions + dashboard data; loads pickled GBT models **in-process** at startup (see Model Serving below) |
| `postgres` | `pgvector/pgvector:pg16` | Single image gives structured tables + vector column for comp-similarity search — no separate vector DB needed |
| `redis` | `redis:7-alpine` | Dashboard query caching |
| `prefect-worker` | same Python base as `api`, different entrypoint | Runs scraping/ETL flows (TMDb, Box Office Mojo, YouTube, Reddit) on schedule, reporting to **Prefect Cloud** |

Prefect Cloud (not self-hosted) was chosen for scheduling/orchestration — free tier, no extra container to run/maintain, hosted UI. Only a lightweight `prefect-worker` container runs locally/in-prod to execute flows.

### Why Docker specifically
- Scraping jobs need isolation from the API process — rate-limited, long-running, shouldn't share a runtime/restart cycle with request-serving code
- `api` and `prefect-worker` share the same model-loading/DB-access code — same base image, different `CMD`
- Local dev parity: pgvector + Redis are painful to install natively on Windows; compose makes `docker compose up` bring up the whole stack

### Where NOT to containerize
- **Frontend in prod**: ship to Vercel directly rather than running a Next.js container in prod (containerize locally only if wanting one `docker compose up` for full-stack demos)
- **Prod Postgres**: use managed Postgres (Supabase/Neon) instead of self-hosting the `postgres` container — both support the `pgvector` extension, keeping local/prod consistent

### Model Serving (Decided: Path 1 — in-process)

Three paths were considered:

1. **In-process** (chosen): FastAPI loads the pickled XGBoost/LightGBM model file into memory at container startup and calls `model.predict()` directly in the request handler. Simplest, lowest latency, no extra service. Tradeoff: updating the model requires redeploying/restarting the API.
2. **Decoupled model-serving service**: model runs behind its own API (BentoML/Seldon/TorchServe/a second FastAPI app), main API calls it over HTTP/gRPC. Lets you retrain/redeploy the model independently of API code, at the cost of a network hop, another container to run, and schema-sync overhead between the two services.
3. **Managed inference endpoint** (e.g. SageMaker): fully hosted, autoscaled, but priced per endpoint-hour — overkill for GBTs at a few-thousand-movie dataset scale; really meant for GPU-bound/variable-load deep learning workloads.

**Rationale for Path 1**: GBT inference on tabular features is fast and cheap (no GPU needed), retraining will happen infrequently (batch, as new box office results roll in) rather than continuously, and the project is pre-launch — decoupling buys flexibility not needed yet at real operational cost. Revisit if retraining cadence ever exceeds API deploy cadence, or if inference becomes a load bottleneck separate from API traffic.

---

## Project Scaffold (Built)

Directory structure, docker-compose, and Postgres DDL are live in the repo:
- `docker-compose.yml` — `postgres` (pgvector/pgvector:pg16), `redis`, `api` (FastAPI), `frontend` (Next.js), `prefect-worker`
- `api/` — FastAPI app with `/health` checking Postgres + Redis connectivity
- `frontend/` — Next.js app-router scaffold; server-rendered home page fetches API health over the internal Docker network (`API_INTERNAL_URL=http://api:8000`, distinct from the browser-facing `NEXT_PUBLIC_API_URL`)
- `prefect-worker/` — runs a placeholder healthcheck flow on a 60s loop until a real Prefect Cloud workspace/API key is wired in
- `db/init/001_schema.sql` — full DDL, auto-applied on first boot against an empty `postgres_data` volume

Verified end-to-end: `docker compose up -d --build` brings up all 5 services; `curl localhost:8000/health` and `curl localhost:3000` both resolve correctly.

### Postgres DDL — decisions made beyond the original Step 1 spec
- **`box_office_results` split into two tables**: `box_office_totals` (one row per movie — opening weekend + lifetime totals) and `box_office_weekly` (the actual weekend-by-weekend time series needed for "legs"/drop-off). The original single-table description conflated a point-in-time fact with a time series.
- **`franchises` table added**: needed as the target of `movies.franchise_id`, which the original schema referenced but didn't define.
- **`movie_embeddings` table added now** (not in the original Step 1 list): backs the pgvector comp-similarity search already committed to in the Modeling Approach section. `VECTOR(384)` as a placeholder dimension (sentence-transformers MiniLM-class default) — will need to match whichever embedding model is actually used, since the column width is fixed. Empty until the embedding pipeline exists.
- **Predictions/verdicts table deliberately deferred**: storing the dashboard's stage-by-stage verdict output is a modeling-stage concern: designing it now, before the staged models exist, risks guessing the wrong output shape. Revisit once the staged models are built.
- **Check constraints over native Postgres enums**: for `role_type`, `tier`, `budget_confidence`, `trailer_type`, `stage`, `source` — easier to alter later than enum types, which have historically been awkward to modify without table locks.

### Next steps
- Write TMDb ingestion script (backbone layer: `movies`, `people`, `movie_credits`, `studios`)
- Or continue building out the API/dashboard against the now-live schema

---

## TMDb Backbone Ingestion (Built)

`prefect-worker/flows/tmdb_backfill.py` populates `movies`, `studios`, `franchises`, `people`, and `movie_credits` from TMDb. Run manually:
```
docker compose run --rm --no-deps prefect-worker python -m flows.tmdb_backfill \
    --start-date 2010-01-01 --end-date 2026-07-31 --min-vote-count 50
```
(`docker compose run`, not `exec` — see gotcha below.)

### TMDb endpoint mapping
- `GET /discover/movie` (`primary_release_date.gte/.lte`, `with_release_type=3` for wide theatrical only, `vote_count.gte` to filter obscure/straight-to-video) — candidate movie id discovery
- `GET /movie/{id}?append_to_response=credits,release_dates` — one call gets details + full cast/crew + release-by-country data, collapsing what would otherwise be 3 separate calls
- MPAA rating isn't on the base details payload — extracted from `release_dates.results[iso_3166_1=="US"]`, preferring the `type: 3` (Theatrical) certification
- `GET /person/{id}` — birthday/imdb_id per new person only (existing people are looked up by `tmdb_id` first, so this call is skipped for anyone already backfilled)
- `belongs_to_collection` (free on movie details) maps directly onto our `franchises` table — no extra call needed for franchise linking

### Schema tweak made while building this
Added `studios.tmdb_company_id` and `franchises.tmdb_collection_id` (both `UNIQUE`) — the original DDL deduped both by `name` string, which conflicts with the "never match on name string" rule already applied to `people`. Migrated live via `ALTER TABLE` since both tables were still empty.

### Design decisions
- **Cast capped at billing order < 15** (`CAST_LIMIT`) — matches the "1st vs 8th billed matters" star-power signal from the plan; avoids pulling every background extra
- **Crew role mapping**: `job == "Director"` → director, `job == "Producer"` → producer, `department == "Writing"` → writer; everything else dropped
- **`budget_confidence`**: `"estimated"` if TMDb returns a nonzero budget, `"unknown"` if zero/missing — TMDb budgets are crowd-sourced, never treated as `"confirmed"`
- **Rate limiting**: a small reusable `RateLimiter` (token-spacing, thread-safe) capped at 20 req/sec, well under TMDb's documented ~40 req/sec ceiling — same utility class intended for reuse with YouTube/Reddit later, per the "shared rate-limiter from day one" plan

### Gotcha hit during testing: don't `exec` into the running prefect-worker container
The long-running `prefect-worker` container already runs the placeholder healthcheck flow, which spins up its own local ephemeral Prefect API server (SQLite-backed) since no Prefect Cloud workspace is wired in yet. Running a second process via `docker compose exec` into that *same* container starts a second local ephemeral server pointing at the same SQLite state file — the two collided mid-migration and crashed the container. Fix: use `docker compose run --rm --no-deps prefect-worker ...` for one-off flow runs, which spins up an independent container with its own throwaway local state. This whole class of problem goes away once Prefect Cloud is actually configured (`PREFECT_API_KEY`/`PREFECT_API_URL` in `.env`) — flows would talk to the shared cloud API instead of each spinning up a local server.

### Verified
Test run (Q1 2024, `min_vote_count=300`, 59 movies) produced 59 `movies`, 1,207 `people`, 1,308 `movie_credits`, 56 `studios`, 16 `franchises` — genres, MPAA ratings, budget confidence flags, and franchise linking (e.g. *The Beekeeper*, *Justice League: Crisis on Infinite Earths*) all populated correctly.

### Next steps
- Run the full historical backfill (2010–present, or per the doc's original 15–20 year window)
- Box Office Mojo scraper for `box_office_totals`/`box_office_weekly` (the prediction label — per the original build order, get this right before feature engineering)
- OMDb pull for critic scores, in parallel with the above

---

## Box Office Mojo Scraper (Built)

`prefect-worker/bom_client.py` + `prefect-worker/flows/bom_backfill.py` populate `box_office_totals` and `box_office_weekly` for every movie already in the DB that has an `imdb_id` but no box office data yet. Run manually:
```
docker compose run --rm --no-deps prefect-worker python -m flows.bom_backfill
```

### Reliability research (before building)
Checked three candidate sources for the box office label data:
- **Box Office Mojo**: only public source with a true weekend-by-weekend time series (needed for the "legs"/drop-off feature) — nothing else substitutes. No official API; scraping, ToS gray area (already flagged in the original plan). Pages are keyed by `imdb_id` (`/title/{imdb_id}/`), which we already have — clean join, no fuzzy title matching.
- **The Numbers**: independent second budget figure (caught a real discrepancy: $40M vs. TMDb's $35M for *The Beekeeper*) plus its own weekly table, but keyed by a title+year slug with no stable id — fuzzier join. Deferred.
- **Wikipedia**: official API, zero scraping risk, but totals/budget only, no weekly series.

Decision: build BOM only for now (the irreplaceable piece); revisit The Numbers as a budget cross-check and Wikipedia as a zero-risk fallback later if budget-confidence turns out to matter a lot for the model.

### How the scraper works
- `GET /title/{imdb_id}/` → parses the `mojo-performance-summary-table` (domestic/international/worldwide totals, matched by label text, not position) and finds the domestic release's `/release/{id}/` path
- `GET /release/{id}/weekend/` → parses the weekly table by resolving column `title` attributes (`"Weekend Gross"`, `"Number of Theaters"`, `"Weekend"` = week-in-release number) rather than fixed column positions, so it survives BOM reordering columns
- `opening_weekend_domestic` is derived from the weekly row where `weekend_number == 1`, not scraped separately
- Rate limited to 1 req/sec (`RateLimiter`, same reusable class as the TMDb client) — deliberately conservative given the ToS gray area
- Any per-movie failure (404 = no BOM page, 5xx, timeout) is caught and logged as a skip rather than crashing the whole batch run

### Bugs hit and fixed during testing
- **Wrong "Domestic" link matched**: the title page has *two* links with the text "Domestic" — a navigation tab (`/date/...`) and the actual release link (`/release/rl.../`). The first match (the nav tab) doesn't fit the release-id pattern, so the naive `find()` silently returned no weekly data for every movie. Fixed by iterating all "Domestic"-text links and taking the one whose `href` actually matches `/release/rl\d+/`.
- **Duplicate weekend numbers on holiday weekends**: BOM shows two rows tagged with the same week number for holiday frames (e.g. MLK weekend) — a standard 3-day figure and an extended 4-day total. Since our schema is `UNIQUE(movie_id, weekend_number)`, kept the first (standard) row and dropped the duplicate, for comparability across movies that didn't open on a holiday.
- **One bad page killed the whole batch**: an unhandled 503 on a single movie propagated past Prefect's task retries and crashed the entire flow run after 25/78 movies. Fixed by catching `httpx.HTTPError` per-movie and logging it as a skip, same as the existing 404 handling.

### Verified
Full run against the 78 movies already in the DB: 78/78 `box_office_totals` rows, 393 `box_office_weekly` rows (avg. ~5 weekends/movie), 43/78 with a populated opening weekend (the rest are movies without a BOM-tracked US domestic release, e.g. day-and-date international titles). Spot-checked *The Beekeeper*'s 11-week legs curve against the live BOM page — exact match.

### Next steps
- Run TMDb + BOM backfill together across the full historical window
- OMDb pull for critic scores (RT/Metacritic)
- Revisit The Numbers/Wikipedia as budget cross-checks if `budget_confidence` proves important to the model

---

## Full Historical Backfill (Run)

Ran `tmdb_backfill.py` across 2010-01-01 to 2026-08-03. First attempt at `min_vote_count=200` discovered 7,644 candidates — well above the doc's original 2,000-3,000 target — so raised to `min_vote_count=500`, trading corpus size for staying near the original target and biasing toward well-tracked/higher-hype movies (arguably better signal for a hype-driven model anyway).

### Bug hit and fixed: empty-string `imdb_id` collision
TMDb returns `imdb_id: ""` (not `null`) for people without a linked IMDb page. `_get_or_create_person` in `tmdb_backfill.py` passed this straight through to `upsert_person`, and since Postgres `UNIQUE` allows multiple `NULL`s but not multiple identical non-null values, the second person with `imdb_id=""` violated `people_imdb_id_key` and crashed the run after ~650 movies. Fixed by normalizing `detail.get("imdb_id") or None`, matching the normalization the movie-level upsert already had.

### Architecture change: dropped `@flow`/`@task` from the backfill scripts
Both `tmdb_backfill.py` and `bom_backfill.py` originally used Prefect's `@flow`/`@task` decorators. Running them via `docker compose run` repeatedly triggered Prefect's local ephemeral server (used when no real Prefect Cloud workspace is configured) into `database is locked` / startup-timeout crashes — a flakiness in Prefect's own SQLite-backed state, unrelated to our code, that got worse the longer/more request-heavy the run. Since both scripts already have hand-written per-item retry/skip logic (the real safety net), the Prefect orchestration layer added risk without adding value for a one-off manual script. Both are now plain Python — `tmdb_backfill_flow()`/`bom_backfill_flow()` are just regular functions, still callable the same way (`python -m flows.tmdb_backfill ...`). Revisit `@flow`/`@task` once a real Prefect Cloud workspace is wired in (`PREFECT_API_KEY`/`PREFECT_API_URL`), since that removes the local-ephemeral-server failure mode entirely.

### Result
Corpus grew to 1,291+ movies (2010–2026, `min_vote_count=500`) and climbing — this was run in the background and finished after the API layer work below was already underway.

---

## Movie Data API (Built)

`api/app/routers/movies.py` + `api/app/queries.py` + `api/app/schemas.py` expose the backfilled data via FastAPI, ahead of the actual dashboard frontend. No ORM — raw SQL via SQLAlchemy Core (`text()`), matching the style already used in `prefect-worker/db.py` and the existing `/health` endpoint, rather than introducing SQLAlchemy models.

### Endpoints
- `GET /movies` — paginated list, filterable by `genre`, `year`, `search` (title `ILIKE`)
- `GET /movies/{id}` — full detail: core fields, studio, franchise, ordered credits (director → writer → producer → actor, then billing order), box office totals + weekly series
- `GET /movies/{id}/comps` — heuristic similar-movies list: score = shared genre count + shared-director weight (×3) + shared-actor weight, ranked descending. Explicitly a placeholder for the embedding-based k-NN retrieval from the Modeling Approach section (`movie_embeddings` stays empty until that pipeline exists)

### Verified
- `GET /movies?limit=3` — real paginated rows against the live (still-growing) corpus
- `GET /movies/{id}` for *The Beekeeper* — full credits list, correct franchise linking (`The Beekeeper Collection`), box office totals + 11-week series matching the earlier BOM verification
- `GET /movies/{id}/comps` for *The Beekeeper* — genuinely meaningful results: *End of Watch* (also directed by David Ayer) and *Safe*/*Blitz*/*The Mechanic* (all Jason Statham action-thrillers) ranked at the top, confirming the director/actor-match weighting works as intended
- 404 confirmed for a nonexistent movie id

### Next steps
- Frontend dashboard pages against these endpoints (movie list, movie detail "stage timeline" view)
- Redis caching on the list/detail endpoints once real dashboard traffic patterns exist (deliberately skipped for now — premature at this data volume)
- OMDb critic score pull, embedding-based comps to eventually replace the heuristic

---

## Full Backfill Completion, Data Audit, and Embedding Pipeline

Once the full TMDb backfill finished (4,395 movies, 45,059 people, 94,803 credits, 1,921 studios, 644 franchises, zero errors) and BOM was kicked off against the complete set, used the wait time productively: data quality audit → comps heuristic stress test at scale → embedding pipeline.

### Data quality audit
Coverage across the full corpus: 99.98% have `imdb_id`, 99.75% have a studio, 88% have an MPAA rating, 0 missing genres/runtime. Budget: 67.7% `estimated`, 32.3% `unknown` (close to the doc's expected 20-30%).

**Real bug found**: TMDb sometimes stores clearly-bogus placeholder budgets (`$1`, `$5`, `$7`, `$117`, `$119`) instead of nulling them when the real budget is unknown — 6 movies had this. Since our `budget_confidence` logic only checked `budget > 0`, these were being marked `"estimated"` rather than `"unknown"`, which would badly corrupt any ROI-multiplier feature (dividing box office by a "$1 budget"). Confirmed a $1,000 floor cleanly separates the garbage from genuine ultra-low-budget films (*Birdemic: Shock and Terror*'s well-documented real $10,000 budget sits safely above it). Fixed both the 6 existing rows (`budget_usd = NULL`, `budget_confidence = 'unknown'`) and the bug at its source in `tmdb_backfill.py` (`process_movie`) so future backfills don't reintroduce it.

### Comps heuristic stress test (at 4,395 movies vs. the original 78)
Spot-checked across genres/eras/franchises — held up very well: correctly surfaced franchise sequences (*Fast X* → *F9*/*Furious 7*/*Fast Five*, *Toy Story 4* → *Toy Story 5*) and, more impressively, auteur directors purely via the director-match weight rather than genre alone (*Inception* → *Interstellar*/*Tenet*/*Dunkirk*, *La La Land* → *Whiplash*/*Babylon*, *Get Out* → *Nope*/*Us*, *The Conjuring* → *Insidious* 1&2). No failures worth fixing.

### Embedding pipeline (Built)
`prefect-worker/embedding_client.py` (lazy-loaded `sentence-transformers/all-MiniLM-L6-v2` singleton) + `prefect-worker/flows/build_embeddings.py` populate `movie_embeddings` — the learned-embedding-space step from the Modeling Approach section, intended to eventually replace/supplement the heuristic `/comps` endpoint. Text descriptor per movie: genres, director(s), top-5-billed cast, studio, coarse budget tier, release year — deliberately **not including the movie title** (see bug below). Added `pgvector` (Python package) for clean vector parameter binding via `register_vector(conn)`, and a named Docker volume for the HuggingFace model cache so repeated one-off runs don't re-download the ~80MB model weights.

**Dependency tradeoff accepted**: `sentence-transformers` pulls in `torch`, growing the `prefect-worker` image by roughly 1-2GB and adding several minutes to builds. Confined to this one ETL-only container, consistent with the existing service-boundary rationale (scraping/ML batch jobs isolated from the request-serving API).

#### Bugs hit and fixed
- **psycopg3 `with conn:` closes the connection, not just the transaction** (a real difference from psycopg2): `build_embeddings.py` reused one connection across all batches, and the first batch's `with conn: ...` block committed *and closed* the connection, crashing the second batch with `the connection is closed`. Fixed by using `conn.commit()` explicitly instead of the `with conn:` context manager when a connection needs to survive past the current block.
- **Movie title in the embedded text caused superficial lexical clustering, not semantic similarity**: initial results were bad — *The Beekeeper*'s top match was *Ramona and Beezus* (a kids' comedy), *Fast X*'s top matches were "X" and "Saw X", *Get Out*'s were *Inside Out*/*Lights Out*. All wordpiece/subword token overlap on the title, drowning out the structured genre/cast/director signal. Fixed by dropping the title from the embedded text entirely — result was a dramatic quality jump (cosine distances tightened from ~0.3-0.44 down to ~0.11-0.16) and the nearest neighbors became genuinely coherent: *Fast X* → *F9* (correct franchise entry, now #1), *Inception* → *Interstellar*/*TRON: Legacy*/*Mad Max: Fury Road* (big-budget sci-fi/action spectacle), *Get Out* → *It Comes at Night*/*It Follows* (genuinely similar low-budget horror-thriller).
- Re-indexed `idx_movie_embeddings_ivfflat` after the bulk load (it was created against an empty table originally, which `ivfflat` clusters poorly against).

**Note on the two similarity approaches**: the embedding surfaces a different, complementary notion of similarity to the heuristic — broader genre/style/budget-tier clustering rather than the heuristic's exact-match director/cast rewards. Both are valid; this was expected, not a discrepancy to resolve.

### Verified
4,395/4,395 movies embedded. k-NN sanity-checked via raw `<=>` cosine-distance SQL against *The Beekeeper*, *Inception*, *Fast X*, *Get Out* — all produced thematically coherent nearest neighbors after the title fix.

### Next steps
- Wire `GET /movies/{id}/comps` to optionally use pgvector k-NN (`ORDER BY embedding <=> ...`) alongside or instead of the heuristic
- Re-run `build_embeddings.py` once BOM data lands, to consider folding box office performance into the text descriptor (currently pre-release signals only)
- OMDb critic score pull

---

## Embedding Model Migration: MiniLM → nomic-embed-text-v1.5

Decided to migrate ahead of the originally-planned review-embedding work (see next section), on the reasoning that MiniLM's 256-token context would badly truncate real reviews (400-1000+ words), making the switch immediately relevant rather than a future concern.

### Model comparison (researched before switching)
Compared three candidates — `all-MiniLM-L6-v2` (current), `nomic-embed-text-v1.5`, and `embeddinggemma:300m`:

| | MiniLM (previous) | nomic-embed-text-v1.5 | embeddinggemma:300m |
|---|---|---|---|
| Params | 22.7M | 137M | 300M |
| Native dims | 384 | 768, Matryoshka to 64 | 768, Matryoshka to 128 |
| Context | 256 tokens | 8,192 tokens | 2,048 tokens |
| MTEB | not top-tier (2021 baseline) | ~62.28 | 69.67 (English v2) |
| Languages | English | English | 100+ |

Chose nomic over Gemma: Gemma's higher MTEB score comes with multilingual support we don't need, and its Matryoshka breakpoints (768/512/256/128) don't include 384, forcing a schema migration regardless. Nomic's Matryoshka range goes down to 64, so it can truncate to exactly 384 — a drop-in replacement for the existing `movie_embeddings.embedding VECTOR(384)` column with no schema change.

### Implementation details
- `prefect-worker/embedding_client.py`: switched to `nomic-ai/nomic-embed-text-v1.5` via `sentence-transformers` (`trust_remote_code=True`, required until transformers v5.5.0/sentence-transformers v5.3.0). Every input gets nomic's required task-instruction prefix — used `"clustering: "` (matches our use case: grouping similar movies), not `"search_query"/"search_document"` (those are for query-vs-document retrieval).
- Matryoshka truncation to 384 follows nomic's documented recipe: layer-norm the full 768-dim output, slice to 384, re-normalize (`F.layer_norm` → slice → `F.normalize`).
- `model_version` now stores `"nomic-ai/nomic-embed-text-v1.5@384d"` (base model + truncation width together, since they jointly determine the vector space — a future switch to a different truncation width needs its own re-embed, and this makes that visible in the data itself).
- Added `einops` to `requirements.txt` (required by nomic's custom model code).

### Bug hit and fixed: CPU-only torch
Rebuilding after adding `einops` triggered a fresh, unpinned `torch` resolution that pulled the **GPU/CUDA build** — several GB of `nvidia-cudnn`/`nvidia-cublas`/`triton`/etc. wheels, completely unused since this container only ever runs on CPU. Fixed in `prefect-worker/Dockerfile` by installing a pinned CPU-only wheel first (`pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu`) before the general `requirements.txt` install, so pip's dependency resolver sees torch already satisfied and never reaches for the CUDA build. Cut the torch download from 526MB (+ ~1.5GB of CUDA packages) down to 174.6MB; final image settled at 2.2GB instead of an unbounded larger size.

### Verified: same stress-test movies as MiniLM, head-to-head
Re-ran identical k-NN sanity checks (*The Beekeeper*, *Inception*, *Fast X*, *Get Out*) against the same queries used for MiniLM. Nomic won decisively on every one:

| Movie | MiniLM top result | Nomic top result |
|---|---|---|
| *The Beekeeper* | *Ramona and Beezus* (before title-fix bug) / general action-thriller cluster (after) | **A Working Man** — Statham's *next* film with David Ayer, the best possible match |
| *Inception* | *Interstellar* at #3 | *Dark Knight Rises*, *Tenet*, *Interstellar* — 3 of 6 are Nolan's own films |
| *Fast X* | *F9* at distance 0.127 | *F9* at distance **0.046** — much tighter |
| *Get Out* | Neither *Us* nor *Nope* appeared in top 6 | **Us** and **Nope** rank #1 and #2 |

Cosine distances also tightened across the board (MiniLM ~0.11-0.16 → nomic ~0.05-0.10), indicating more confident, decisive clustering, not just better top-1 picks.

### Next steps
- Review-embedding pipeline (the original motivation for this migration) — new `review_embeddings` table, source TBD, using nomic at full native 768-dim rather than the 384-truncated version used for `movie_embeddings`
- Wire pgvector k-NN into `GET /movies/{id}/comps`, now with a meaningfully stronger embedding backing it

---

## BOM Backfill Completion (Full Corpus)

The full-corpus BOM run (started before the embedding migration, interleaved with it across several sessions) hit a real-world scraping reliability issue worth recording in detail, since the fix mattered.

### The 503 problem
After roughly an hour of sustained scraping at the original 1 req/sec rate, Box Office Mojo's error rate climbed sharply — from a normal few percent up to 45%, then 77%, then 73% on immediate back-to-back retries, even after a full 1-hour cooldown between attempts. Box Office Mojo has no official API or published rate limit (unlike TMDb's documented ~40 req/sec), so there was no stated threshold to target — the 503s were the only signal available, and they pointed to an undocumented, IP-level soft-block triggered by sustained request volume rather than a transient server issue (a real API rate-limit violation typically returns 429, not 503; a 503 from a struggling-but-not-actively-blocking server was the working hypothesis until behavior proved otherwise).

**Fix**: dropped `bom_client.py`'s self-imposed rate limit from 1 req/sec to 1 req/4sec (`RateLimiter(max_per_second=0.25)`). This fully resolved it — the final run against the last 826 movies completed with **zero errors**, versus the 45-77% error rates seen at the faster pace.

### Operational note: mid-run Docker Desktop restart
Partway through, the whole Docker Desktop daemon stopped (likely a system restart), silently killing the in-progress scraping container. No data was lost — Postgres's volume persisted independently, and the backfill's `LEFT JOIN ... WHERE box_office_totals.movie_id IS NULL` discovery query meant simply re-running `bom_backfill.py` picked up exactly where it left off, no manual bookkeeping needed. This is the same idempotency property that made the earlier 503-driven retries safe to just re-run rather than needing careful resumption logic.

### Final result
**4,394/4,394 movies have box office data. 0 missing. 23,131 `box_office_weekly` rows** (~5.3 weekends/movie average, consistent with typical theatrical runs). Combined with the full TMDb backbone (4,395 movies, 45,059 people, 94,803 credits) and the nomic-based `movie_embeddings` for all 4,395 movies, the full historical dataset described in the original plan's Step 2/3 scope is now completely populated.

### Next steps
- Feature engineering / staged model training can now begin in earnest — this was the "cold start problem... likely the biggest time sink" the original plan flagged, and it's done
- OMDb critic score pull (the remaining un-backfilled source from the original Step 4 build order)
- Reddit sentiment pull (lowest priority per the original plan, most fragile source)

---

## OMDb Critic Scores: On-Demand + Background Trickle (Built)

OMDb's free tier caps at **1,000 requests/day** with no way through it in one sitting — a bulk backfill of all 4,394 movies (like TMDb/BOM got) would take 5+ days. Rather than force that pattern, built a hybrid: fetch-and-cache on demand for whatever's actually being viewed, plus a slow background trickle that opportunistically fills in the rest under the daily cap.

### Schema
New `critic_scores` table (`db/init/003_critic_scores.sql`, applied live): `movie_id` (PK), `imdb_rating`, `imdb_votes`, `rotten_tomatoes_pct`, `metacritic_score`, `source`, `fetched_at`. Row presence = "fetched, don't refetch" for v1 — no staleness/refresh policy yet.

### On-demand path (`api/`)
`GET /movies/{id}` (`api/app/routers/movies.py`) now checks `critic_scores` first; on a cache miss, calls OMDb synchronously via the new `api/app/omdb_client.py`, caches the result, returns it inline. Added `httpx` to `api/requirements.txt` (not previously a dependency there) and `omdb_api_key` to `Settings`. Designed to degrade gracefully at every failure point — missing key, OMDb's daily-limit response, or any other exception all just return `critic_scores: null` rather than failing the whole movie detail request.

### Background trickle (`prefect-worker/`)
`prefect-worker/flows/omdb_trickle.py` — plain Python (same established pattern, no `@flow`/`@task`), processes up to `MAX_PER_RUN = 900` movies per run (headroom under the 1,000 cap for on-demand traffic), ordered by `release_date DESC NULLS LAST` so recently-released movies (most likely to be viewed soon) get filled in first. Stops immediately and reports clearly if OMDb signals its daily limit rather than continuing to burn calls on guaranteed failures. Meant to run once/day manually for now; a real schedule is a Prefect Cloud concern once that's configured.

### Duplication note
The OMDb client + parsing logic is intentionally duplicated between `api/` and `prefect-worker/` rather than shared — matches the existing architecture, where these two services already have zero shared code (even different DB access styles: SQLAlchemy Core vs. raw psycopg).

### Bug caught during verification (not a code bug — a key activation issue)
First live test returned `401 Unauthorized` from OMDb. Diagnosed by calling `omdb_client.fetch_critic_scores` directly inside the `api` container (bypassing the router's broad exception handler, which was silently swallowing the real error — worth knowing that handler intentionally hides errors from the response, so direct-client testing is the way to debug it). Turned out to be OMDb's email verification step not yet completed on the new key; worked immediately once activated.

### Verified end-to-end
- No key set → `critic_scores: null`, rest of movie detail still returns correctly
- Real key, cache miss → live OMDb fetch, correct parsing (*The Beekeeper*: IMDb 6.3, RT 71%, Metacritic 53), cached to `critic_scores`
- Repeat request → served from cache, confirmed via unchanged `fetched_at` (no second OMDb call)
- Trickle flow (capped at 5 for testing) → correctly prioritized the most recently released movies, handled movies missing specific scores (e.g. no RT % yet) gracefully

### Next steps
- Run the trickle flow daily (or once real Prefect Cloud scheduling is set up) until the historical corpus is fully covered
- Reddit sentiment pull (lowest priority per the original plan, most fragile source)

---

## Critic-Score Gap Investigation + Recent-Movie Refresh (Built)

After the first full trickle run (900 movies), some had missing Rotten Tomatoes (128) or Metacritic (106) scores. Investigated and addressed in four parts.

### #1/#2: Spot-check confirmed genuine OMDb-side gaps, not a bug
Called `omdb_client.fetch_critic_scores` directly against the raw OMDb API for *Talk to Me* (a well-reviewed 2023 horror film) — OMDb's own `Ratings` array only contained IMDb and Metacritic entries, no Rotten Tomatoes at all, despite the film certainly having a real RT score in the world. This confirmed the gaps are inherent to OMDb's own data completeness, not a parsing bug on our end, and not fixable without going directly to RT (which OMDb was chosen specifically to avoid). Decision: treat missingness as real signal (a movie some critics never scored/aggregated), not an error to chase — no code change, just documented as v1's stance. Side note: OMDb's raw response also includes a `BoxOffice` field (domestic gross) — redundant with our BOM data, not used.

### #3/#4: `prefect-worker/flows/refresh_recent.py` (new), scoped to recent movies only
Explicitly limited to `release_date >= CURRENT_DATE - 90 days` (includes upcoming/unreleased movies too, since those are trivially within the window) — older movies' gaps are permanent per the investigation above, so refreshing them has no payoff; per the original ask, "not worth the investment for older movies."

- **#3 (TMDb audience votes)**: added `tmdb_vote_average`/`tmdb_vote_count` columns to `critic_scores` — a supplementary audience-sentiment signal, not a critic score. Wasn't new data to fetch: `TMDbClient.get_movie_detail()` already returns these fields on every call; the original `tmdb_backfill.py` simply never persisted them. Reused the existing client method as-is rather than adding a slimmer one for two fields, since the recent-movies subset is small enough that the extra unused credits/release_dates payload is a negligible cost.
- **#4 (OMDb re-check)**: re-fetches OMDb for the same recent-movies subset, in case a movie was originally scored before its reviews caught up (embargo/early access). Reuses the existing `upsert_critic_scores` (`ON CONFLICT DO UPDATE`) — no new upsert logic needed.

New `db.py` helpers: `get_recent_movies`, `ensure_critic_scores_row` (`INSERT ... ON CONFLICT DO NOTHING`, so a movie with no OMDb data yet still gets a row for the TMDb-only fields), `update_tmdb_votes`.

Exposed via API: `CriticScoresOut` gained `tmdb_vote_average`/`tmdb_vote_count` (both defaulted to `None` — required to avoid breaking the on-demand path in `routers/movies.py`, which constructs `CriticScoresOut` from an OMDb-only dict that never has these two keys).

### Verified
18 movies fell in the 90-day window. All 18 got TMDb vote data populated — including *Avatar Aang: The Last Airbender*, which has zero OMDb data yet but got real TMDb votes (9.318 avg / 655 votes), exactly the gap-filling case this was built for. OMDb re-check ran cleanly alongside it, correctly leaving fields null where OMDb genuinely has nothing (consistent with the earlier finding — most of these are permanent gaps, not timing issues). Confirmed via `GET /movies/{id}` that both new fields surface correctly in the API response (*Toy Story 5*: `tmdb_vote_average: 7.413, tmdb_vote_count: 756` alongside its OMDb scores).

### Next steps
- Run `refresh_recent.py` periodically (e.g. weekly) alongside the daily `omdb_trickle.py`
- Reddit sentiment pull (lowest priority per the original plan, most fragile source)

---

## pgvector k-NN Wired into `/comps` (Built)

`GET /movies/{id}/comps` now supports both similarity methods via a `method` query param (`embedding` default, `heuristic` available too) rather than only the hand-written heuristic. `api/app/queries.py:get_comps_by_embedding` runs the same `<=>` cosine-distance query used to manually validate the nomic embeddings earlier, unparameterized on the Python side (no `pgvector` package needed in `api/` — that's only required where Python vectors get inserted, in `prefect-worker`).

`CompOut` extended with `distance: float | None` and `shared_genres`/`score` made optional (defaulted), since the two methods return different fields — embedding mode leaves `shared_genres`/`score` empty/null, heuristic mode leaves `distance` null.

### Verified
Both modes tested against *Get Out*: embedding mode returns *Us*/*Nope* at #1/#2 (distances 0.057/0.063, matching earlier manual verification exactly); heuristic mode also surfaces *Nope*/*Us* but via genre-overlap scoring instead. 404 still correctly returned for a nonexistent movie id.

### Next steps
- Feature engineering / staged GBT model pipeline — the actual core product feature (stage-by-stage verdict + confidence interval), not yet started; everything through this point has been the data layer
- Trailer/YouTube and Reddit sentiment ingestion
- Redis caching, automated tests, real Prefect Cloud scheduling

---

## Staged Verdict System v1: Comp-Based Heuristic (Built)

The first version of the project's actual core feature — per-movie, per-stage flop/solid/hit/blockbuster verdicts. Decided upfront (before planning) to ship a comp-based heuristic rather than trained GBT models first, build YouTube trailer ingestion now rather than defer it, and detect stage transitions via a daily scheduled scan rather than on-demand.

### Schema: `verdicts` table
New (`db/init/004_verdicts.sql`): `movie_id`, `stage`, `comp_count`, ROI percentiles (p25/p50/p75), `verdict_bucket`, `comp_movie_ids` (audit trail), plus `actual_roi_multiple`/`actual_bucket` computed the same way from the movie's own outcome once known — letting the heuristic's accuracy be measured directly rather than just asserted. `UNIQUE(movie_id, stage)`.

### Stage vocabulary and detection
Reuses `sentiment_snapshots`'s existing stage enum minus `casting_news` (no structured source exists for that — Reddit/Twitter still deferred). `detect_stage()` in `prefect-worker/flows/stage_scan.py` is a pure function with precedence `post_release > pre_release > trailer > teaser > announcement`, driven entirely by data already in the DB (`release_date`, `trailers.publish_date`).

### One flow, unified backfill + incremental scan
`get_movies_needing_stage_check` (new in `prefect-worker/db.py`) returns movies with no verdict row yet, or whose furthest-reached stage isn't `post_release` — meaning the very first run doubles as the full historical backfill (since ~4,394/4,395 movies are already fully released and land straight in `post_release`), while all future runs only touch genuinely active movies. No separate backfill script was needed.

### Comp-based verdict computation
Reuses the embedding `<=>` k-NN query from `api/app/queries.py:get_comps_by_embedding`, duplicated into `prefect-worker/db.py:get_comps_for_verdict` per the established cross-service pattern. ROI = `total_worldwide / budget_usd` across the top-15 comps that have both fields; percentiles computed in pure Python (sort + linear interpolation, no new dependency); median bucketed via the plan's original thresholds (<1x flop, 1-3x solid, 3-5x hit, 5x+ blockbuster). Fewer than 3 usable comps → row still written (audit trail) but `verdict_bucket`/percentiles left null rather than guessed.

### YouTube trailer ingestion (`prefect-worker/youtube_client.py`, new)
`search_trailer` (`search.list`, 100 quota units) and `get_video_stats` (`videos.list`, ~1 unit/call, batches of 50). Deliberately scoped to only search for movies not yet `post_release` and only once (until found) — `search.list` against the full 4,395-movie historical corpus would cost 439,500 units against a 10,000/day free quota, ~44x over, and low-value anyway per the plan's existing note that historical trailer velocity is unreliable.

### Verified
- First run: all 4,395 movies processed, zero errors, all landed in `post_release` (expected — corpus has no genuinely upcoming movies, see caveat below)
- 4,395 verdict rows written; bucket distribution: 970 solid, 846 flop, 531 blockbuster, 450 hit (actual outcomes) / 2,478 solid, 771 hit, 552 flop, 330 blockbuster, 264 insufficient-data (predicted)
- **Accuracy check** (the whole point of storing `actual_bucket` alongside the prediction): strict exact-match accuracy is **36.1%**, barely above the naive **34.7%** baseline of always guessing "solid" (the most common actual outcome) — the v1 heuristic has only marginal signal for fine-grained classification. But **83.3% land within one bucket** of the truth, meaning it does capture rough scale even though precision is weak. This is exactly the outcome the plan anticipated: a real baseline for comparison, not a finished predictor — validates prioritizing this over jumping straight to GBT models, since now there's a concrete number to beat.
- `GET /movies/{id}/verdicts` verified against *The Beekeeper*: predicted "solid" (comp median 1.72x ROI) vs. actual "hit" (4.65x) — a representative example of the adjacent-bucket-but-not-exact pattern from the accuracy check
- Re-ran `stage_scan.py` a second time: 0 movies needed rechecking, confirming idempotency

### Early-stage/YouTube path exercised (closed the verification gap)
Pulled 20 genuinely upcoming movies via a scoped TMDb discover call (`primary_release_date.gte=2026-08-06`, `.lte=2027-02-05`, `min_vote_count=0`, `sort_by=popularity.desc`, 1 page) — `min_vote_count` had to drop to 0 since unreleased titles have near-zero TMDb votes; `sort_by` gained a parameter (previously hardcoded to `primary_release_date.asc`) so this one-off pull could rank by popularity instead and surface notable titles (*Avengers: Doomsday*, *Dune: Part Three*, *Ramayana*, *Coyote vs. Acme*) rather than whatever happened to release first. Built embeddings for the 20, then ran `stage_scan` twice — once before adding a real `YOUTUBE_API_KEY` (`.env` had the placeholder still blank, silently producing zero trailer matches — not a code bug), once after.

- **First run** (no YouTube key): correctly split the 20 into `announcement` (8) / `pre_release` (12) purely from release-date windowing — confirms `detect_stage`'s date-based branches work standalone.
- **After adding the key**: re-ran `stage_scan`; all 20 picked up real trailers (18 `trailer`, 2 `teaser`) via `search_trailer`, each with real `trailer_metrics` (e.g. *Avengers: Doomsday*: 58.9M views, 2.5M likes). Confirmed `GET /movies/4891/verdicts` (Avengers: Doomsday) returns **two independent rows** — the original frozen `announcement` verdict plus a new `trailer` verdict — proving the "prior stage's row is never touched again" design actually holds under a real stage transition, not just in theory.
- Comp verdicts for the 20 upcoming movies ranged `solid` to `blockbuster` (no `flop`/`hit` bimodal pattern beyond that), all with `actual_bucket: null` as expected (no box office yet).

### Next steps
- Trailer engagement / critic scores feeding into comp weighting, so the confidence interval actually narrows by stage (the explicitly-deferred limitation from this pass)
- Reddit sentiment pull, Redis caching, automated tests, real Prefect Cloud scheduling

## GBT Model Training v1 (Built)

Trained an actual predictor (`prefect-worker/flows/train_model.py`) to compare against the comp heuristic's 36.1%/83.3% baseline, using the identical ROI-multiple target and bucket thresholds (imported from `stage_scan.py`, not duplicated — same service). Like the heuristic, v1 predictions are **precomputed in batch and stored** in `verdicts` (now `method='gbt_v1'`), not served live in-process — the "in-process serving" architecture already decided in the Model Serving section is deferred until there's a concrete need the daily batch can't cover (e.g. an on-demand prediction for a movie the batch hasn't reached).

### Approach
- **Three LightGBM quantile boosters** (`objective="quantile"`, alpha 0.25/0.5/0.75, native `lgb.train()` API — not the sklearn wrapper, keeps a future `api/` load-side dependency to just `lightgbm`) trained on `log(ROI multiple)`, producing the same `roi_multiple_p25/p50/p75` shape the heuristic already stores. Quantile-crossing guarded by sorting the three predictions per row at inference time.
- **Pre-release-only features**, matching the heuristic's own stated limitation, for a fair comparison: log budget, runtime, MPAA rating, is-English, release month/season, top-15 genre multi-hot, is-franchise, and — the most predictive group by feature-importance gain — **time-respecting expanding-average ROI** for the movie's studio, primary director, lead actor, and franchise (computed only from that entity's strictly-earlier releases, leakage-safe). Missing prior-averages (new director, non-franchise, etc.) are left as `NaN` — LightGBM handles missing values natively.
- **Time-based split**: sorted by release date, last 20% (560 of 2,797 labeled movies, cutoff 2021-07-29) held out as test — avoids sequel-leakage a random split would allow, and simulates real forward deployment.
- **Schema change**: `verdicts`'s UNIQUE constraint widened from `(movie_id, stage)` to `(movie_id, stage, method)` (`005_verdicts_multi_method.sql`) so `gbt_v1` rows coexist with `comp_heuristic_v1` rows — `upsert_verdict` gained a `method` parameter (defaulting to `comp_heuristic_v1` so `stage_scan.py` needed no changes beyond the `ON CONFLICT` clause). `GET /movies/{id}/verdicts` needed zero code changes — it already returns every matching row as a list.
- **Batch inference covers every movie with a budget** (2,977 of 4,415 — including unreleased ones with a known budget, like *Ramayana*/*Coyote vs. Acme*/*Digger* from the upcoming-movies pull), using each movie's current latest stage from existing verdict rows.

### Verified
- Build hit one real gotcha: LightGBM's compiled backend needs `libgomp1`, absent from the `python:3.12-slim` base — added `apt-get install libgomp1` to `prefect-worker/Dockerfile`.
- **GBT vs. comp heuristic, same 559-movie holdout** (a like-for-like rerun of the heuristic's accuracy check, scoped to the same test set the GBT never saw): GBT **40.7% exact-match / 86.1% within-one-bucket** vs. heuristic **36.3% exact-match / 86.9% within-one-bucket**. The GBT modestly beats the heuristic on exact classification; within-one-bucket is essentially a wash — an honest, non-dramatic result, not a clean sweep.
- Feature importance (gain): `log_budget` dominates, followed closely by the three prior-average-ROI features (studio, director, actor) — confirms the leakage-safe track-record features are pulling real weight, not just budget.
- `SELECT method, count(*) FROM verdicts GROUP BY method` → 4,435 `comp_heuristic_v1` / 2,977 `gbt_v1`, as expected (GBT skips the ~1,438 movies with no budget yet).
- Re-ran `stage_scan.py` after the constraint change — still upserts idempotently, no regression.
- `GET /movies/{id}/verdicts` for *Ramayana*: both methods present at the `trailer` stage; GBT's percentile band (1.87x–4.98x) is visibly tighter than the heuristic's (0.98x–8.20x) around the same 3.4-3.5x median — a good qualitative sanity check that the trained model is genuinely more decisive, not just noise.

### Next steps
- Live in-process serving in `api/` once there's a concrete case the daily batch can't cover
- Reddit sentiment pull, Redis caching, automated tests, real Prefect Cloud scheduling

## GBT Model v2: Critic-Score Features (Built)

Added critic scores (IMDb rating/votes, Rotten Tomatoes %, Metacritic, TMDb vote aggregates) as additional features to the same `train_model.py` pipeline, additive to v1's feature set rather than a separate model — LightGBM handles missing values natively, so one model transparently uses critic signal when present and falls back to v1's behavior when absent. Writes to `verdicts` as `method='gbt_v2'`, coexisting with `comp_heuristic_v1`/`gbt_v1` (no further schema changes needed beyond v1's `(movie_id, stage, method)` constraint).

Trailer engagement was explicitly scoped out of this pass: zero movies currently have both trailer stats and a known box-office outcome (the only 20 movies with trailers are the still-unreleased ones pulled earlier), so there's nothing to train against yet.

### A real data-coverage bug found and fixed along the way
First training run produced **byte-for-byte identical** results to `gbt_v1` (same MAE, same bucket accuracy) with all 6 new critic-score features showing **exactly 0.0 gain** — not a "no signal" finding, a red flag. Root cause: all 604 movies with critic scores fell *after* the model's 2021-07-29 time-split cutoff (OMDb ingestion, via `get_movies_missing_critic_scores`, prioritizes recent releases for dashboard freshness — never did a real historical backfill). The training set had literally zero examples with a critic score to learn from.

Fixed by adding a second, purpose-built backfill: `get_budgeted_movies_missing_critic_scores` (`prefect-worker/db.py`) + `prefect-worker/flows/critic_score_backfill.py`, oldest-released-first and restricted to budgeted movies — the direct inverse priority of the existing recency-ordered `omdb_trickle.py`, since the goal here is training coverage, not viewing freshness. Same OMDb-quota-aware pattern (stop cleanly on `OMDbRateLimited`, 900/run cap).

Running it also surfaced a **real pre-existing bug** in `omdb_client.py` (both the `api/` and `prefect-worker/` copies): OMDb returns its daily-quota-exhausted message (`{"Response":"False","Error":"Request limit reached!"}`) with HTTP status **401**, not 200 — the existing code called `resp.raise_for_status()` before checking the response body, so the quota signal was never caught as `OMDbRateLimited` and instead fell through as a generic per-movie error, burning ~800 wasted requests against the daily cap logging 401s before this was caught. Fixed by checking the body on a 401 status before `raise_for_status()` in both copies.

### Verified
- After the fix: two backfill runs in one day yielded **1,000 pre-cutoff budgeted movies** with real critic scores (up from 0) — enough for LightGBM to actually learn from.
- Retrained `gbt_v2`: **47.0% exact-bucket-match / 90.4% within-one-bucket** on the same 559/560-movie holdout used for all three methods — a real jump over both `gbt_v1` (40.7%/86.1%) and `comp_heuristic_v1` (36.3%/86.9%), not a rounding-error improvement.
- Feature importance (gain): `log_budget` still #1, but `log_imdb_votes` jumped straight to #2, with `imdb_rating` and `rotten_tomatoes_pct` both in the top 10 — critic scores earned real weight, not token inclusion.
- `SELECT method, count(*) FROM verdicts GROUP BY method` → `comp_heuristic_v1` 4,437 / `gbt_v1` 2,977 / `gbt_v2` 2,977.
- `GET /movies/4/verdicts` (The Beekeeper, actual outcome: 4.65x ROI, "hit"): heuristic predicted "solid" (wrong), both `gbt_v1` and `gbt_v2` predicted "hit" (correct), with `gbt_v2`'s band (2.40x–3.21x) tighter than `gbt_v1`'s (1.86x–3.89x) around the same true value.

### Next steps
- Continue the `critic_score_backfill` flow daily until pre-cutoff coverage saturates (currently 1,000 of the training set's older budgeted movies; OMDb's 1,000/day cap means this is gradual) — retrain `gbt_v2` periodically as coverage grows
- Trailer engagement: revisit once enough of the 20 upcoming movies actually release and accumulate real outcomes to train against
- Reddit sentiment pull, Redis caching, automated tests, real Prefect Cloud scheduling

### 2026-08-08 retrain — Wikidata budget backfill + more critic-score coverage
Retrained `gbt_v2` after the Wikidata budget backfill (+42 movies with budgets) and further `critic_score_backfill`/`omdb_trickle` runs grew coverage (`budget_usd` now on 3,022 movies, `critic_scores.imdb_rating` on 2,880). Training pool grew to 3,022 budgeted movies (2,266 train / 567 test, time-split at 2021-07-28, up from the 559/560-movie holdout in the original write-up above).

**Hit and fixed a real bug getting here**: `train_model.py`'s 3-way comparison query pulled frozen `comp_heuristic_v1`/`gbt_v1` verdict rows filtered only on `verdict_bucket IS NOT NULL`, not `actual_bucket IS NOT NULL`. Some of those frozen rows were written back when their movies were still unreleased and never got backfilled with an outcome — with the larger/shifted test set, one such row surfaced and crashed `_bucket_accuracy` on `None`. Fixed by adding `AND v.actual_bucket IS NOT NULL` to that query (`prefect-worker/flows/train_model.py`) — doesn't touch the evaluation methodology, just guards against comparing on rows with no known outcome, which was always the intent.

Results: **`gbt_v2` 49.4% exact / 90.8% within-one** vs `gbt_v1` 40.9%/86.1% and `comp_heuristic_v1` 36.3%/87.0% (on 562-563 test movies) — a modest but real improvement over the original write-up's 47.0%/90.4% for `gbt_v2`, consistent with "more data, same signal" rather than a step change. Top features unchanged in character: `log_imdb_votes` #1 this run (was #2), `log_budget` #2, critic-score features (`imdb_rating`, `rotten_tomatoes_pct`, `metacritic_score`) still solidly in the top 10. Wrote 3,022 fresh `gbt_v2` verdict rows (up from 2,977).

**Unreleased-movie coverage is the real limiter, not the model**: of the 18 movies with `release_date > CURRENT_DATE`, only 5 have a `budget_usd` and therefore a `gbt_v2` verdict (The End of Oak Street, Coyote vs. Acme, The Dog Stars, Digger, Ramayana) — all landed in the "solid" bucket, p50 ROI 1.16x-2.52x. Neither Avengers: Doomsday nor Dune: Part Three has a budget yet, so neither has a batch verdict; the live `/predict` endpoint returns a clean `reason: "no budget"` 200 for both, matching the documented behavior above. The Wikidata backfill's 42 recovered budgets (see below) didn't happen to include any of the still-unbudgeted tentpoles.

## Wikidata Budget Backfill (Built)

1,438 of 4,415 movies (33%) had no `budget_usd`, permanently excluding them from every ROI-based verdict. Investigated the gap directly rather than assuming it was an ingestion bug: it skews heavily international (Japanese anime, Korean thrillers, German comedies) — TMDb's own crowd-sourced budget data is Hollywood-centric, so this is a real source gap.

Checked two alternatives against real examples pulled from the gap: **Wikidata** (queried by IMDb id, P345→P2130) hit for *The Addams Family 2* ($23M) but missed two of the international titles tested; The-Numbers.com wasn't pursued (Hollywood-centric, unlikely to help a disproportionately-international gap). Went with Wikidata: free public SPARQL endpoint, no API key, exact-match via a stable id already on every movie, and its `VALUES` clause supports batching many ids per query.

### Approach
- `prefect-worker/wikidata_client.py` (new): batched SPARQL lookup, filtered to **USD-only** budgets (`wikibase:quantityUnit = wd:Q4917`) — a deliberate scoping call, since many international films' Wikidata budgets are recorded in local currency and currency conversion (historical exchange rates) was judged not worth the complexity for this pass. Non-USD entries are skipped, not converted or guessed.
- `prefect-worker/flows/budget_backfill.py` (new): pulls all budget-missing movies, batches, updates `budget_usd`/`budget_confidence='estimated'` for matches (`db.py`'s new `get_movies_missing_budget`/`update_movie_budget`).
- Designed as a single-run backfill (Wikidata's `VALUES` batching meant the whole 1,437-movie backlog only needed ~29 batches), not a multi-day trickle like the OMDb critic-score backfill.

### An active external outage hit mid-build, handled the same way as the earlier OMDb 401 bug
First run: batch 1 (100 ids) succeeded (3 matches), then every subsequent batch hit a 429 with `"Aggressively rate-limiting to 1 req/min - this rule was created during active wdqs outage"` — a real, temporary Wikidata infrastructure incident, not something in our control. The initial code caught this as a generic exception and burned through all 14 remaining batches uselessly, logging the same 429 repeatedly — the identical shape of bug just fixed in `omdb_client.py`. Fixed properly: added `WikidataRateLimited` (mirroring `OMDbRateLimited`), dropped batch size 100→50, and added retry-with-backoff (5 attempts, 65s apart, matching the outage's own stated 1-req/min throttle) in `budget_backfill.py` rather than giving up on the whole run at the first 429.

### Verified
- Ran the fixed version as a background task (~30 min, paced by the outage throttle): **42 of 1,437 movies matched** (real budgets recovered, e.g. *Fountain of Youth* $180M, *Luck* $140M) — `SELECT count(*) FROM movies WHERE budget_usd IS NULL` dropped from 1,438 to 1,396.
- ~8 of ~29 batches (400 movies) never got a successful query at all (exhausted all 5 retries against the ongoing outage) — genuinely unattempted, not confirmed-absent. A rerun once Wikidata's outage clears should recover more from exactly those movies (the idempotent `WHERE budget_usd IS NULL` query naturally re-targets only what's still missing, no extra bookkeeping needed).
- Honest coverage read: 42/1437 (~3%) is a modest, partial win, consistent with the USD-only + Wikidata-coverage limitations flagged going in — this doesn't come close to closing the international-title gap that motivated the search, but it's real, free coverage with no ongoing cost.

### Additional source investigated and rejected: The-Numbers.com
Looked for a second budget source to cover more of the remaining gap (1,396 of 1,438 originally missing, still uncovered after Wikidata). The-Numbers.com was the obvious next candidate — a real budget-tracking trade site — but two problems surfaced on direct investigation, not assumption:
- **No documented search API or reliable URL pattern.** Its movie URLs need title+year+**country** disambiguation (e.g. `/movie/September-5-(2024-Germany)`), and its canonical titles don't always match ours (our `"Ghostland"` is their `"Incident in a Ghostland"`) — would need real search/matching infrastructure, not simple slug construction, i.e. BOM-level scraper fragility risk a second time.
- **Budgets are paywalled for most titles.** A 7-movie probe (fetching actual pages directly, since search-engine-summarized answers turned out unreliable — one reported a $40M figure for *The Two Popes* that wasn't actually on the page) found only **2 of 7 (~29%) had a public budget figure**; the rest showed "full financial estimates... available through our research services" instead.

Given ~29% publicly-available *before* even accounting for real-world match-rate loss from the title-matching problem, the expected yield didn't justify the scraper-fragility cost. Decision: not pursued. Recorded here so this path isn't re-investigated from scratch later — the negative result is the useful part.

### A fourth source checked, same ceiling: Box Office Mojo's own Budget field
Before writing off further budget sourcing, checked whether Box Office Mojo — already scraped reliably via `bom_client.py`'s proven, IMDb-ID-keyed pattern (no title-matching risk, unlike Wikidata/The Numbers) — exposes budget on the title pages already being fetched for box office. It does (`Budget$190,000,000` for a well-known blockbuster tested first), which looked promising since it would've meant near-zero incremental scraping risk.

But a 12-movie probe across the actual remaining gap (random sample, mixed English/international) found only **2/12 (~17%) had a budget on BOM** — the same pattern seen on TMDb, Wikidata, and The Numbers: present for well-known titles, absent for the smaller/mid-tier films that make up most of the remaining gap. **Four independent sources now show the same ceiling.** This reads less like "haven't found the right source" and more like a genuine data-availability limit — budgets for smaller and international films simply aren't well-documented in public English-language sources. Decision: not pursued further, despite BOM's low implementation risk, since the expected yield doesn't justify even a low-risk re-scrape. Budget coverage for this segment of the corpus is treated as a real, structural gap going forward, not a to-do.

### Next steps
- Rerun `budget_backfill.py` once Wikidata's outage clears to pick up the ~400 never-attempted movies
- Retrain `gbt_v1`/`gbt_v2` to pick up the newly-budgeted movies (not done automatically by this backfill)
- Reddit sentiment pull, Redis caching, automated tests, real Prefect Cloud scheduling

## Live In-Process GBT Serving in `api/` (Built)

Closed the "batch-only" gap flagged in both GBT write-ups: a movie added (or budgeted) after the last `train_model.py` run previously had no prediction until the next manual retrain. Implements Path 1 from the Model Serving section above (already decided): FastAPI loads the `gbt_v2` boosters into memory and calls `predict()` directly in the request handler — `GET /movies/{id}/predict`, computed live and never persisted, distinct from `/verdicts`' stored historical timeline.

### Approach
- **Model artifacts moved to a shared top-level `models/`** directory (was `prefect-worker/models/`, only reachable from one container) — bind-mounted read-write into `prefect-worker` and read-only into `api`. `train_model.py`'s `MODEL_DIR` needed no code change (`dirname(__file__)/../models` already resolved to the same `/app/models` container path either way).
- **`prefect-worker/flows/train_model.py` now exports prior-avg-ROI lookups**: the leakage-safe expanding-mean features (`studio_prior_avg_roi` etc.) only ever existed as an in-memory pandas computation. Added `_entity_avg_lookup()` — a plain (non-expanding, all-history) per-entity mean, folded into `feature_metadata_gbt_v2.json` under `prior_avg_lookups` — a deliberately simpler "current snapshot" used only at serving time, not fed back into training.
- **`api/app/gbt_predictor.py`** (new): single-row mirror of `train_model.py`'s feature building, duplicated per the established cross-service pattern. No pandas/scikit-learn added to `api/` — just `lightgbm`, since native `Booster.predict()` accepts plain lists and categorical encoding (`mpaa_rating`) is replicated via a plain index lookup into the saved `mpaa_categories` list rather than needing a real pandas `category` dtype. Lazy-loaded module singleton, same shape as `prefect-worker/embedding_client.py`'s `_get_model()`.
- **`api/app/queries.py`** gained `get_primary_credits()` — a lighter single-movie director/lead-actor id lookup than the full `get_movie_credits()` list.
- **Movies without a budget get a clean 200**, not an error: `LivePredictionOut` has a `reason` field (`"no budget"`) with all ROI fields `null`, mirroring how `/comps`/`/verdicts` already degrade gracefully.

### Verified
- Both `api` and `prefect-worker` Dockerfiles needed the same `libgomp1` fix already hit in GBT v1 (LightGBM's compiled backend, missing from `python:3.12-slim`).
- `GET /movies/4892/predict` (Ramayana, budgeted but not yet released): live p50 = 3.83x → 4.42x depending on run, bucket `hit` — close to but not identical to the stored batch `gbt_v2` row (p50 3.83x, also `hit`), exactly the expected divergence from live lookups being plain means vs. training's leakage-safe expanding means, not a bug.
- `GET /movies/4891/predict` (Avengers: Doomsday, no budget yet): clean `200` with all fields `null` and `reason: "no budget"`.
- `GET /movies/999999/predict`: `404`, as expected.

### Next steps
- Reddit sentiment pull, Redis caching, automated tests, real Prefect Cloud scheduling

## Trailer Backfill for the Training Corpus (Built)

The GBT v2 write-up flagged trailer engagement as scoped out because zero movies had both trailer stats and a known outcome. Root cause, confirmed by reading `stage_scan.py`: it only ever searches YouTube for trailers on movies **not yet `post_release`**, specifically to conserve `search.list`'s 100-unit cost against YouTube's 10,000/day free quota (~100 searches/day possible at all). The already-released, budgeted, outcome-known corpus that `train_model.py` actually trains on (~3,000 movies via `get_movies_for_training`) had never had a trailer search run against it — the only 20 existing trailer rows were all from a batch of still-unreleased test movies with no outcome yet.

### Approach
- `prefect-worker/db.py` gained `get_released_movies_missing_trailer(cur, limit)`: released (`release_date <= CURRENT_DATE`), `budget_usd` set, has a `box_office_totals` row, no `trailers` row yet — the same population `get_movies_for_training()` selects, joined against what's missing. Ordered most-recent-release-first: recent titles are far more likely to return a real official trailer from a plain title search than older/obscure ones (unrelated or fan-made results), maximizing hit rate per unit of quota.
- `prefect-worker/flows/trailer_backfill.py` (new): plain-Python flow (no `@flow`/`@task`, matching the established pattern), reusing `youtube_client.py`'s existing `search_trailer`/`get_video_stats`/`YouTubeQuotaExceeded` and `db.py`'s existing `get_trailers_for_movie`/`insert_trailer`/`upsert_trailer_metrics` unchanged. `MAX_PER_RUN = 90`, leaving headroom under the ~100/day ceiling. Stops cleanly on `YouTubeQuotaExceeded`, same shape as `critic_score_backfill.py`'s OMDb handling — no retry loop.
- Deliberately additive: `stage_scan.py` was not touched and keeps its existing not-yet-post_release-only trailer search behavior for its own purpose (ongoing stage detection).

### Verified
- Ran once: **90/90 movies processed, 90/90 got a matching trailer** (every recent, well-known, budgeted title returned a real official-trailer hit — no misses this run, though that won't hold as the backlog moves to older/smaller titles).
- `trailer_outcome_pairs` (trailers joined to a budgeted movie with a `box_office_totals` row): **0 → 90**. This is the number that actually matters — it was the literal blocker for training on trailer engagement at all.
- Total `trailers` rows: 20 → 110.
- Remaining backlog: 2,926 released/budgeted/outcome-known movies still missing a trailer (3,016 before this run).
- Also ran `critic_score_backfill.py` and `omdb_trickle.py` in the same session to keep pushing critic-score coverage: both reported **0/795 and 0/900 processed respectively, hitting OMDb's daily rate limit immediately** — the day's 1,000-request OMDb quota was already exhausted by earlier work before these runs started. Critic-score coverage is unchanged this run: 2,880 movies overall with an IMDb rating, 2,219 of those among budgeted movies (out of 3,022 budgeted movies total, ~73.4%).

### Next steps
- **Re-run daily** — YouTube quota resets every 24h and this only gets through ~90 movies/day against a 2,926-movie backlog (~33 days at this rate, assuming hit rate stays high): `docker compose run --rm --no-deps prefect-worker python -m flows.trailer_backfill`
- Once enough (trailer, known-outcome) pairs accumulate (dozens isn't enough for LightGBM to find real signal — likely need low hundreds at least), add trailer engagement (view/like/comment counts) as `gbt_v3` features, same additive pattern as v2's critic scores
- Re-run `critic_score_backfill.py`/`omdb_trickle.py` on a day when OMDb's quota hasn't already been used by other work, to keep closing the remaining critic-score gap (803 of 3,022 budgeted movies, ~26.6%, still missing a score)
- Reddit sentiment pull, Redis caching, automated tests, real Prefect Cloud scheduling

### Bug fixed 2026-08-10: YouTube 429 misclassified as a generic per-item error
Running all backfills in parallel surfaced a fourth instance of the same bug class hit earlier this session (OMDb 401, Wikidata 429, Wikipedia's anonymous burst limit): YouTube's `_get()` in `youtube_client.py` only treated `403 + "quota" in body` as the "stop the run" signal, so a genuine `429 Too Many Requests` (a short-term burst limit, distinct from daily quota exhaustion — likely triggered by running trailer_backfill concurrently with other flows) fell through to `raise_for_status()` as a generic per-item error. `trailer_backfill.py`'s broad `except Exception: continue` then burned through 67 of a 90-movie batch logging the same 429 repeatedly instead of stopping (only 23/90 matched that run, vs. 90/90 the prior run). Fixed by also raising `YouTubeQuotaExceeded` on 429, not just the quota-403 case. Confirmed working: the very next run reported a clean `"daily quota exhausted after 0/90 - stopping"` instead of 90 wasted retries.

## Reddit Sentiment Ingestion v1 (Built, blocked on credentials)

The lowest-priority, explicitly-deferred data source from the original plan ("most fragile source," never built). Picked up now. Two distinct populations, per the product thesis: **pre-release buzz** (`movies.release_date > CURRENT_DATE`) — a genuinely new signal not available from any other source in the pipeline — and a **historical backfill for released movies**, scoped to exactly the population that matters for GBT training (`budget_usd` present AND a `box_office_totals` row), so this becomes a usable model feature rather than a display curiosity.

### Approach
- **`prefect-worker/reddit_client.py`** (new): OAuth2 client-credentials grant (Reddit "script" app, app-only/read-only — no end-user login needed for a server-side search job). Token cached in-process. Searches a fixed multi-subreddit set (`movies`, `boxoffice`, `trailers` — `DEFAULT_SUBREDDITS`, could be made configurable later) via `/r/{sub1}+{sub2}+{sub3}/search`, quoting the title and appending the release year to cut down false matches on generic titles. Same rate-limit-before-`raise_for_status()` lesson as `omdb_client.py`/`wikidata_client.py`: checks for `429` (and `403`, which for Reddit usually means an expired/invalid token, not "no results") before `raise_for_status()` would otherwise mask either as a generic HTTP error. `RedditRateLimited`/`RedditAuthError` let calling flows stop cleanly instead of hammering a wall. `RateLimiter(max_per_second=0.9)`, staying under Reddit's ~60 req/min script-app ceiling with margin.
- **`prefect-worker/reddit_sentiment.py`** (new): pure aggregation, shared by both flows so they compute metrics identically. Primary v1 metrics — mention volume (post count) and average engagement (Reddit's upvote-based post `score`) — are the trustworthy signal per the task scope. A lexicon-based sentiment score (~25 hand-picked positive/negative words, matched against post title+selftext) is the explicit stretch goal; it returns `None` (not a fake `0.0`) when a movie has zero lexicon hits, so "no signal" is never conflated with "neutral."
- **`sentiment_snapshots` didn't fit as originally scaffolded** — checked before assuming it was right, per the task instructions. Its `source`/`stage`/`sentiment_score`/`volume`/`raw_sample_ids` columns all lined up, but two things were missing: no column for the primary engagement-score metric, and no uniqueness constraint to upsert against (it was designed as an open-ended append-only time series, but a "refresh this stage's snapshot in place" model — same as `verdicts`' `(movie_id, stage, method)` upsert — is simpler and matches how every other re-run in this pipeline behaves). `db/init/006_sentiment_snapshots_reddit.sql` adds `avg_engagement_score NUMERIC` and `UNIQUE (movie_id, stage, source)`; applied directly to the live DB via `docker compose exec postgres psql` since `db/init/` only runs on a fresh volume.
- **`db.py`** gained three functions: `get_upcoming_movies_for_sentiment()` (the full unreleased set — no `LIMIT`, no "missing" filter, since buzz is expected to change run over run and the upsert just refreshes in place), `get_movies_for_reddit_backfill(limit)` (mirrors `get_movies_for_training()`'s core filter, oldest-first, excludes movies with an existing `post_release`/`reddit` snapshot), and `upsert_sentiment_snapshot()`.
- **Two flows, not one** — deliberate split, matching the two populations' very different operational shape: `flows/reddit_buzz_upcoming.py` processes the whole (small, currently 18-movie) unreleased set every run, meant to be re-run eagerly/often since pre-release buzz is time-sensitive. `flows/reddit_sentiment_backfill.py` is the large, quota-throttled historical job (`MAX_PER_RUN = 250`, one Reddit request per movie at ~1 req/sec ≈ 4-5 min/run), meant to be re-run daily until it reports 0 remaining, same pattern as `critic_score_backfill.py`. Both are plain functions, no `@flow`/`@task`, per the established project convention.

### Verified
- `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` in `.env` are still empty placeholders (`REDDIT_USER_AGENT` has a placeholder value too — `filmybox/0.1 by yourusername`). **No real API calls have been made; this cannot ingest real data yet.**
- Migration applied to the live DB: `ALTER TABLE sentiment_snapshots ADD CONSTRAINT ... UNIQUE (movie_id, stage, source)` and `ADD COLUMN avg_engagement_score NUMERIC` both ran clean against the running `postgres` container.
- `get_upcoming_movies_for_sentiment()` against live data returns 18 movies (earliest: two titles releasing 2026-08-12). `get_movies_for_reddit_backfill(5)` correctly returns the oldest budgeted+box-office movies (`Daybreakers`, `Leap Year`, `Henry's Crime`, `Tooth Fairy`, `The Book of Eli`, all Jan 2010) — confirms the training-population filter and ordering are right.
- Ran `reddit_buzz_upcoming_flow()` for real against the live DB with `search_movie_mentions` monkeypatched to return two fixed fake posts (no real network call — no credentials to make one with): confirmed the full path — aggregation (`volume=2`, `avg_engagement_score=62.5`, `sentiment_score=-0.5` from the fake lexicon-negative post) → upsert → all 18 rows landed correctly in `sentiment_snapshots`. **Deleted these 18 mocked rows afterward** so no fake sentiment data is left in the live database.
- Confirmed the empty-credential path exits cleanly: `docker compose run --rm --no-deps prefect-worker python -m flows.reddit_buzz_upcoming` prints `REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET not set, skipping` and exits 0, same shape as `critic_score_backfill.py` without `OMDB_API_KEY`.
- Not verified (no credentials): real Reddit search results, real rate-limit handling against Reddit's actual 429 behavior, real-world lexicon sentiment quality (the 25-word list is a rough first pass, not tuned against any labeled data).

### Next steps
1. **Create a Reddit "script" app**: go to https://www.reddit.com/prefs/apps while logged into a Reddit account, click "create app," choose type **script**, leave the redirect URI as `http://localhost:8080` (unused by client-credentials but required by the form). This gives a client ID (under the app name) and a client secret.
2. Set `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` in `.env` to those values, and replace `REDDIT_USER_AGENT`'s placeholder (`filmybox/0.1 by yourusername`) with a real Reddit username per Reddit's API rules (unique, descriptive user agents are required — generic ones get silently throttled harder).
3. First real run, small population first to sanity-check real output before the larger batch job:
   ```
   docker compose run --rm --no-deps prefect-worker python -m flows.reddit_buzz_upcoming
   docker compose run --rm --no-deps prefect-worker python -m flows.reddit_sentiment_backfill
   ```
4. Re-run `reddit_sentiment_backfill` daily (or on a schedule once real Prefect Cloud scheduling lands) until it reports 0 remaining — likely several dozen runs given the training population size.
5. Once real data exists, feed `avg_engagement_score`/`sentiment_score`/`volume` into `train_model.py` as new GBT features (not done here — out of scope for ingestion v1) and evaluate whether they actually improve `gbt_v2`'s predictions before committing to them long-term, given the "most fragile source" concern that deferred this in the first place.

## Thread-Based Sentiment: YouTube Trailer Comments + Bluesky (Built)

Reddit sentiment was fully built but blocked on an unpredictable external gate: Reddit's 2026 "Responsible Builder Policy" closed self-service registration, requires filing a ticket and waiting for approval, and explicitly calls out ML-training use cases as needing separate sign-off — reports describe hobbyist requests being ghosted rather than denied, no reliable timeline. Rather than wait, added two more thread-based sources that don't have that problem.

### Sources chosen and why
- **YouTube trailer comments** — the most directly on-topic signal possible: literal reactions to the trailer/teaser itself, not just title mentions elsewhere. `commentThreads.list` costs 1 quota unit/call (vs. 100 for the `search.list` calls `trailer_backfill.py`/`stage_scan.py` already use), trivial against the shared 10,000/day budget. No new credentials — reuses `YOUTUBE_API_KEY`.
- **Bluesky** — free and self-service (a real account + an instantly-generated "app password," no approval queue), unlike Reddit. Verified empirically before building anything: `public.api.bsky.app` (the endpoint some guides describe as "no auth needed") blocks non-browser traffic at the CDN layer with a raw 403 — not a real API response — while the actual PDS endpoint `bsky.social` returns a clean `{"error":"AuthMissing"}` for search without a session token. So real auth is required, just self-service rather than approval-gated.
- The-Numbers/Letterboxd/X considered and rejected before building anything: X's free tier is gone (pay-per-use, $0.005/read, no free tier); Letterboxd's API is by-request-only (same slow-approval shape as Reddit) and review-focused rather than thread-based, not matching what was actually asked for.

### Approach
- **Generalized the shared sentiment-scoring module** rather than write a third copy of the lexicon/aggregation logic: `reddit_sentiment.py` → `sentiment_scoring.py`, `summarize_posts(posts)` → `summarize_items(items)` taking a source-agnostic `{"id", "text", "engagement"}` shape. Both existing Reddit flows updated to normalize their Reddit-specific post shape into this before calling — no behavior change, just DRY.
- **`youtube_client.py`** gained `get_top_level_comments()` — top-level comments only for v1 (no reply-thread traversal, matches this project's repeated "keep v1 scope reasonable" pattern). Comments-disabled-on-video is a real, expected case (some trailers disable them) — returns `[]`, not an error.
- **`bluesky_client.py`** (new) — session-based auth (`com.atproto.server.createSession`), `app.bsky.feed.searchPosts`, `BlueskyRateLimited`/`BlueskyAuthError` checked from status/body *before* `raise_for_status()` — the OMDb/Wikidata lesson from earlier today applied proactively this time instead of discovered the hard way a third time.
- **YouTube comments cover every movie with a trailer regardless of release status** (one flow, `flows/youtube_comment_sentiment.py`) — unlike Reddit's released-vs-upcoming split, a trailer's reception is relevant whether the movie's out yet or not. Uses each trailer's own `trailer_type` as the snapshot's `stage`.
- **Bluesky mirrors Reddit's exact two-flow shape** (`bluesky_buzz_upcoming.py` eager/small, `bluesky_sentiment_backfill.py` quota-throttled/large, same training-relevant budget+box-office population as Reddit's backfill) — `db.py` gained `get_movies_needing_comment_sentiment`/`get_movies_for_bluesky_backfill` alongside the existing Reddit queries.
- `db/init/007_sentiment_snapshots_bluesky.sql` — widened `sentiment_snapshots.source`'s CHECK constraint to include `'bluesky'` (already permitted `'youtube_comments'`/`'twitter'` from the original schema).

### Verified
- `youtube_comment_sentiment.py`: 110/110 trailers processed in one run (0 remaining against the current trailer population — will keep pace automatically as `trailer_backfill.py` adds more). Real, varied output — e.g. *Weapons* (100 comments, sentiment 0.64) vs. *Highest 2 Lowest* (100 comments, sentiment -0.45) vs. *The Naked Gun* (100 comments, sentiment -0.03) — genuine signal spread, not placeholder data.
- `bluesky_buzz_upcoming.py`: all 18 upcoming movies refreshed in one run. Real spread here too — e.g. *Dune: Part Three* and *The Dog Stars* both hit sentiment 1.0 (unanimous positive lexicon hits in a small sample), *Avengers: Doomsday* at a more modest 0.14 despite the highest engagement score (0.95) of the batch.
- `bluesky_sentiment_backfill.py`: 250 movies processed (hit its per-run cap) on the first real run. 2,766 of the ~3,016 training-relevant population remain — needs continued periodic runs, same shape as every other quota-throttled backfill in this project.
- Both sources' `sentiment_snapshots` rows verified against the live DB (not just script exit codes): `source='youtube_comments'` → 110 rows (108 trailer, 2 teaser); `source='bluesky'` → 268 rows (250 post_release, 18 pre_release).

### Next steps
- Keep re-running `bluesky_sentiment_backfill.py` periodically until it reports 0 remaining (2,766 movies left as of this run)
- Once meaningful coverage exists across all three sentiment sources (Reddit still blocked on credentials, YouTube comments and Bluesky both live now), feed `avg_engagement_score`/`sentiment_score`/`volume` per source into `train_model.py` as `gbt_v3` features and evaluate whether they actually help, same as GBT v2's critic-score evaluation
- Redis caching, automated tests, real Prefect Cloud scheduling

## Frontend MVP: Landing, About, Auth, Dashboard (Built)

First real UI — `frontend/` had been an untouched Next.js scaffold all session. Built: landing page, about page, real multi-user auth (NextAuth v4, email/password via a Credentials provider), and a protected dashboard listing upcoming movies with predictions, plus a per-movie timeline page.

### Approach
- **Auth goes through the FastAPI backend, not a direct Postgres connection from Next.js** — new `POST /auth/register`/`POST /auth/login` endpoints (bcrypt hashing, new `users` table via `008_users.sql`), NextAuth's `authorize()` calls them server-side via the existing `API_INTERNAL_URL` pattern already used by the health-check page. Keeps the "only `api/`/`prefect-worker/` touch Postgres" invariant intact rather than adding a second independent DB client into the frontend.
- JWT session strategy (no sessions table needed). Route protection via `getServerSession` + redirect in each protected page, not middleware (one protected route family so far).
- Tailwind CSS added for styling (`tailwind.config.ts`, `postcss.config.mjs`, `app/globals.css`).
- `GET /movies` gained an `upcoming: bool` query param (filters `release_date > CURRENT_DATE`, orders ascending) for the dashboard's list.
- New `GET /movies/{id}/sentiment` endpoint — the sentiment data built earlier (YouTube comments, Bluesky) had zero API exposure until this pass.
- Dashboard does N+1 fetches (one `/movies?upcoming=true` call, then one `/verdicts` call per row via `Promise.all`) — deliberately not optimized into a single SQL join at ~18 rows.
- **Movie timeline page** (`/dashboard/[id]`): added after finding a real gap while testing — the dashboard originally collapsed each movie down to its single latest `gbt_v2` verdict, which made a retrain-driven prediction change (Ramayana's p50 moved between retrains as more budgets/critic scores landed elsewhere in the corpus, shifting its comps' track-record features) look like an unexplained mystery. The `verdicts` table already stores one frozen row per lifecycle stage (announcement/teaser/trailer/pre_release/post_release) per method — this was never surfaced in the UI. The detail page now shows every stage's full method breakdown (comp heuristic, gbt_v1, gbt_v2) plus sentiment data, reusing the existing `/verdicts` and `/sentiment` endpoints with zero backend changes.
- Explicitly scoped out (confirmed via direct question): a true append-only history of every recompute *within* a stage — the existing per-stage-frozen model is the intended granularity, not a live audit log of every retrain.

### Bugs hit and fixed during verification
- Frontend returned 500s on every page after adding Tailwind/NextAuth: a stale anonymous Docker volume (`/app/node_modules`) from an earlier container was shadowing the freshly-built image's `node_modules`, which didn't have the new deps. Fixed with `docker compose rm -sf frontend && docker compose up -d --force-recreate --renew-anon-volumes frontend`.
- The new `/dashboard/[id]` dynamic route 404'd even after the file existed on disk — Next.js's dev-mode file watcher missed the new directory over the Docker-on-Windows bind mount. Fixed with a plain `docker compose restart frontend` to force route re-discovery.

### Verified
- All public pages (`/`, `/about`, `/login`, `/register`) return 200; `/dashboard` and `/dashboard/[id]` correctly 307-redirect to `/login` when unauthenticated.
- Full registration → login → dashboard flow confirmed working end-to-end via the browser (register 200, credentials callback 200, session established, dashboard renders).
- Dashboard correctly shows real predictions for the 5 budgeted upcoming movies and an honest "no prediction yet" for the other 13 (budget-gap-limited, not a bug — consistent with the earlier budget-source research).

### Next steps
- ~~Movie detail/timeline page could extend to non-upcoming (released) movies too~~ — done, see "Released Movies, Posters, and Visual Stage Timeline" below
- Redis caching, automated tests, real Prefect Cloud scheduling
- Wire sentiment into the model as `gbt_v3` features (still the top substantive next step, unrelated to the frontend work)

## Wikipedia Infobox Budget Backfill (Built)

A third budget source, after Wikidata's structured `P2130` claim (only 42 matches — sparse) and a Bluesky social-consensus attempt (`budget_extraction.py`'s consensus-gated dollar-figure extraction, requiring 2+ corroborating posts within a tight bucket) that was built, tested, and **reverted** after real bad data surfaced on spot-check: common-word titles ("Border," "Run," "The Congress") pulled in wildly wrong figures from unrelated posts (a government-prison-budget post matching a "budget" search), and even on real matches, different posts disagreed by up to $85M (Dune: Part Two: $165M/$190M/$250M across different posts). Not trustworthy enough to write into the model; rolled back before any of it reached `movies.budget_usd`.

Wikipedia infobox turned out to be the better source: **correct-by-construction** (resolves the exact Wikipedia article via Wikidata's own sitelink relationship, keyed off IMDb id — no title-matching ambiguity the way Bluesky's free-text search had) and a single citation-backed field per movie, not scattered chatter needing consensus.

### Approach
- `prefect-worker/wikipedia_client.py`: `get_sitelinks()` batches IMDb-id → English Wikipedia article resolution via the same Wikidata SPARQL `VALUES` pattern `wikidata_client.py` already uses; `fetch_infobox_budget()` fetches the article's parsed HTML and extracts the infobox's Budget row. USD-only, same scope decision as the Wikidata backfill (non-`$` values skipped, not converted).
- `prefect-worker/flows/budget_wikipedia_backfill.py`: two-step per the client's shape — batch-resolve sitelinks (cheap), then fetch+parse each resolved article individually (the real rate-limited step, no batching possible for arbitrary page content).

### Two real bugs found and fixed during verification
- **Range parsing**: first live test returned `None` for every movie, including ones known to have a budget. Root cause: infobox budgets are frequently a *range* ("$190–250 million"), not a single figure — the original regex expected one number immediately followed by its unit and silently failed to match. Fixed by extending the regex to capture an optional second bound and using the range midpoint (e.g. Furious 7's "$190–250 million" → $220M).
- **Anonymous-API burst limit**: the flow repeatedly stalled after ~10 requests regardless of client-side pacing (tried 2 req/sec, then 0.5 req/sec — same wall both times). Isolated it with a direct sequential test outside the rate limiter: exactly 10 clean requests, then a real `You are making too many requests to the API` response from Wikipedia's anonymous-tier rate limit (a burst allowance, not a steady-state rate — confirmed independent of request spacing). Added `WikipediaRateLimited` (same status-check-before-`raise_for_status()` pattern as every other source this session) and retry-with-backoff (5 attempts, 30s apart) to `budget_wikipedia_backfill.py`, rather than treating it as a hard stop.

### Verified
- Full run (background, ~4 hours wall-clock, paced by the retry backoff): **1,291 Wikipedia articles resolved, 213 matched** with a real USD budget — `movies.budget_usd IS NULL` count dropped from 1,389 to 1,176.
- Real recovered budgets spot-checked directly against the actual Wikipedia infobox during debugging (Furious 7 $220M, Inception $160M, The Dark Knight $185M, Titanic $200M, Avatar $237M) — all correct.
- `SELECT budget_confidence, count(*) FROM movies GROUP BY budget_confidence` → 3,239 `estimated` / 1,176 `unknown` (up from 2,977/1,438 combined across all budget sources this session — Wikidata's 42 + Wikipedia's 213 + earlier partial runs).
- Run stopped just short of the full backlog (1,350/1,388 batches) on one last sitelink-batch rate limit — a rerun would pick up the remaining ~38.

### "Already tried" tracking (added 2026-08-12)
Re-runs on 2026-08-10 revealed a real limitation: `get_movies_missing_budget()` couldn't distinguish "already tried, no Wikipedia budget exists" from "never attempted," so re-running mostly re-scanned the same already-failed movies (two re-runs processed 971 movies combined, matched 0). Fixed with `010_wikipedia_budget_checked.sql` (`movies.wikipedia_budget_checked`, default false) plus `get_movies_missing_budget_unchecked_wikipedia()`/`mark_wikipedia_budget_checked()` in `db.py`. The flag is only set on a **definitive** answer (budget found, no Wikipedia article exists, or the article has no USD field) — a movie that hit `WikipediaRateLimited` and exhausted its retries is deliberately left unchecked, since that's still unknown, not a confirmed "no." Verified: first run under the new logic processed 350 of the 1,175 unchecked movies (0 matched, 350 newly marked checked); an immediate re-run correctly started from 825, not 1,175 — confirming re-runs now make monotonic progress instead of spinning forever.

### Next steps
- Continue re-running `budget_wikipedia_backfill.py` — it will now reliably work through the remaining ~825 unchecked movies over successive runs, throttled by Wikipedia's anonymous burst limit but no longer wasting effort on already-failed ones
- ~~Retrain `gbt_v1`/`gbt_v2` to pick up the 213 newly-budgeted movies~~ — superseded by `gbt_v3` below, which retrains on the latest data anyway
- Redis caching, automated tests, real Prefect Cloud scheduling

## GBT v3: Sentiment Features (Built)

Wires Bluesky and YouTube trailer-comment sentiment (1,376+ snapshots, previously unused) into the model — flagged as "the top substantive next step" across several recent sections.

### A coverage-skew bug found and fixed before training (not after)
Checked sentiment coverage against the model's time-based train/test split *before* building the feature, given the exact same bug already broke the first `gbt_v2` attempt. Found two mirror-image problems:
- **YouTube comments**: 0 movies before the ~2021-07-29 cutoff, 110 after. Root cause: `trailer_backfill.py`'s movie selection (`get_released_movies_missing_trailer`) is deliberately recency-first (maximizes YouTube search hit-rate for movies people actually view), which meant zero training-set coverage.
- **Bluesky (post_release)**: 1,248 before the cutoff, 0 after. The mirror problem: `get_movies_for_bluesky_backfill`'s oldest-first ordering (deliberately closes historical gaps first) meant zero test-set coverage.

Fixed with two narrowly-scoped topup queries/flows, each targeting exactly the missing side: `get_released_movies_missing_trailer_training_topup`/`trailer_backfill_training_topup.py` (pre-cutoff, feeds the existing unordered `youtube_comment_sentiment.py`) and `get_movies_for_bluesky_backfill_recent_topup`/`bluesky_sentiment_topup.py` (post-cutoff). Ran once each: YouTube training-side coverage 0 → 90, Bluesky test-side coverage 0 → 250. Both are still partial (especially YouTube, quota-bound at ~90/day against ~2,300 training movies with no trailer yet) but enough for a real first evaluation.

### Approach
- `db.get_movies_for_training()` gained two more joins: `bluesky` (`stage='post_release'`, unique per movie via the existing `(movie_id, stage, source)` constraint — plain `LEFT JOIN` is safe) and `youtube_comments` (no stage filter, since a movie could in principle have a snapshot for either `teaser` or `trailer` — used `LEFT JOIN LATERAL ... LIMIT 1` instead of a plain join to guard against row duplication, since that combination isn't covered by the unique constraint).
- 6 new additive, `NaN`-native feature columns (same pattern as v2's critic scores): `bluesky_sentiment_score`, `log_bluesky_volume`, `log_bluesky_avg_engagement`, `youtube_sentiment_score`, `log_youtube_volume`, `log_youtube_avg_engagement`.
- `MODEL_METHOD = "gbt_v3"`; comparison loop extended to 4-way (`comp_heuristic_v1`/`gbt_v1`/`gbt_v2`/`gbt_v3`).

### Verified
- **4-way accuracy on the same 599-movie holdout**: `gbt_v3` 50.1% exact / 89.0% within-one, vs. `gbt_v2` 48.4%/90.8%, `gbt_v1` 42.0%/86.6%, `comp_heuristic_v1` 36.4%/87.5%. A genuinely mixed result, reported honestly: exact-match improved, within-one-bucket slightly regressed — not an unambiguous win.
- **Feature importance shows real, uneven signal**: `log_bluesky_avg_engagement` (433 gain) and `log_bluesky_volume` (347) rank #11/#13 of 33 features — ahead of several genre and seasonality features, genuine contribution. `bluesky_sentiment_score` (108) is weaker but present. All three YouTube features rank near the bottom (42/27/27) — consistent with its much thinner coverage (90 training examples vs. Bluesky's 1,248+), not evidence the signal itself is useless.
- Wrote 3,239 fresh `gbt_v3` verdict rows, coexisting with v1/v2/heuristic in `verdicts` via the existing `(movie_id, stage, method)` schema — no changes needed there.

### Next steps
- ~~Keep running `trailer_backfill_training_topup.py`~~ — done across several sessions (0 → 183 → 272+ training-side movies as of the hyperparameter-tuning pass below); Bluesky's post-cutoff (test-side) coverage backlog is now fully exhausted too
- Redis caching, automated tests, real Prefect Cloud scheduling

## GBT v3 Hyperparameter Tuning (Built)

LightGBM's parameters (`num_leaves=31`, `learning_rate=0.05`, `min_data_in_leaf=10`) had been carried forward unchanged since `gbt_v1` and never actually tuned. Added a real small grid search (27 combinations: `num_leaves ∈ {15,31,63}` × `learning_rate ∈ {0.03,0.05,0.1}` × `min_data_in_leaf ∈ {5,10,20}` — deliberately small given only ~2,400 training rows, to avoid overfitting the validation set's own noise) plus early stopping to pick `num_boost_round` per candidate.

### Approach
- **Proper 3-way time-ordered split** (train/val/test), replacing the previous train/test split — tuning only ever sees train+val; the test set stays untouched until the one final evaluation, preserving the held-out discipline every accuracy comparison this session has relied on. `VAL_FRACTION = 0.15` carved out of the pre-test 80%, so the split is ~65/15/20.
- **Tuned on the p50 (median) objective only**, not all three quantile models independently — tuning triples the search cost for the same essential tree-complexity/learning-rate decision, and the winning hyperparameters are applied to p25/p50/p75 alike for the final fit.
- **Selected by validation exact-bucket accuracy**, not raw quantile loss — loss and bucket accuracy don't always agree, and bucket accuracy is the metric actually reported and compared against the other methods.
- Final model refit on train+val combined (all pre-test data) at the winning hyperparameters/iteration count, then evaluated once on the still-untouched test set — unchanged methodology from every prior GBT pass.

### Verified
- **Best hyperparameters found**: `num_leaves=15, learning_rate=0.03, min_data_in_leaf=5, num_boost_round=313` — simpler trees, slower learning, more rounds than the old defaults, which tracks with a small-dataset regime (less overfitting headroom).
- **Clean improvement from tuning itself**, same 599-movie test set: 49.6% exact / 90.0% within-one, up from the untuned `gbt_v3`'s 48.9%/89.5% — both metrics improved, not a tradeoff. Now ahead of `gbt_v2` (48.3%) on exact-match, though still slightly behind on within-one (90.8%).
- **Sentiment features still contribute real signal** under the new hyperparameters: `log_bluesky_avg_engagement`/`log_bluesky_volume` remain solidly mid-pack (~13th/14th of 33 features), and YouTube's `log_youtube_avg_engagement` grew further (86→141 gain) as training-side coverage kept building across sessions. None of the 6 sentiment features show zero importance.

### Next steps
- ~~Redis caching~~ — done below
- Automated tests, real Prefect Cloud scheduling

## Redis Caching + Live-Serving gbt_v2→v3 Fix (Built)

Redis had been provisioned since the original scaffold and pinged in `/health`, but never actually cached anything — explicitly deferred earlier as premature. Revisited now for one concrete reason: `GET /movies/{id}/predict` runs live LightGBM inference on every request, a genuinely different cost profile from the rest of the API.

### A real bug found while wiring it up, not caused by it
While adding caching to `/predict`, found `api/app/gbt_predictor.py`'s `METHOD` had been hardcoded to `"gbt_v2"` this entire time — live serving never picked up `gbt_v3`'s sentiment features or tuned hyperparameters, even though `/verdicts` (batch-precomputed by `train_model.py`) had been showing `gbt_v3` correctly. The two endpoints had been silently inconsistent. Caching a known-stale model's predictions would have been counterproductive, so fixed this first: added `api/app/queries.py:get_sentiment_for_prediction()` (mirrors `prefect-worker/db.py:get_movies_for_training()`'s sentiment joins exactly, same `LATERAL` guard for `youtube_comments` since that source/movie combination isn't covered by the unique constraint), extended `gbt_predictor.py`'s feature-building with the same 6 sentiment columns `train_model.py` uses, and bumped `METHOD` to `"gbt_v3"`. `_metadata["feature_columns"]` already listed the new columns from the existing `feature_metadata_gbt_v3.json`, so no other changes were needed there.

### Approach
- `api/app/cache.py` (new): `cache_get`/`cache_set`, lazy Redis client singleton, both wrapped in try/except so any Redis failure degrades to a cache miss rather than an error - Redis being down should make the API slower, never broken.
- Cached exactly 3 endpoints (the ones with real, non-trivial cost): `predict` (TTL 3600s - predictions only change on a manual retrain), `comps` (TTL 900s), `list_movies` (TTL 300s, most likely to reflect freshly-landed backfill data). Left `get_movie`/`get_verdicts`/`get_sentiment` uncached - cheap indexed reads where caching would add complexity for negligible gain.
- TTL-based expiry only, no explicit invalidation - the flows that change this data run in a separate `prefect-worker` container; real invalidation would need cross-service coupling not justified at this traffic level.
- Same "check cache, else compute and store" shape already established in this file by `_get_or_fetch_critic_scores`, just Redis instead of a Postgres upsert as the cache layer.

### Verified
- All 3 endpoints: second call returns byte-identical data to the first (confirmed via diff) and is meaningfully faster (`predict`: 0.92s → 0.09s, a ~10x speedup from skipping live model inference).
- `redis-cli keys '*'` shows the expected 3 key patterns (`predict:4892`, `comps:4892:embedding:5`, `movies:None:None:None:False:5:0`) with sane TTLs.
- Stopped the redis container entirely and re-hit `/predict` and `/movies` - both returned clean `200`s (degraded to direct computation), confirming Redis is genuinely optional, not a hard dependency.
- `/movies/4892/predict` now correctly reports `"method":"gbt_v3"`, matching `/verdicts`.

### Next steps
- ~~Automated tests~~ — done below
- Real Prefect Cloud scheduling

## Automated Tests v1 (Built)

Zero automated tests existed anywhere in the project until now — every change across 7 data sources, 3 model versions, live serving, and caching had been verified by hand. Scoped deliberately to unit tests for pure/deterministic logic only, no test database or network calls in the suite itself — real integration tests need test-DB fixture infrastructure that's a genuinely bigger lift, and starting there would have meant shipping nothing this pass.

### Approach
- pytest, one suite per service (`prefect-worker/tests/`, `api/tests/`), matching the existing "these two services share no code" architecture.
- `prefect-worker/tests/`: `RateLimiter.wait()`'s spacing enforcement, `stage_scan.py`'s `_bucket`/`_percentile`/`detect_stage` (all 5 lifecycle branches), `sentiment_scoring.py`'s `summarize_items` (including the "no lexicon hits → `None`, not `0.0`" distinction), `budget_extraction.py`'s paragraph-splitting and corroboration-margin logic, `wikipedia_client.py`'s `_parse_money` (including the range-midpoint parsing that was a real bug earlier this session).
- `api/tests/`: `gbt_predictor.py`'s `_bucket`/`_season_features`, the no-budget→`None` path, and a fixture-based test of the full feature-vector construction using fake `Booster` stubs (record the row they're called with, return a fixed value) rather than real trained model files — verifies `NaN` fallback for missing critic/sentiment data, `mpaa_rating` category-index lookup, genre one-hot construction, and the quantile-crossing sort guard (deliberately fed "crossed" fake quantile predictions to confirm the guard actually reorders them). `cache.py`'s get/set round-trip tested against the real redis service (already available for free in the same docker network), plus the graceful-degradation guarantee against a deliberately-unreachable Redis instance.
- Added `pytest==8.3.3` to both `requirements.txt` files.

### Verified
- `docker compose run --rm --no-deps prefect-worker python -m pytest -v` → **39 passed**.
- `docker compose run --rm --no-deps api python -m pytest -v` (with `redis` up) → **12 passed**.
- Sanity-checked the suite isn't vacuously passing: deliberately broke a `_bucket` boundary assertion, confirmed it actually fails with a clear diff, then reverted and confirmed green again.

### Next steps
- DB-touching logic (`db.py`/`queries.py`) and full API endpoint tests need real test-database fixture infrastructure - not built this pass
- External-API client behavior (rate-limit detection, response parsing) currently only verified by hand against the real APIs
- ~~Real Prefect Cloud scheduling~~ — still manual, see next section's open item

## Released Movies, Posters, and Visual Stage Timeline (Built)

Direct feedback after shipping the upcoming-movies dashboard: the UI (plain tables, a stacked list of stage cards) didn't visually communicate the actual product thesis — a movie's prediction evolving stage by stage, and how it compares to reality once released. Also closed the gap flagged in the Frontend MVP's own "Next steps": the detail/timeline page had never been linked from anywhere for already-released movies.

### Approach
- **`GET /movies` gained `released_only: bool`** (mirrors the existing `upcoming` param's shape exactly, `release_date <= CURRENT_DATE`) — additive, not a replacement, so no existing callers changed behavior.
- **New `/dashboard/released` page**: paginated (25/page), searchable, server-rendered list showing predicted vs. actual bucket per movie with a ✓/✗ correctness indicator — the same N+1 `/verdicts`-per-row pattern the upcoming dashboard already established, now taking the *last* `gbt_v3` verdict (the post-release one) instead of the current-stage one.
- **Movie posters via TMDb's public image CDN** (`https://image.tmdb.org/t/p/{size}{poster_path}`) — no new API key or auth needed for the images themselves, and `poster_path` was already present in the exact `/movie/{id}` response `tmdb_backfill.py` has always fetched, just never captured. Stored as the raw path fragment (not a full URL) so the frontend picks whatever size fits each context (`w92` list thumbnails, `w342` detail-page image). One-time `poster_backfill.py` flow backfilled the ~4,400 pre-existing movies (TMDb's 20 req/sec limit made this a ~4-minute job, not a quota-throttled multi-day one like the YouTube/Wikipedia sources) — 4,412 of 4,415 matched, 3 transient read timeouts.
- **New shared `StageTimeline` component** (`frontend/app/components/StageTimeline.tsx`): a horizontal row of 5 connected dot nodes (announcement → teaser → trailer → pre_release → post_release), plain Tailwind/flexbox rather than a charting dependency (`frontend/package.json` had zero chart libraries, consistent with the project's "no new dependency unless truly needed" pattern). Deliberately scoped to `gbt_v3` only, not a repeat of the existing multi-method comparison — the existing full per-stage/per-method breakdown stays on the detail page below the timeline as supplementary detail, not removed. Reached stages are colored by bucket; unreached stages render dimmed, so an upcoming movie still shows genuine visual progress. Released movies show the post-release node's actual bucket/ROI plus total worldwide box office; any movie with a `gbt_v3` prediction shows that prediction's value regardless of release status.

### Bugs found and fixed along the way
- `dashboard/page.tsx` had `method === "gbt_v2"` hardcoded in its verdict filter — silently stale since `gbt_v3` shipped, the same bug class as the `gbt_predictor.py` `METHOD` staleness bug from the Redis caching pass. Also found `METHOD_LABELS` was missing a `gbt_v3` entry entirely.
- `StageTimeline`'s summary line originally used a single `isReleased ? boxOfficeLine : expectedOutcomeLine` mutually-exclusive ternary. A movie that had technically crossed its release date but had no box-office data ingested yet (a real, common state — box office lags release) rendered *nothing*, because neither branch's condition was fully satisfied. Fixed by decoupling the two conditions: the box-office line and the predicted/expected-outcome line now render independently, so a `gbt_v3` prediction always shows when one exists.
- Mid-verification, the whole Docker Desktop engine had gone down between sessions (`open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.` on every `docker compose run`) — all 6 recurring maintenance flows appeared to "succeed" (exit code 0) while actually erroring before ever reaching the containers. Caught by reading the actual output rather than trusting the exit code, restarted Docker Desktop, brought the stack back up (`docker compose up -d`, postgres/redis data volume intact), and reran cleanly.

### Verified
- `SELECT count(*) FROM movies WHERE poster_path IS NOT NULL` → 4,412 of 4,415.
- `GET /movies?limit=N` and `GET /movies/{id}` both return real `poster_path` strings.
- Released movie detail page (`/dashboard/134`, "Cop Out"): poster renders, timeline's post-release node shows "actual: solid (1.85x)" alongside the `gbt_v3` prediction, and "Total worldwide box office: $55.6M" renders correctly.
- Upcoming movie with a single reached stage (`/dashboard/4905`): timeline dims the unreached Announcement/Teaser/Trailer nodes, fills Pre-release with the `gbt_v3` bucket/value, and the "Expected outcome as of the latest stage" line renders.
- Both list pages (`/dashboard`, `/dashboard/released`) show poster thumbnails without breaking existing pagination/search; `/dashboard/released?page=2` correctly renders "Page 2 of 177" (confirmed via raw HTML — a plain-text `grep` had initially missed this due to React's hydration comment nodes splitting the text, not an actual rendering bug).
- Stage-to-stage delta annotations are implemented and wired (computed client-side from consecutive `gbt_v3` verdicts) but not yet exercised by real data — no upcoming movie currently has more than one `gbt_v3`-staged verdict yet, since `gbt_v3` is comparatively new.

### Next steps
- Real Prefect Cloud scheduling for the recurring maintenance flows (`refresh_recent`, `omdb_trickle`, `stage_scan`, `youtube_comment_sentiment`, `bluesky_buzz_upcoming`, `trailer_backfill`) and `train_model.py` — still entirely manual `docker compose run`, and the Docker-Desktop-down incident above is exactly the kind of silent failure real scheduling/alerting would catch
- DB-touching logic and full API endpoint tests (unchanged gap from Automated Tests v1)
- Delta annotations will get real exercise once more upcoming movies accumulate multiple `gbt_v3`-staged verdicts over time
