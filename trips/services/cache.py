"""Small in-process cache for external provider responses."""

import hashlib
import json
from typing import Any

from django.conf import settings
from django.core.cache import cache


def route_cache_key(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> str:
    return "route:{:.6f},{:.6f}:{:.6f},{:.6f}".format(
        origin[0], origin[1], destination[0], destination[1]
    )


def poi_cache_key(route_coordinates: list[list[float]]) -> str:
    payload = json.dumps(route_coordinates, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"poi:{digest}"


def get_cached(key: str) -> Any | None:
    return cache.get(key)


def set_cached(key: str, value: Any) -> None:
    cache.set(key, value, timeout=settings.EXTERNAL_CACHE_TIMEOUT)
