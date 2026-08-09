"""Thin httpx wrapper around Reddit's OAuth2 "script" app flow.

v1 scope: search a fixed set of subreddits for posts mentioning a movie
title (+ year, to disambiguate common titles like "Wonder Woman" or "It"),
and return enough per-post data for the caller to compute mention volume,
average engagement (Reddit's upvote-based post score), and an optional
lightweight lexicon sentiment score. No comment-tree fetching, no NLP model -
that's deliberately out of scope for v1 (see reddit_sentiment_backfill.py's
docstring / planning doc).
"""

import time

import httpx

from rate_limiter import RateLimiter

REDDIT_AUTH_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_API_BASE = "https://oauth.reddit.com"

DEFAULT_SUBREDDITS = ["movies", "boxoffice", "trailers"]

# Reddit's documented OAuth limit for script-type apps is ~60 requests/minute
# (published as 100 QPM per OAuth client in the newer API terms, but 60/min
# is the conservative figure widely used for script apps and script apps
# have a history of being throttled harder than confidential web apps) -
# stay comfortably under 1 req/sec rather than chase the documented ceiling.
_limiter = RateLimiter(max_per_second=0.9)


class RedditRateLimited(Exception):
    """Reddit's OAuth API is rate-limiting us (429, or its own
    "you are doing that too much" body) - stop the run rather than burn
    through the remaining queue against the same wall.
    """


class RedditAuthError(Exception):
    """Credentials missing/invalid - distinct from a transient rate limit so
    callers can fail fast instead of retrying pointlessly.
    """


class _TokenCache:
    """Module-level so every call in a run shares one token instead of
    re-authenticating per request.
    """

    def __init__(self):
        self.token: str | None = None
        self.expires_at: float = 0.0


_token_cache = _TokenCache()


def get_access_token(client_id: str, client_secret: str, user_agent: str) -> str:
    """Client-credentials grant (Reddit "script" app, app-only/read-only
    access - no end-user login needed, which is all a server-side search
    job needs). Cached in-process until ~60s before expiry.
    """
    if _token_cache.token and time.monotonic() < _token_cache.expires_at:
        return _token_cache.token

    resp = httpx.post(
        REDDIT_AUTH_URL,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        headers={"User-Agent": user_agent},
        timeout=15.0,
    )
    if resp.status_code == 429:
        raise RedditRateLimited(resp.text)
    if resp.status_code in (401, 403):
        raise RedditAuthError(f"Reddit rejected credentials ({resp.status_code}): {resp.text}")
    resp.raise_for_status()
    data = resp.json()

    token = data.get("access_token")
    if not token:
        raise RedditAuthError(f"Reddit token response missing access_token: {data}")

    _token_cache.token = token
    _token_cache.expires_at = time.monotonic() + data.get("expires_in", 3600) - 60
    return token


def search_movie_mentions(
    title: str,
    year: int | None,
    client_id: str,
    client_secret: str,
    user_agent: str,
    subreddits: list[str] | None = None,
    limit: int = 100,
) -> list[dict]:
    """Searches `subreddits` (default DEFAULT_SUBREDDITS) for posts matching
    `title` (quoted, plus year if given, to cut down on false matches for
    generic titles). Returns a list of
    {id, title, score, num_comments, created_utc, permalink, selftext}
    dicts, newest-relevance-ranked, capped at `limit` (Reddit's own per-call
    max is 100).

    Raises RedditRateLimited / RedditAuthError; callers should stop the run
    on either rather than continue burning requests.
    """
    subs = subreddits or DEFAULT_SUBREDDITS
    token = get_access_token(client_id, client_secret, user_agent)

    query = f'"{title}"' + (f" {year}" if year else "")
    multi_sr = "+".join(subs)

    _limiter.wait()
    resp = httpx.get(
        f"{REDDIT_API_BASE}/r/{multi_sr}/search",
        params={
            "q": query,
            "restrict_sr": "on",
            "sort": "relevance",
            "limit": min(limit, 100),
        },
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": user_agent,
        },
        timeout=15.0,
    )
    # Reddit signals throttling with 429 (and occasionally 403 for a bad/
    # revoked token, which we don't want to misclassify as "no results") -
    # check both before raise_for_status() would otherwise mask them as a
    # generic HTTP error.
    if resp.status_code == 429:
        raise RedditRateLimited(resp.text)
    if resp.status_code == 403:
        raise RedditAuthError(f"Reddit returned 403 (token invalid/expired?): {resp.text}")
    resp.raise_for_status()
    data = resp.json()

    posts = []
    for child in data.get("data", {}).get("children", []):
        p = child.get("data", {})
        posts.append(
            {
                "id": p.get("id"),
                "title": p.get("title", ""),
                "selftext": p.get("selftext", ""),
                "score": p.get("score", 0),
                "num_comments": p.get("num_comments", 0),
                "created_utc": p.get("created_utc"),
                "permalink": p.get("permalink"),
                "subreddit": p.get("subreddit"),
            }
        )
    return posts
