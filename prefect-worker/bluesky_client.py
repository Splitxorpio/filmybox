"""Thin httpx wrapper around Bluesky's AT Protocol.

Unlike Reddit, Bluesky access is self-service - a free account plus an
"app password" generated instantly from account settings, no approval
queue. But it does require real auth: confirmed empirically that
public.api.bsky.app (the read-only AppView some blog posts describe as
"no auth needed") blocks non-browser traffic at the CDN layer (raw 403,
not a real API response), while the actual PDS endpoint bsky.social
returns a clean {"error":"AuthMissing"} for search without a session
token. So: real session-based auth against bsky.social, same as any other
source here.

v1 scope mirrors reddit_client.py: search for posts mentioning a movie
title (+ year), return enough per-post data for sentiment_scoring.py's
summarize_items() (id/text/engagement=like count). No thread/reply
traversal, no NLP model.
"""

import httpx

from rate_limiter import RateLimiter

BSKY_BASE_URL = "https://bsky.social"

# Bluesky's documented rate limits are generous (thousands/hour for
# authenticated requests) - no need to chase the exact ceiling, just stay
# comfortably conservative.
_limiter = RateLimiter(max_per_second=2)


class BlueskyRateLimited(Exception):
    """Bluesky is rate-limiting us (429) - stop the run rather than burn
    through the remaining queue against the same wall.
    """


class BlueskyAuthError(Exception):
    """Credentials missing/invalid - distinct from a transient rate limit so
    callers can fail fast instead of retrying pointlessly.
    """


class _SessionCache:
    """Module-level so every call in a run shares one session instead of
    re-authenticating per request.
    """

    def __init__(self):
        self.access_jwt: str | None = None


_session_cache = _SessionCache()


def _authenticate(handle: str, app_password: str) -> str:
    if _session_cache.access_jwt:
        return _session_cache.access_jwt

    resp = httpx.post(
        f"{BSKY_BASE_URL}/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": app_password},
        timeout=15.0,
    )
    if resp.status_code == 429:
        raise BlueskyRateLimited(resp.text)
    if resp.status_code in (400, 401):
        raise BlueskyAuthError(f"Bluesky rejected credentials ({resp.status_code}): {resp.text}")
    resp.raise_for_status()
    data = resp.json()

    token = data.get("accessJwt")
    if not token:
        raise BlueskyAuthError(f"Bluesky session response missing accessJwt: {data}")

    _session_cache.access_jwt = token
    return token


def search_movie_mentions(
    title: str,
    year: int | None,
    handle: str,
    app_password: str,
    limit: int = 100,
) -> list[dict]:
    """Searches Bluesky posts matching `title` (+ year, to disambiguate
    generic titles). Returns [{"id", "text", "engagement"}, ...],
    engagement = like count. Raises BlueskyRateLimited / BlueskyAuthError;
    callers should stop the run on either rather than continue.
    """
    token = _authenticate(handle, app_password)

    query = f'"{title}" trailer' + (f" {year}" if year else "")

    _limiter.wait()
    resp = httpx.get(
        f"{BSKY_BASE_URL}/xrpc/app.bsky.feed.searchPosts",
        params={"q": query, "limit": min(limit, 100)},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15.0,
    )
    # Bluesky signals throttling with 429, and an expired/invalid session
    # token with 401 - check both before raise_for_status() would otherwise
    # mask them as a generic HTTP error.
    if resp.status_code == 429:
        raise BlueskyRateLimited(resp.text)
    if resp.status_code == 401:
        _session_cache.access_jwt = None
        raise BlueskyAuthError(f"Bluesky returned 401 (token invalid/expired?): {resp.text}")
    resp.raise_for_status()
    data = resp.json()

    items = []
    for post in data.get("posts", []):
        record = post.get("record", {})
        items.append(
            {
                "id": post.get("uri", ""),
                "text": record.get("text", ""),
                "engagement": post.get("likeCount", 0),
            }
        )
    return items
