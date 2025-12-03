# app/services/espn_nfl_roster_client.py

import logging
from typing import Dict, Any, List, Optional

import requests

from app.config import settings

logger = logging.getLogger("wspm")

# Usamos el SITE base de NFL
BASE_URL_SITE = settings.espn_nfl_site_base_url

# Cache en memoria para mapear abreviatura -> team_id
TEAM_ID_CACHE: Dict[str, int] = {}


def _load_team_ids_from_espn() -> None:
    """
    Llama a:
      https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams

    y construye un mapa abbr -> team_id en TEAM_ID_CACHE.
    """
    global TEAM_ID_CACHE

    url = f"{BASE_URL_SITE}/teams"
    logger.info(f"[ESPN][NFL][Teams] Fetch lista de equipos desde: {url}")

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"[ESPN][NFL][Teams] Error al obtener lista de equipos: {e}")
        return

    sports = data.get("sports") or []
    for s in sports:
        leagues = s.get("leagues") or []
        for l in leagues:
            teams = l.get("teams") or []
            for t in teams:
                team_obj = t.get("team") or t
                abbr = team_obj.get("abbreviation")
                tid = team_obj.get("id")
                if abbr and tid:
                    try:
                        tid_int = int(tid)
                        TEAM_ID_CACHE[abbr.upper()] = tid_int
                    except (TypeError, ValueError):
                        continue

    logger.info(f"[ESPN][NFL][Teams] Cargados {len(TEAM_ID_CACHE)} equipos en cache.")


def get_team_id_from_abbr(team_abbr: str) -> Optional[int]:
    """
    Devuelve el team_id de ESPN para una abreviatura NFL (ej: DAL, KC, PHI).
    Si la cache está vacía, primero llama a _load_team_ids_from_espn().
    """
    if not team_abbr:
        return None

    abbr_up = team_abbr.upper()

    if abbr_up not in TEAM_ID_CACHE:
        _load_team_ids_from_espn()

    return TEAM_ID_CACHE.get(abbr_up)


def fetch_team_roster(team_id: int) -> Optional[Dict[str, Any]]:
    """
    Llama al endpoint de roster de equipo (SITE):

      https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{TEAM_ID}/roster
    """
    url = f"{BASE_URL_SITE}/teams/{team_id}/roster"
    logger.info(f"[ESPN][NFL][Roster] Fetch desde URL: {url}")

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data
    except Exception as e:
        logger.error(f"[ESPN][NFL][Roster] Error al obtener roster para team_id={team_id}: {e}")
        return None


def _parse_athletes_list(athletes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parsea una lista de atletas (ya "aplanada") en formato simplificado.
    Cada elemento de `athletes` aquí debe ser un objeto jugador.
    """
    players_out: List[Dict[str, Any]] = []

    for item in athletes:
        # Algunos endpoints usan directamente el atleta;
        # otros usan { "athlete": { ... }, "position": {...}, ... }
        athlete = item.get("athlete") or item.get("player") or item
        athlete_id = athlete.get("id")
        if not athlete_id:
            continue

        full_name = (
            athlete.get("fullName")
            or athlete.get("displayName")
            or athlete.get("shortName")
            or ""
        )

        # Posición: primero del "item", luego del propio athlete
        pos_obj = item.get("position") or athlete.get("position") or {}
        position = pos_obj.get("abbreviation") or pos_obj.get("displayName")

        jersey = athlete.get("jersey") or item.get("jersey")

        depth = item.get("depthChartOrder") or item.get("starter")
        try:
            if isinstance(depth, str):
                depth_int = int(depth)
            else:
                depth_int = int(depth) if depth is not None else None
        except (TypeError, ValueError):
            depth_int = None

        players_out.append(
            {
                "athlete_id": str(athlete_id),
                "name": full_name,
                "position": position,
                "jersey": jersey,
                "depth": depth_int,
            }
        )

    return players_out


def parse_team_roster(raw: Dict[str, Any], team_abbr: str) -> Dict[str, Any]:
    """
    Devuelve una estructura simplificada:

    {
      "team_abbr": "DAL",
      "team_name": "Dallas Cowboys",
      "players": [ {...}, ... ]
    }
    """
    team_name = team_abbr.upper()

    # En este endpoint específico, el team_name no viene tan explícito,
    # así que usamos simplemente la abreviatura como fallback.
    # Si en algún futuro ESPN agrega "team": {...}, aquí lo leeríamos:
    team_obj = raw.get("team") or {}
    if team_obj:
        team_name = team_obj.get("displayName") or team_obj.get("name") or team_name

    # 💡 Aquí viene el truco:
    # raw["athletes"] es una lista de grupos como:
    # [
    #   {"position": "offense", "items": [ {...}, {...} ]},
    #   {"position": "defense", "items": [ {...}, {...} ]},
    #   ...
    # ]
    # Tenemos que *aplanar* todos los items de todos los grupos.
    athletes_list: List[Dict[str, Any]] = []

    groups = raw.get("athletes") or []
    if isinstance(groups, list):
        for group in groups:
            items = group.get("items") or []
            if isinstance(items, list):
                athletes_list.extend(items)

    # Fallback defensivo por si ESPN cambia algo
    if not athletes_list:
        # Intentar otros formatos posibles
        if isinstance(raw.get("athletes"), list):
            athletes_list = raw["athletes"]
        roster = team_obj.get("roster", {}) or {}
        entries = roster.get("entries")
        if isinstance(entries, list):
            athletes_list.extend(entries)

    players_out = _parse_athletes_list(athletes_list)

    return {
        "team_abbr": team_abbr.upper(),
        "team_name": team_name,
        "players": players_out,
    }


def fetch_team_roster_by_abbr(team_abbr: str) -> Optional[Dict[str, Any]]:
    """
    Punto de entrada público:
      - Resuelve team_id desde ESPN con la abreviatura (DAL, KC, PHI, etc.).
      - Llama al endpoint de roster (SITE /teams/{id}/roster).
      - Parsea a estructura simplificada.
    """
    team_id = get_team_id_from_abbr(team_abbr)
    if team_id is None:
        logger.warning(f"[ESPN][NFL][Roster] No se encontró team_id para abreviatura={team_abbr}")
        return None

    raw = fetch_team_roster(team_id)
    if not raw:
        return None

    return parse_team_roster(raw, team_abbr=team_abbr)
