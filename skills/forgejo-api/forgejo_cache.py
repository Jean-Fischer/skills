"""
File-based cache for the Forgejo API skill with TTL and ETag support.

Cache file: ~/.cache/forgejo-api.json

Protocol
--------
- Each cache entry stores: {value, timestamp, ttl}
- On get_cached:
    * If entry exists and (now - timestamp) < ttl: return value (no network call)
    * If expired: call fetch_fn(etag) with the stored ETag
        - On NOT_MODIFIED: bump timestamp, return cached value
        - On fresh (data, etag): store new value, ttl, and etag; return data
        - On exception: return stale value as fallback
- On cache miss: call fetch_fn(None) and store result with given ttl
"""

import json
import os
import time
from typing import Any, Callable, Optional

CACHE_FILE = os.path.expanduser("~/.cache/forgejo-api.json")
DEFAULT_TTL = int(os.environ.get("PI_CACHE_TTL", 300))


def _load_cache() -> dict:
    """Load the cache from disk, returning an empty dict if file doesn't exist or is invalid."""
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError, OSError:
        return {}


def _save_cache(cache: dict) -> None:
    """Save the cache to disk, creating the directory if necessary."""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except OSError:
        pass  # Best effort.


def get_cached(
    key: str,
    fetch_fn: Callable[[Optional[str]], Any],
    ttl: int = DEFAULT_TTL,
    etag_key: Optional[str] = None,
) -> Any:
    """
    Return value from cache or, when stale/missing, call *fetch_fn*.

    *fetch_fn(etag)* receives the cached ETag (or *None* on first fetch).
    It should send ``If-None-Match`` when an ETag is provided.

    On a ``304 Not Modified``, *fetch_fn* **must** return the sentinel
    ``forgejo_cache.NOT_MODIFIED``.  On a fresh ``200`` it should return
    ``(parsed_data, etag_string)``.  A bare value without an ETag is also
    accepted (no ETag will be stored for that key).

    The *ttl* argument is the time-to-live in seconds for this cache entry.
    If omitted, the value of the ``PI_CACHE_TTL`` environment variable is used
    (default 300 seconds).
    """
    cache = _load_cache()
    now = time.time()
    etag_key = etag_key or f"{key}::etag"

    entry = cache.get(key)
    if entry:
        # Entry exists: check freshness using the TTL stored with the entry.
        stored_ttl = entry.get("ttl", DEFAULT_TTL)
        age = now - entry.get("timestamp", 0)
        if age < stored_ttl:
            # Fresh: return cached value without network call.
            return entry["value"]

        # Stale: try conditional GET with stored ETag.
        stored_etag = cache.get(etag_key)
        try:
            fresh = fetch_fn(stored_etag)
        except Exception:
            # Network error: return stale value as fallback.
            return entry["value"]

        if fresh is NOT_MODIFIED:
            # Not modified: refresh timestamp and return cached value.
            entry["timestamp"] = now
            cache[key] = entry
            _save_cache(cache)
            return entry["value"]

        # Fresh data received: update cache.
        _store_fresh(cache, key, fresh, now, ttl, etag_key)
        return _unwrap_value(fresh)

    # No cache entry: fetch fresh data.
    try:
        fresh = fetch_fn(None)
    except Exception:
        raise

    if fresh is NOT_MODIFIED:
        # Should not happen without a cached entry, but guard anyway.
        return None

    _store_fresh(cache, key, fresh, now, ttl, etag_key)
    return _unwrap_value(fresh)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _store_fresh(
    cache: dict,
    key: str,
    fresh: Any,
    timestamp: float,
    ttl: int,
    etag_key: str,
) -> None:
    """Store a fresh response and extract its ETag, if any."""
    value, etag = _split_etag(fresh)
    cache[key] = {"value": value, "timestamp": timestamp, "ttl": ttl}
    if etag is not None:
        cache[etag_key] = etag
    elif etag_key in cache:
        del cache[etag_key]
    _save_cache(cache)


def _unwrap_value(fresh: Any) -> Any:
    """Return the data portion of a (data, etag) tuple, or the bare value."""
    if isinstance(fresh, tuple) and len(fresh) == 2:
        return fresh[0]
    return fresh


def _split_etag(fresh: Any) -> tuple:
    """
    Return ``(value, etag_or_None)``.

    Understands:
    - ``(data, etag_string)`` tuples
    - objects with a ``.headers`` dict-like (e.g. ``requests.Response``)
    - bare values (no ETag)
    """
    if isinstance(fresh, tuple) and len(fresh) == 2:
        value, etag = fresh
        if isinstance(etag, str) and etag.strip():
            return value, etag
        return value, None
    if hasattr(fresh, "headers"):
        etag = (
            fresh.headers.get("ETag")
            or fresh.headers.get("Etag")
            or fresh.headers.get("etag")
        )
        if etag:
            return fresh, etag
    return fresh, None


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def clear_cache() -> None:
    """Remove the cache file."""
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)


# ---------------------------------------------------------------------------
# Sentinel for 304 Not Modified
# ---------------------------------------------------------------------------


class _NotModified:
    """Singleton sentinel — *fetch_fn* returns this on a 304 response."""

    _instance = None

    def __new__(cls) -> "_NotModified":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NOT_MODIFIED"

    def __bool__(self) -> bool:
        return False


NOT_MODIFIED = _NotModified()
