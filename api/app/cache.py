"""Thin Redis caching helper for the three api/ endpoints with real,
non-trivial compute cost (live GBT inference, pgvector k-NN, paginated
list+count) - see planning doc's Redis Caching section for why those three
specifically and not the cheaper single/few-row-read endpoints.

TTL-based expiry, no explicit invalidation - see planning doc for why (the
flows that change this data run in a separate prefect-worker container;
proper invalidation would need real cross-service coupling not justified at
this traffic level). Every call degrades gracefully to a cache miss on any
Redis error - Redis being unreachable should make the API slower, never
broken, same principle already applied to OMDb failures in
_get_or_fetch_critic_scores.
"""

import json

import redis

from app.config import settings

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def cache_get(key: str) -> dict | list | None:
    try:
        raw = _get_client().get(key)
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def cache_set(key: str, value: dict | list, ttl_seconds: int) -> None:
    try:
        _get_client().setex(key, ttl_seconds, json.dumps(value, default=str))
    except Exception:
        pass
