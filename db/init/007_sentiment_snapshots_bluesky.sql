-- Adds 'bluesky' as a valid sentiment_snapshots.source, alongside the
-- existing reddit/twitter/youtube_comments values.
ALTER TABLE sentiment_snapshots DROP CONSTRAINT sentiment_snapshots_source_check;
ALTER TABLE sentiment_snapshots ADD CONSTRAINT sentiment_snapshots_source_check
    CHECK (source = ANY (ARRAY['reddit', 'twitter', 'youtube_comments', 'bluesky']));
