# app/services/cache.py

import time
from functools import wraps
from typing import Any, Callable, Dict, Tuple

# Caché en memoria muy simple
_cache: Dict[
    Tuple[str, Tuple[Any, ...], Tuple[Tuple[str, Any], ...]],
    Tuple[float, Any]
] = {}


def ttl_cache_json(ttl_seconds: int = 300):
    """
    Decorador de caché con TTL para funciones que devuelven JSON (dict).

    Uso:
        @ttl_cache_json(ttl_seconds=900)
        def fetch_xxx(...):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (
                func.__module__ + "." + func.__name__,
                args,
                tuple(sorted(kwargs.items())),
            )
            now = time.time()

            # Si está en cache y no ha expirado → devolver
            if key in _cache:
                expires_at, value = _cache[key]
                if now < expires_at:
                    return value

            # Si no, llamar a la función y cachear
            result = func(*args, **kwargs)
            _cache[key] = (now + ttl_seconds, result)
            return result

        return wrapper

    return decorator
