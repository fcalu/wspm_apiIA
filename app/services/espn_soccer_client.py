import requests
from typing import Optional, Dict, Any

from app.config import settings
from app.utils.cache import get_from_cache, set_in_cache
from app.core.logging import logger


BASE_URL_SITE = settings.espn_soccer_site_base_url
BASE_URL_CORE = settings.espn_soccer_core_base_url


def fetch_soccer_scoreboard_data(use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Obtiene el scoreboard de la liga de soccer configurada (ej. Premier League eng.1).
    """
    cache_key = "soccer:scoreboard:current"

    if use_cache:
        cached = get_from_cache(cache_key, ttl_seconds=settings.espn_cache_ttl_seconds)
        if cached is not None:
            logger.info(f"[ESPN][SOC] Cache HIT para {cache_key}")
            return cached

    url = f"{BASE_URL_SITE}/scoreboard"
    logger.info(f"[ESPN][SOC] Fetch scoreboard desde URL: {url}")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if use_cache:
            set_in_cache(cache_key, data)
            logger.info(f"[ESPN][SOC] Cache SET para {cache_key}")

        return data
    except requests.RequestException as e:
        logger.error(f"[ESPN][SOC] Error al obtener el scoreboard: {e}")
        return None


def fetch_soccer_game_odds(event_id: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Obtiene odds de un juego de soccer por event_id.
    """
    cache_key = f"soccer:odds:{event_id}"

    if use_cache:
        cached = get_from_cache(cache_key, ttl_seconds=settings.espn_cache_ttl_seconds)
        if cached is not None:
            logger.info(f"[ESPN][SOC] Cache HIT para {cache_key}")
            return cached

    url = f"{BASE_URL_CORE}/events/{event_id}/competitions/{event_id}/odds"
    logger.info(f"[ESPN][SOC] Fetch odds desde URL: {url}")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if use_cache:
            set_in_cache(cache_key, data)
            logger.info(f"[ESPN][SOC] Cache SET para {cache_key}")

        return data
    except requests.RequestException as e:
        logger.error(f"[ESPN][SOC] Error al obtener las cuotas: {e}")
        return None
