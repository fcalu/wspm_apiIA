import requests
from typing import Any, Dict, Optional, List

from app.config import settings
from app.utils.cache import get_from_cache, set_in_cache
from app.core.logging import logger

BASE_URL_SITE = settings.espn_nba_site_base_url


def fetch_nba_team_roster_by_abbr(team_abbr: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    Intenta obtener un roster simplificado NBA por abreviatura.
    ESPN NBA puede variar en el endpoint exacto dependiendo de la temporada.
    Esta versión:
    - consulta teams desde site api
    - busca el team_id por abbreviation
    - intenta pedir roster con un patrón común

    Si falla, regresa None sin romper el API.
    """
    team_abbr = team_abbr.upper().strip()
    cache_key = f"nba:roster:{team_abbr}"

    if use_cache:
        cached = get_from_cache(cache_key, ttl_seconds=settings.espn_cache_ttl_seconds)
        if cached is not None:
            return cached

    try:
        # 1) catálogo de equipos
        teams_url = f"{BASE_URL_SITE}/teams"
        logger.info(f"[ESPN][NBA] Fetch teams catalog: {teams_url}")

        teams_resp = requests.get(teams_url, timeout=settings.espn_timeout_seconds)
        teams_resp.raise_for_status()
        teams_data = teams_resp.json()

        sports = teams_data.get("sports", [])
        leagues = sports[0].get("leagues", []) if sports else []
        teams = leagues[0].get("teams", []) if leagues else []

        team_id = None
        team_name = None

        for t in teams:
            team_obj = (t or {}).get("team", {}) or {}
            if team_obj.get("abbreviation") == team_abbr:
                team_id = team_obj.get("id")
                team_name = team_obj.get("displayName")
                break

        if not team_id:
            logger.warning(f"[ESPN][NBA] No se encontró team_id para {team_abbr}")
            return None

        # 2) intentar roster
        # Patrón típico site api:
        roster_url = f"{BASE_URL_SITE}/teams/{team_id}/roster"
        logger.info(f"[ESPN][NBA] Fetch roster: {roster_url}")

        roster_resp = requests.get(roster_url, timeout=settings.espn_timeout_seconds)
        roster_resp.raise_for_status()
        roster_data = roster_resp.json()

        players_out: List[Dict[str, Any]] = []

        # ESPN suele traer "athletes" en grupos por posición
        athletes_groups = roster_data.get("athletes", [])
        for grp in athletes_groups:
            items = grp.get("items", [])
            for p in items:
                players_out.append(
                    {
                        "athlete_id": str(p.get("id")) if p.get("id") else None,
                        "name": p.get("fullName"),
                        "position": (p.get("position") or {}).get("abbreviation"),
                        "jersey": p.get("jersey"),
                        "depth": None,
                        "team_abbr": team_abbr,
                    }
                )

        result = {
            "team_abbr": team_abbr,
            "team_name": team_name or team_abbr,
            "players": [p for p in players_out if p.get("athlete_id")],
        }

        if use_cache:
            set_in_cache(cache_key, result)

        return result

    except Exception as e:
        logger.error(f"[ESPN][NBA] Error roster {team_abbr}: {e}")
        return None
