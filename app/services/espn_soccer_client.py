# app/services/espn_soccer_client.py

from typing import Optional, Dict, Any

import requests

from app.config import settings
from app.utils.cache import get_from_cache, set_in_cache
from app.core.logging import logger


def _resolve_league_code(raw_league: Optional[str]) -> str:
    """
    Normaliza el parámetro de liga para usarlo en las URLs de ESPN.

    Acepta:
      - None -> usa liga por defecto (settings.espn_soccer_default_league)
      - alias definido en settings.espn_soccer_leagues (ej. "laliga")
      - código ESPN directo (ej. "esp.1", "eng.1")
    """
    if not raw_league:
        return settings.espn_soccer_default_league

    league = raw_league.strip()

    # 1) Si viene ya un código ESPN válido (ej: "esp.1") lo aceptamos tal cual
    if league in settings.espn_soccer_leagues.values():
        return league

    # 2) Si viene un alias (ej: "laliga", "premier_league")
    if league in settings.espn_soccer_leagues:
        return settings.espn_soccer_leagues[league]

    # 3) Fallback: usar lo que venga (permite probar ligas no mapeadas aún)
    return league


def _build_site_base_url(league_code: str) -> str:
    """
    Construye el base_url 'site' para una liga dada (scoreboard).
    """
    return settings.espn_soccer_site_base_url_template.format(
        league_code=league_code
    )


def _build_core_base_url(league_code: str) -> str:
    """
    Construye el base_url 'core' para una liga dada (odds).
    """
    return settings.espn_soccer_core_base_url_template.format(
        league_code=league_code
    )


def fetch_soccer_scoreboard_data(
    league: Optional[str] = None,
    use_cache: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Obtiene el scoreboard de una liga de soccer específica.

    Parámetros:
      - league: puede ser alias ("laliga") o código ESPN ("esp.1").
        Si es None, usa settings.espn_soccer_default_league.
    """
    league_code = _resolve_league_code(league)
    cache_key = f"soccer:scoreboard:{league_code}"

    if use_cache:
        cached = get_from_cache(
            cache_key,
            ttl_seconds=settings.espn_cache_ttl_seconds,
        )
        if cached is not None:
            logger.info(f"[ESPN][SOCCER] Cache HIT scoreboard {league_code}")
            return cached

    base_url = _build_site_base_url(league_code)
    url = f"{base_url}/scoreboard"

    logger.info(f"[ESPN][SOCCER] Fetch scoreboard {league_code} URL={url}")

    try:
        resp = requests.get(
            url,
            timeout=settings.espn_timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()

        if use_cache:
            set_in_cache(cache_key, data)
            logger.info(f"[ESPN][SOCCER] Cache SET scoreboard {league_code}")

        return data
    except requests.RequestException as e:
        logger.error(
            f"[ESPN][SOCCER] Error al obtener scoreboard {league_code}: {e}"
        )
        return None


def fetch_soccer_game_odds(
    event_id: str,
    league: Optional[str] = None,
    use_cache: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Obtiene las odds de un partido de soccer para una liga concreta.
    """
    league_code = _resolve_league_code(league)
    cache_key = f"soccer:odds:{league_code}:{event_id}"

    if use_cache:
        cached = get_from_cache(
            cache_key,
            ttl_seconds=settings.espn_cache_ttl_seconds,
        )
        if cached is not None:
            logger.info(f"[ESPN][SOCCER] Cache HIT odds {league_code} ev={event_id}")
            return cached

    core_base = _build_core_base_url(league_code)
    url = f"{core_base}/events/{event_id}/competitions/{event_id}/odds"

    logger.info(
        f"[ESPN][SOCCER] Fetch odds {league_code} ev={event_id} URL={url}"
    )

    try:
        resp = requests.get(
            url,
            timeout=settings.espn_timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()

        if use_cache:
            set_in_cache(cache_key, data)
            logger.info(
                f"[ESPN][SOCCER] Cache SET odds {league_code} ev={event_id}"
            )

        return data
    except requests.RequestException as e:
        logger.error(
            f"[ESPN][SOCCER] Error al obtener odds {league_code} ev={event_id}: {e}"
        )
        return None
