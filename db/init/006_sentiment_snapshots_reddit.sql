-- Reddit sentiment ingestion (see reddit_client.py / flows/reddit_*.py) writes
-- one row per movie/stage/source and re-upserts it on every re-run, rather than
-- appending a true time series - a movie's "pre_release" buzz snapshot gets
-- refreshed in place as it approaches release, and a new "post_release" row
-- is written once box office data exists. Needs a uniqueness constraint to
-- upsert against, which the original scaffolding never added.
ALTER TABLE sentiment_snapshots
    ADD CONSTRAINT sentiment_snapshots_movie_stage_source_key UNIQUE (movie_id, stage, source);

-- volume (post count) and sentiment_score (lexicon-based, optional) already
-- existed, but the primary v1 signal - Reddit's upvote-based engagement per
-- post - had no column to land in.
ALTER TABLE sentiment_snapshots
    ADD COLUMN avg_engagement_score NUMERIC;
