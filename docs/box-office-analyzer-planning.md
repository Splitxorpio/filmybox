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
- Real GBT model training, now with the comp-heuristic's 36.1%/83.3% numbers as the baseline to beat
- Trailer engagement / critic scores feeding into comp weighting, so the confidence interval actually narrows by stage (the explicitly-deferred limitation from this pass)
- Reddit sentiment pull, Redis caching, automated tests, real Prefect Cloud scheduling
