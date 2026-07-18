"""Small Redis caching helpers (JSON values, TTL-based).

Uses the shared connection from realtime/redis_client.py. Every helper
swallows Redis errors: a cache failure must degrade to "no caching",
never break the feature it fronts.
"""

import json

from realtime.redis_client import get_redis


def cache_get(key: str):
    """Return the cached JSON value, or None on miss or any Redis failure."""
    try:
        raw = get_redis().get(key)
    except Exception:
        return None
    return json.loads(raw) if raw is not None else None


def cache_set(key: str, value, ttl_seconds: int) -> None:
    """Cache a JSON-serializable value with a TTL. Failures are ignored."""
    try:
        get_redis().set(key, json.dumps(value), ex=ttl_seconds)
    except Exception:
        pass


def cache_delete(key: str) -> None:
    """Invalidate a cache key. Failures are ignored."""
    try:
        get_redis().delete(key)
    except Exception:
        pass
