import redis as redis_lib

from app import cache


def test_cache_round_trip():
    cache.cache_set("test:roundtrip", {"a": 1, "b": [1, 2, 3]}, ttl_seconds=10)
    assert cache.cache_get("test:roundtrip") == {"a": 1, "b": [1, 2, 3]}


def test_cache_get_missing_key_returns_none():
    assert cache.cache_get("test:definitely-not-set-xyz-123") is None


def test_cache_set_applies_ttl():
    cache.cache_set("test:ttl", {"a": 1}, ttl_seconds=100)
    ttl = cache._get_client().ttl("test:ttl")
    assert 0 < ttl <= 100


def test_cache_list_value_round_trips():
    cache.cache_set("test:list", [{"id": 1}, {"id": 2}], ttl_seconds=10)
    assert cache.cache_get("test:list") == [{"id": 1}, {"id": 2}]


def test_cache_degrades_gracefully_when_redis_unreachable(monkeypatch):
    """Redis being down should make cache_get/cache_set no-ops, never raise -
    the graceful-degradation guarantee stated in cache.py's own docstring.
    """
    broken_client = redis_lib.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.5, decode_responses=True)
    monkeypatch.setattr(cache, "_client", broken_client)

    assert cache.cache_get("any-key") is None
    cache.cache_set("any-key", {"a": 1}, ttl_seconds=10)  # must not raise
