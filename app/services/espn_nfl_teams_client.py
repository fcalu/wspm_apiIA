# app/services/espn_nfl_teams_client.py

import logging
from typing import List, Dict, Any, Optional

import requests

from app.config import settings

logger = logging.getLogger("wspm")

BASE_URL_SITE = settings.espn_nfl_site_base_url


def fetch_nfl_teams_raw() -> Optional[Dict[str, Any]]:
    """
    Llama al endpoint de ESPN que lista los equipos NFL:

      https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams
    """
    url = f"{BASE_URL_SITE}/teams"
    logger.info(f"[ESPN][NFL][Teams] Fetch lista de equipos desde: {url}")

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"[ESPN][NFL][Teams] Error al obtener lista de equipos: {e}")
        return None


def parse_nfl_teams(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parsea el JSON de ESPN a una lista simplificada de equipos:

    [
      {
        "team_id": 6,
        "abbr": "DAL",
        "name": "Dallas Cowboys",
        "location": "Dallas",
        "short_name": "Cowboys",
        "logo": "https://....png"
      },
      ...
    ]
    """
    teams_out: List[Dict[str, Any]] = []

    sports = raw.get("sports") or []
    for s in sports:
        leagues = s.get("leagues") or []
        for l in leagues:
            teams = l.get("teams") or []
            for t in teams:
                team_obj = t.get("team") or t

                tid = team_obj.get("id")
                abbr = team_obj.get("abbreviation")
                name = team_obj.get("displayName") or team_obj.get("name")
                location = team_obj.get("location")
                short_name = team_obj.get("shortDisplayName")

                # Logo principal (si existe)
                logos = team_obj.get("logos") or []
                logo_url = None
                if logos and isinstance(logos, list):
                    # Tomamos el primero como logo principal
                    logo_url = logos[0].get("href")

                if not tid or not abbr or not name:
                    continue

                try:
                    team_id = int(tid)
                except (TypeError, ValueError):
                    continue

                teams_out.append(
                    {
                        "team_id": team_id,
                        "abbr": abbr,
                        "name": name,
                        "location": location,
                        "short_name": short_name,
                        "logo": logo_url,
                    }
                )

    return teams_out


def fetch_nfl_teams_simplified() -> List[Dict[str, Any]]:
    """
    Función principal para rutas:
    - Llama a ESPN
    - Parsea el resultado al formato simplificado
    """
    raw = fetch_nfl_teams_raw()
    if not raw:
        return []

    return parse_nfl_teams(raw)
