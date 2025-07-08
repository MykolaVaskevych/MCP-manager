"""Response caching for MCP requests."""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CacheEntry:
    """Cache entry with TTL support."""

    def __init__(self, data: Any, ttl_seconds: int = 300):
        self.data = data
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(seconds=ttl_seconds)

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return datetime.now() > self.expires_at

    def time_to_live(self) -> float:
        """Get remaining TTL in seconds."""
        remaining = self.expires_at - datetime.now()
        return max(0.0, remaining.total_seconds())


class ResponseCache:
    """Cache for MCP responses with TTL and size limits."""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        self.cache: Dict[str, CacheEntry] = {}
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the cache cleanup task."""
        # Don't start cleanup task automatically to avoid task context issues
        # Cache cleanup will be handled on-demand during operations
        pass

    async def stop(self) -> None:
        """Stop the cache cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    def generate_cache_key(self, server_id: str, method: str, params: Any) -> str:
        """Generate cache key for request."""
        # Create a deterministic key from server_id, method, and params
        key_data = {"server_id": server_id, "method": method, "params": params}

        # Convert to JSON and hash for consistent key
        json_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(json_str.encode()).hexdigest()

    async def get(self, cache_key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        async with self._lock:
            entry = self.cache.get(cache_key)

            if entry is None:
                return None

            if entry.is_expired():
                del self.cache[cache_key]
                return None

            logger.debug(f"Cache hit for key: {cache_key}")
            return entry.data

    async def set(self, cache_key: str, data: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL."""
        if ttl is None:
            ttl = self.default_ttl

        async with self._lock:
            # Periodically clean up expired entries (every 100 operations)
            if len(self.cache) % 100 == 0:
                await self._cleanup_expired_unlocked()

            # Evict oldest entries if at max size
            if len(self.cache) >= self.max_size:
                await self._evict_oldest()

            self.cache[cache_key] = CacheEntry(data, ttl)
            logger.debug(f"Cache set for key: {cache_key}, TTL: {ttl}s")

    async def delete(self, cache_key: str) -> None:
        """Delete specific cache entry."""
        async with self._lock:
            self.cache.pop(cache_key, None)

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            self.cache.clear()
            logger.info("Cache cleared")

    async def _evict_oldest(self) -> None:
        """Evict oldest cache entries to make room."""
        # Sort by creation time and remove oldest
        sorted_entries = sorted(self.cache.items(), key=lambda x: x[1].created_at)

        # Remove oldest 10% of entries
        evict_count = max(1, len(sorted_entries) // 10)
        for key, _ in sorted_entries[:evict_count]:
            del self.cache[key]

        logger.debug(f"Evicted {evict_count} cache entries")

    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired entries."""
        while True:
            try:
                await asyncio.sleep(60)  # Cleanup every minute
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cache cleanup: {e}")

    async def _cleanup_expired(self) -> None:
        """Remove expired cache entries."""
        async with self._lock:
            await self._cleanup_expired_unlocked()

    async def _cleanup_expired_unlocked(self) -> None:
        """Remove expired cache entries (assumes lock is already held)."""
        expired_keys = [key for key, entry in self.cache.items() if entry.is_expired()]

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_entries = len(self.cache)
        expired_entries = sum(1 for entry in self.cache.values() if entry.is_expired())

        return {
            "total_entries": total_entries,
            "expired_entries": expired_entries,
            "active_entries": total_entries - expired_entries,
            "max_size": self.max_size,
            "fill_percentage": (total_entries / self.max_size) * 100,
        }
