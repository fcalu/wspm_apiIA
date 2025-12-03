import time
from typing import Any, Dict, Tuple

# Cache muy simple en memoria (clave -> (timestamp, valor))
_cache: Dict[str, Tuple[float, Any]] = {}


def get_from_cache(key: str, ttl_seconds: int = 60):
    now = time.time()
    if key in _cache:
        ts, value = _cache[key]
        if now - ts <= ttl_seconds:
            return value
        else:
            # Expirado
            del _cache[key]
    return None


def set_in_cache(key: str, value: Any):
    _cache[key] = (time.time(), value)
