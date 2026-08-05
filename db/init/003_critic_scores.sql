-- Critic scores from OMDb (wraps IMDb rating, Rotten Tomatoes, Metacritic).
-- Populated two ways: on-demand in the API (api/app/routers/movies.py) when a
-- movie without a cached row is viewed, and a background trickle
-- (prefect-worker/flows/omdb_trickle.py) that opportunistically backfills
-- the rest of the corpus under OMDb's free-tier 1,000 req/day cap.
CREATE TABLE critic_scores (
    movie_id             INTEGER PRIMARY KEY REFERENCES movies(id) ON DELETE CASCADE,
    imdb_rating          NUMERIC,
    imdb_votes           INTEGER,
    rotten_tomatoes_pct  INTEGER,
    metacritic_score     INTEGER,
    -- Supplementary audience-sentiment signal (not a critic score) from
    -- TMDb, refreshed only for recent/upcoming movies (see
    -- prefect-worker/flows/refresh_recent.py) since RT/Metacritic coverage
    -- gaps on older titles are inherent to OMDb's own data, not fixable here.
    tmdb_vote_average    NUMERIC,
    tmdb_vote_count      INTEGER,
    source               TEXT NOT NULL DEFAULT 'omdb',
    fetched_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
