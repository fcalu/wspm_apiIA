# app/services/espn_nba_client.py

from typing import Optional, Dict, Any

import requests

from app.config import settings
from app.utils.cache import get_from_cache, set_in_cache
from app.core.logging import logger

# Base URLs desde settings
BASE_URL_SITE = settings.espn_nba_site_base_url
BASE_URL_CORE = settings.espn_nba_core_base_url


# ---------------------------------------------------------
# SCOREBOARD
# ---------------------------------------------------------
def fetch_nba_scoreboard(date: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Scoreboard NBA para una fecha específica YYYYMMDD.
    """
    date = (date or "").strip()
    if not date:
        logger.error("[ESPN][NBA] Fecha vacía al solicitar scoreboard.")
        return None

    cache_key = f"nba:scoreboard:{date}"

    if use_cache:
        cached = get_from_cache(cache_key, ttl_seconds=settings.espn_cache_ttl_seconds)
        if cached is not None:
            logger.info(f"[ESPN][NBA] Cache HIT para {cache_key}")
            return cached

    url = f"{BASE_URL_SITE}/scoreboard"
    params = {"dates": date}

    logger.info(f"[ESPN][NBA] Fetch scoreboard: {url} params={params}")

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if use_cache:
            set_in_cache(cache_key, data)
            logger.info(f"[ESPN][NBA] Cache SET para {cache_key}")

        return data
    except requests.RequestException as e:
        logger.error(f"[ESPN][NBA] Error al obtener scoreboard: {e}")
        return None


# ---------------------------------------------------------
# ODDS
# ---------------------------------------------------------
def fetch_nba_game_odds(event_id: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Odds de un partido NBA por event_id.
    """
    if not event_id:
        return None

    cache_key = f"nba:odds:{event_id}"

    if use_cache:
        cached = get_from_cache(cache_key, ttl_seconds=settings.espn_cache_ttl_seconds)
        if cached is not None:
            logger.info(f"[ESPN][NBA] Cache HIT para {cache_key}")
            return cached

    # Mismo patrón que NFL: events/{event_id}/competitions/{event_id}/odds
    url = f"{BASE_URL_CORE}/events/{event_id}/competitions/{event_id}/odds"

    logger.info(f"[ESPN][NBA] Fetch odds: {url}")

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if use_cache:
            set_in_cache(cache_key, data)
            logger.info(f"[ESPN][NBA] Cache SET para {cache_key}")

        return data
    except requests.RequestException as e:
        logger.error(f"[ESPN][NBA] Error al obtener odds para {event_id}: {e}")
        return None


# ---------------------------------------------------------
# TEAM + ROSTER
# ---------------------------------------------------------
def fetch_nba_team_with_roster(team_abbr: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Obtiene la info del equipo NBA (por abreviatura) incluyendo el roster.

    Usamos el endpoint:
      {BASE_URL_SITE}/teams/{team_abbr}?enable=roster,projection,statistics

    La respuesta típica trae algo como:
      {
        "team": {
          "displayName": "...",
          "abbreviation": "LAL",
          "roster": {
             "entries": [
                { "player": { "id": "...", "fullName": "...", ... } },
                ...
             ]
          }
        }
      }
    """
    if not team_abbr:
        return None

    team_abbr = team_abbr.upper()
    cache_key = f"nba:team:{team_abbr}:roster"

    if use_cache:
        cached = get_from_cache(cache_key, ttl_seconds=settings.espn_cache_ttl_seconds)
        if cached is not None:
            logger.info(f"[ESPN][NBA] Cache HIT para {cache_key}")
            return cached

    url = f"{BASE_URL_SITE}/teams/{team_abbr}"
    params = {"enable": "roster,projection,statistics"}

    logger.info(f"[ESPN][NBA] Fetch team+roster: {url} params={params}")

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if use_cache:
            set_in_cache(cache_key, data)
            logger.info(f"[ESPN][NBA] Cache SET para {cache_key}")

        return data
    except requests.RequestException as e:
        logger.error(f"[ESPN][NBA] Error al obtener team+roster para {team_abbr}: {e}")
        return None
