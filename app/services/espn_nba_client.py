import re
import requests
from typing import Optional, Dict, Any

from app.config import settings
from app.utils.cache import get_from_cache, set_in_cache
from app.core.logging import logger

BASE_URL_SITE = settings.espn_nba_site_base_url
BASE_URL_CORE = settings.espn_nba_core_base_url


def _clean_date(date: str) -> str:
    if not date:
        return ""
    return date.strip()


def fetch_nba_scoreboard(date: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Scoreboard NBA por fecha ESPN.
    date debe venir como YYYYMMDD.
    """
    date = _clean_date(date)

    if not re.fullmatch(r"\d{8}", date):
        logger.error(f"[ESPN][NBA] Fecha inválida para scoreboard: {repr(date)}")
        return None

    cache_key = f"nba:scoreboard:{date}"

    if use_cache:
        cached = get_from_cache(cache_key, ttl_seconds=settings.espn_cache_ttl_seconds)
        if cached is not None:
            logger.info(f"[ESPN][NBA] Cache HIT para {cache_key}")
            return cached

    url = f"{BASE_URL_SITE}/scoreboard"
    params = {"dates": date}

    logger.info(f"[ESPN][NBA] Fetch scoreboard desde URL: {url} params={params}")

    try:
        response = requests.get(url, params=params, timeout=10)
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
    Odds de un juego NBA por event_id.
    Nota: ESPN suele modelar competitions con otro id interno,
    pero este endpoint funciona como primer paso.
    """
    event_id = str(event_id).strip()
    if not event_id:
        return None

    cache_key = f"nba:odds:{event_id}"

    if use_cache:
        cached = get_from_cache(cache_key, ttl_seconds=settings.espn_cache_ttl_seconds)
        if cached is not None:
            logger.info(f"[ESPN][NBA] Cache HIT para {cache_key}")
            return cached

    # Mantengo tu patrón actual
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
