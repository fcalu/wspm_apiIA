import requests
from typing import Optional, Dict, Any

from app.config import settings
from app.utils.cache import get_from_cache, set_in_cache
from app.core.logging import logger

BASE_URL_WEB = settings.espn_nfl_web_base_url


def fetch_player_gamelog(
    athlete_id: str,
    season: int,
    season_type: int = 2,
    use_cache: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Obtiene el gamelog de un jugador NFL desde ESPN (no oficial).

    - athlete_id: ID del jugador en ESPN (ej. 3043078 para CeeDee Lamb).
    - season: temporada (ej. 2024).
    - season_type: 1=Pre, 2=Regular, 3=Post.

    Endpoint base:
    site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/{athlete_id}/gamelog
    """

    cache_key = f"nfl:gamelog:{athlete_id}:{season}:{season_type}"

    if use_cache:
        cached = get_from_cache(cache_key, ttl_seconds=settings.espn_cache_ttl_seconds)
        if cached is not None:
            logger.info(f"[ESPN][NFL][Gamelog] Cache HIT para {cache_key}")
            return cached

    url = f"{BASE_URL_WEB}/athletes/{athlete_id}/gamelog?season={season}&seasonType={season_type}"
    logger.info(f"[ESPN][NFL][Gamelog] Fetch desde URL: {url}")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if use_cache:
            set_in_cache(cache_key, data)
            logger.info(f"[ESPN][NFL][Gamelog] Cache SET para {cache_key}")

        return data
    except requests.RequestException as e:
        logger.error(f"[ESPN][NFL][Gamelog] Error al obtener gamelog: {e}")
        return None
