-- FilmyBox historical data schema.
-- Runs automatically on first container start against an empty postgres_data volume
-- (docker-entrypoint-initdb.d executes .sql files alphabetically). To re-run after
-- editing this file on an existing volume: `docker compose down -v` then `up` again,
-- since initdb scripts only fire once per fresh volume.

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- studios
-- ---------------------------------------------------------------------------
CREATE TABLE studios (
    id                  SERIAL PRIMARY KEY,
    name                TEXT NOT NULL UNIQUE,
    tier                TEXT CHECK (tier IN ('major', 'mini_major', 'indie')),
    historical_avg_roi  NUMERIC
);

-- ---------------------------------------------------------------------------
-- franchises
-- Referenced by movies.franchise_id so sequels/reboots can be linked and
-- comps can optionally include/exclude same-franchise entries.
-- ---------------------------------------------------------------------------
CREATE TABLE franchises (
    id      SERIAL PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE
);

-- ---------------------------------------------------------------------------
-- movies
-- ---------------------------------------------------------------------------
CREATE TABLE movies (
    id                  SERIAL PRIMARY KEY,
    tmdb_id             INTEGER UNIQUE,
    imdb_id             TEXT UNIQUE,
    title               TEXT NOT NULL,
    release_date        DATE,
    genres              TEXT[] NOT NULL DEFAULT '{}',
    runtime_minutes     INTEGER,
    mpaa_rating         TEXT,
    original_language   TEXT,
    budget_usd          NUMERIC,
    -- Budget figures are frequently self-reported/unreliable (per planning doc,
    -- ~20-30% of movies). Flag confidence explicitly rather than silently imputing.
    budget_confidence   TEXT NOT NULL DEFAULT 'unknown'
                        CHECK (budget_confidence IN ('confirmed', 'estimated', 'unknown')),
    franchise_id        INTEGER REFERENCES franchises(id),
    studio_id           INTEGER REFERENCES studios(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_movies_release_date ON movies(release_date);
CREATE INDEX idx_movies_franchise_id ON movies(franchise_id);
CREATE INDEX idx_movies_studio_id ON movies(studio_id);
CREATE INDEX idx_movies_genres ON movies USING GIN (genres);

-- ---------------------------------------------------------------------------
-- people
-- Person disambiguation happens via tmdb_id/imdb_id, never by matching on
-- name string (e.g. multiple people named "Michael Bay").
-- ---------------------------------------------------------------------------
CREATE TABLE people (
    id          SERIAL PRIMARY KEY,
    tmdb_id     INTEGER UNIQUE,
    imdb_id     TEXT UNIQUE,
    name        TEXT NOT NULL,
    birth_year  INTEGER
);

-- ---------------------------------------------------------------------------
-- movie_credits
-- ---------------------------------------------------------------------------
CREATE TABLE movie_credits (
    id              SERIAL PRIMARY KEY,
    movie_id        INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    person_id       INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    role_type       TEXT NOT NULL CHECK (role_type IN ('actor', 'director', 'producer', 'writer')),
    billing_order   INTEGER,
    character_name  TEXT,
    UNIQUE (movie_id, person_id, role_type)
);

CREATE INDEX idx_movie_credits_movie_id ON movie_credits(movie_id);
CREATE INDEX idx_movie_credits_person_id ON movie_credits(person_id);

-- ---------------------------------------------------------------------------
-- box_office_totals
-- One row per movie: opening weekend + lifetime totals. Split from the
-- weekly series (below) because these are single point-in-time facts, not
-- a time series — conflating the two in one table made updates ambiguous.
-- ---------------------------------------------------------------------------
CREATE TABLE box_office_totals (
    movie_id                    INTEGER PRIMARY KEY REFERENCES movies(id) ON DELETE CASCADE,
    opening_weekend_domestic    NUMERIC,
    opening_weekend_international NUMERIC,
    total_domestic              NUMERIC,
    total_international         NUMERIC,
    total_worldwide             NUMERIC,
    currency                    TEXT NOT NULL DEFAULT 'USD',
    source                      TEXT,
    last_updated                TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- box_office_weekly
-- The actual time series (weekend 1, 2, 3, ...) needed to compute "legs"/
-- drop-off rate, which the planning doc calls out as often more valuable
-- to predict than the opening weekend number itself.
-- ---------------------------------------------------------------------------
CREATE TABLE box_office_weekly (
    id              SERIAL PRIMARY KEY,
    movie_id        INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    weekend_number  INTEGER NOT NULL CHECK (weekend_number >= 1),
    weekend_gross   NUMERIC,
    theater_count   INTEGER,
    currency        TEXT NOT NULL DEFAULT 'USD',
    source          TEXT,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (movie_id, weekend_number)
);

CREATE INDEX idx_box_office_weekly_movie_id ON box_office_weekly(movie_id);

-- ---------------------------------------------------------------------------
-- trailers
-- ---------------------------------------------------------------------------
CREATE TABLE trailers (
    id              SERIAL PRIMARY KEY,
    movie_id        INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    platform        TEXT NOT NULL DEFAULT 'youtube',
    external_id     TEXT,
    url             TEXT,
    trailer_type    TEXT NOT NULL CHECK (trailer_type IN ('teaser', 'trailer', 'clip', 'other')),
    sequence_number INTEGER NOT NULL DEFAULT 1,
    publish_date    DATE
);

CREATE INDEX idx_trailers_movie_id ON trailers(movie_id);

-- ---------------------------------------------------------------------------
-- trailer_metrics
-- Time series pulled repeatedly per trailer. Note (per planning doc): for
-- historical backfill, only *current* view counts on old trailers are
-- generally available, not their original velocity curve — velocity
-- features are reliable going forward, not retroactively.
-- ---------------------------------------------------------------------------
CREATE TABLE trailer_metrics (
    id              SERIAL PRIMARY KEY,
    trailer_id      INTEGER NOT NULL REFERENCES trailers(id) ON DELETE CASCADE,
    snapshot_date   TIMESTAMPTZ NOT NULL,
    view_count      BIGINT,
    like_count      BIGINT,
    comment_count   BIGINT,
    UNIQUE (trailer_id, snapshot_date)
);

CREATE INDEX idx_trailer_metrics_trailer_id ON trailer_metrics(trailer_id);

-- ---------------------------------------------------------------------------
-- sentiment_snapshots
-- Stored as a time series per stage, not one blended number, since the
-- product thesis depends on the verdict evolving stage by stage.
-- ---------------------------------------------------------------------------
CREATE TABLE sentiment_snapshots (
    id              SERIAL PRIMARY KEY,
    movie_id        INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    stage           TEXT NOT NULL CHECK (stage IN (
                        'announcement', 'casting_news', 'teaser',
                        'trailer', 'pre_release', 'post_release'
                    )),
    snapshot_date   TIMESTAMPTZ NOT NULL,
    source          TEXT NOT NULL CHECK (source IN ('reddit', 'twitter', 'youtube_comments')),
    sentiment_score NUMERIC CHECK (sentiment_score BETWEEN -1 AND 1),
    volume          INTEGER,
    raw_sample_ids  TEXT[]
);

CREATE INDEX idx_sentiment_snapshots_movie_id ON sentiment_snapshots(movie_id);
CREATE INDEX idx_sentiment_snapshots_stage ON sentiment_snapshots(movie_id, stage);

-- ---------------------------------------------------------------------------
-- movie_embeddings
-- Backs the comp-similarity search (k-NN over genre/cast/director/budget/
-- timing) described in the Modeling Approach section. Empty until the
-- embedding pipeline exists; dimension (384) matches a sentence-transformers
-- MiniLM-class model as a placeholder default — change it to match whichever
-- embedding model is actually used, since vector columns are fixed-width.
-- ---------------------------------------------------------------------------
CREATE TABLE movie_embeddings (
    movie_id        INTEGER PRIMARY KEY REFERENCES movies(id) ON DELETE CASCADE,
    embedding       VECTOR(384) NOT NULL,
    model_version   TEXT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_movie_embeddings_ivfflat ON movie_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
