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
