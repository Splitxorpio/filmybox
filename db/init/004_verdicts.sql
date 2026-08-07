-- Per-stage flop/hit/blockbuster verdicts, computed by
-- prefect-worker/flows/stage_scan.py using a comp-based heuristic (median
-- ROI multiple among a movie's top embedding comps - see planning doc's
-- "Staged Verdict System" section for why this precedes real GBT models).
CREATE TABLE verdicts (
    id                    SERIAL PRIMARY KEY,
    movie_id              INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    stage                 TEXT NOT NULL CHECK (stage IN (
                              'announcement', 'teaser', 'trailer', 'pre_release', 'post_release'
                          )),
    computed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    comp_count            INTEGER NOT NULL,
    roi_multiple_p25      NUMERIC,
    roi_multiple_p50      NUMERIC,
    roi_multiple_p75      NUMERIC,
    verdict_bucket        TEXT CHECK (verdict_bucket IN ('flop', 'solid', 'hit', 'blockbuster')),
    comp_movie_ids        INTEGER[] NOT NULL,
    -- Only populated once the movie's own outcome is known (post_release) -
    -- lets the heuristic's accuracy be measured against reality directly.
    actual_roi_multiple   NUMERIC,
    actual_bucket         TEXT CHECK (actual_bucket IN ('flop', 'solid', 'hit', 'blockbuster')),
    method                TEXT NOT NULL DEFAULT 'comp_heuristic_v1',
    UNIQUE (movie_id, stage)
);

CREATE INDEX idx_verdicts_movie_id ON verdicts(movie_id);
