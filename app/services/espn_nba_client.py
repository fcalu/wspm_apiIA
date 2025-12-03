import requests
from typing import Optional, Dict, Any

from app.config import settings
from app.utils.cache import get_from_cache, set_in_cache
from app.core.logging import logger


BASE_URL_SITE = settings.espn_nba_site_base_url
BASE_URL_CORE = settings.espn_nba_core_base_url


def fetch_nba_scoreboard_data(use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Obtiene el scoreboard NBA desde ESPN (no oficial).
    Algunos scoreboards de NBA no usan 'week' como NFL, sino fecha / día.
    Para simplificar, usamos el scoreboard 'hoy'.
    """
    cache_key = "nba:scoreboard:today"

    if use_cache:
        cached = get_from_cache(cache_key, ttl_seconds=settings.espn_cache_ttl_seconds)
        if cached is not None:
            logger.info(f"[ESPN][NBA] Cache HIT para {cache_key}")
            return cached

    url = f"{BASE_URL_SITE}/scoreboard"
    logger.info(f"[ESPN][NBA] Fetch scoreboard desde URL: {url}")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if use_cache:
            set_in_cache(cache_key, data)
            logger.info(f"[ESPN][NBA] Cache SET para {cache_key}")

        return data
    except requests.RequestException as e:
        logger.error(f"[ESPN][NBA] Error al obtener el scoreboard: {e}")
        return None


def fetch_nba_game_odds(event_id: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Obtiene odds de un juego NBA por event_id.
    """
    cache_key = f"nba:odds:{event_id}"

    if use_cache:
        cached = get_from_cache(cache_key, ttl_seconds=settings.espn_cache_ttl_seconds)
        if cached is not None:
            logger.info(f"[ESPN][NBA] Cache HIT para {cache_key}")
            return cached

    url = f"{BASE_URL_CORE}/events/{event_id}/competitions/{event_id}/odds"
    logger.info(f"[ESPN][NBA] Fetch odds desde URL: {url}")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if use_cache:
            set_in_cache(cache_key, data)
            logger.info(f"[ESPN][NBA] Cache SET para {cache_key}")

        return data
    except requests.RequestException as e:
        logger.error(f"[ESPN][NBA] Error al obtener las cuotas: {e}")
        return None
