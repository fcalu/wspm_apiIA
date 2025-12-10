import re
import requests
from typing import Any, Dict

from app.config import settings
from app.core.logging import logger

BASE_URL_WEB = settings.espn_nba_web_base_url


def fetch_nba_player_gamelog(
    athlete_id: str,
    season: int,
    season_type: int = 2,
) -> Dict[str, Any]:
    """
    Gamelog crudo ESPN para un jugador NBA.
    """
    athlete_id = str(athlete_id).strip()

    if not re.fullmatch(r"\d+", athlete_id):
        raise ValueError(f"athlete_id inválido: {athlete_id}")

    url = f"{BASE_URL_WEB}/athletes/{athlete_id}/gamelog"

    params = {
        "season": season,
        "seasonType": season_type,
    }

    logger.info(f"[ESPN][NBA] Fetch gamelog: {url} params={params}")

    resp = requests.get(
        url,
        params=params,
        timeout=getattr(settings, "espn_timeout_seconds", 10),
    )
    resp.raise_for_status()
    return resp.json()
