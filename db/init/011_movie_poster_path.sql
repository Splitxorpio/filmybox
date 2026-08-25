-- TMDb's poster_path is already present in the /movie/{id} response
-- tmdb_backfill.py has always fetched - just never captured. Raw path
-- fragment (e.g. "/abc123.jpg"), not a full URL, so the frontend can pick
-- whatever image size fits each context via TMDb's public image CDN.
ALTER TABLE movies ADD COLUMN poster_path TEXT;
