import requests
from typing import Optional, Dict, Any

from app.config import settings
from app.utils.cache import get_from_cache, set_in_cache
from app.core.logging import logger

# OJO: aquí usamos los nuevos nombres de config.py
BASE_URL_SITE = settings.espn_nfl_site_base_url
BASE_URL_CORE = settings.espn_nfl_core_base_url


def fetch_scoreboard_data(week: int, season_type: int, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Obtiene el scoreboard NFL desde ESPN (no oficial).
    Aplica un cache simple en memoria para evitar llamadas repetidas.
    """
    cache_key = f"nfl:scoreboard:{season_type}:{week}"

    if use_cache:
        cached = get_from_cache(cache_key, ttl_seconds=settings.espn_cache_ttl_seconds)
        if cached is not None:
            logger.info(f"[ESPN][NFL] Cache HIT para {cache_key}")
            return cached

    url = f"{BASE_URL_SITE}/scoreboard?seasontype={season_type}&week={week}"
    logger.info(f"[ESPN][NFL] Fetch scoreboard desde URL: {url}")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if use_cache:
            set_in_cache(cache_key, data)
            logger.info(f"[ESPN][NFL] Cache SET para {cache_key}")

        return data
    except requests.RequestException as e:
        logger.error(f"[ESPN][NFL] Error al obtener el scoreboard: {e}")
        return None


def fetch_game_odds(event_id: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Obtiene odds de un evento NFL por event_id.
    También usa cache simple en memoria.
    """
    cache_key = f"nfl:odds:{event_id}"

    if use_cache:
        cached = get_from_cache(cache_key, ttl_seconds=settings.espn_cache_ttl_seconds)
        if cached is not None:
            logger.info(f"[ESPN][NFL] Cache HIT para {cache_key}")
            return cached

    # 💡 CORRECCIÓN APLICADA: La URL se simplifica quitando /competitions/{event_id}
    url = f"{BASE_URL_CORE}/events/{event_id}/odds"
    logger.info(f"[ESPN][NFL] Fetch odds desde URL: {url}")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if use_cache:
            set_in_cache(cache_key, data)
            logger.info(f"[ESPN][NFL] Cache SET para {cache_key}")

        return data
    except requests.RequestException as e:
        logger.error(f"[ESPN][NFL] Error al obtener las cuotas: {e}")
        return None