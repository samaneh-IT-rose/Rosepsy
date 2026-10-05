from redis import Redis


def hit(redis: Redis, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Fixed-window counter. Returns (allowed, retry_after_seconds)."""
    count = redis.incr(key)
    if count == 1:
        redis.expire(key, window_seconds)
    ttl = redis.ttl(key)
    return count <= limit, max(ttl, 0)
