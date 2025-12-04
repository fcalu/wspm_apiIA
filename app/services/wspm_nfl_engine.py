# app/services/wspm_nfl_engine.py

from typing import Any, Dict, List, Optional


# -----------------------------------------------------------------------------
# (Legacy) Helper para formatos antiguos tipo "stats": [{"name": "...", ...}]
# Lo dejo por compatibilidad, pero la lógica principal ya NO depende de esto.
# -----------------------------------------------------------------------------
def _extract_stat_from_game(game: Any, stat_names: List[str]) -> Optional[float]:
    """
    Intenta extraer un stat numérico de un "game" del gamelog de ESPN en formato
    antiguo (lista de dicts con name/value).

    - stat_names: lista de nombres posibles, ej. ["recYds", "yards"].
    """
    if not isinstance(game, Dict):
        return None

    # Caso 1: stats directos en el nivel del partido
    stats = game.get("stats")
    if isinstance(stats, list):
        for st in stats:
            if not isinstance(st, Dict):
                continue
            name = st.get("name")
            if name in stat_names:
                val = st.get("value") or st.get("displayValue")
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue

    # Caso 2 (fallback): quizá dentro de otro sub-objeto
    boxscore = game.get("boxscore")
    if isinstance(boxscore, Dict):
        for key in ["passing", "rushing", "receiving", "defensive"]:
            group = boxscore.get(key)
            if isinstance(group, list):
                for st in group:
                    if not isinstance(st, Dict):
                        continue
                    name = st.get("name")
                    if name in stat_names:
                        val = st.get("value") or st.get("displayValue")
                        try:
                            return float(val)
                        except (TypeError, ValueError):
                            continue

    return None


# -----------------------------------------------------------------------------
# Helpers para el NUEVO formato indexado de gamelog (names + seasonTypes)
# -----------------------------------------------------------------------------


def _get_regular_season_events_from_indexed_gamelog(
    gamelog: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Extrae la lista de 'events' (partidos) de la temporada regular
    desde un gamelog indexado de ESPN.

    Estructura típica:
      {
        "names": [...],
        "seasonTypes": [
          {
            "displayName": "2024 Regular Season",
            "splitType": "2",
            "categories": [
              {
                "displayName": "...",
                "events": [
                  { "stats": [ ... ], ... },
                  ...
                ]
              },
              ...
            ]
          },
          ...
        ]
      }
    """
    events: List[Dict[str, Any]] = []
    season_types = gamelog.get("seasonTypes", [])

    for st in season_types:
        # splitType "2" suele corresponder a Regular Season
        if st.get("splitType") == "2" or str(st.get("displayName", "")).endswith("Regular Season"):
            categories = st.get("categories", [])
            for cat in categories:
                cat_events = cat.get("events")
                if isinstance(cat_events, list):
                    events.extend(cat_events)
            # si ya encontramos Regular Season, podemos salir
            break

    return events


# -----------------------------------------------------------------------------
# LÓGICA PRINCIPAL: calcular base_projection desde gamelog REAL de ESPN
# -----------------------------------------------------------------------------


def compute_base_projection_from_gamelog(
    gamelog: Dict[str, Any],
    market_type: str,
    games_window: int = 5,
) -> float:
    """
    Calcula una proyección base (media reciente) usando el gamelog real de ESPN.

    Está adaptada al formato indexado:

      - gamelog["names"] = ["gamesPlayed", "rushingYards", "receivingYards", ...]
      - cada event["stats"] = array con los valores en el mismo orden que "names"

    Soporta de momento:
      - "rushing_yards"   -> "rushingYards"
      - "receiving_yards" -> "receivingYards"
      - "passing_yards"   -> "passingYards"

    Si no puede encontrar el stat o no hay suficientes datos,
    devuelve 0.0 (tu endpoint /auto-projection-report decide si lanza error).
    """

    if not gamelog or not isinstance(gamelog, Dict):
        # No hay gamelog → no hay nada que promediar
        return 0.0

    # -------------------------------------------------------------------------
    # 1) Mapeo de market_type (externo) a nombre interno del gamelog ("names")
    # -------------------------------------------------------------------------
    market_to_name: Dict[str, str] = {
        "receiving_yards": "receivingYards",
        "rushing_yards": "rushingYards",
        "passing_yards": "passingYards",
        # aquí puedes ir agregando más: "receptions": "receptions", etc.
    }

    target_stat_name = market_to_name.get(market_type)
    if not target_stat_name:
        # Market no soportado aún
        return 0.0

    # -------------------------------------------------------------------------
    # 2) Encontrar el índice del stat en gamelog["names"]
    # -------------------------------------------------------------------------
    stat_names_list: List[str] = gamelog.get("names", [])
    if not isinstance(stat_names_list, list) or not stat_names_list:
        # No viene el arreglo "names" → intentamos fallback legacy
        return _compute_base_projection_legacy(gamelog, market_type, games_window)

    try:
        stat_idx = stat_names_list.index(target_stat_name)
    except ValueError:
        # El stat no se encuentra en la lista de nombres → fallback
        return _compute_base_projection_legacy(gamelog, market_type, games_window)

    # -------------------------------------------------------------------------
    # 3) Extraer partidos de temporada regular y tomar los más recientes
    # -------------------------------------------------------------------------
    regular_events = _get_regular_season_events_from_indexed_gamelog(gamelog)
    if not regular_events:
        # No hay eventos de temporada regular → fallback
        return _compute_base_projection_legacy(gamelog, market_type, games_window)

    # Ordénalos del más reciente al más antiguo (la API suele traerlos en orden,
    # pero invertimos para estar seguros) y toma la ventana de N juegos.
    recent_events = list(reversed(regular_events))

    values: List[float] = []
    for event in recent_events:
        stats_array = event.get("stats", [])
        if not isinstance(stats_array, list):
            continue

        if len(stats_array) <= stat_idx:
            continue

        raw_val = stats_array[stat_idx]

        try:
            # Los stats suelen venir como string, a veces con comas "1,234".
            val = float(str(raw_val).replace(",", ""))
        except (TypeError, ValueError):
            continue

        # Aquí NO filtramos los ceros; asumimos que 0 es un valor válido
        # (ej. RB jugó poco, o QB con pocos pases, etc.)
        values.append(val)

        if len(values) >= games_window:
            break

    if not values:
        # Si no se logró extraer nada del formato indexado, último intento: legacy
        return _compute_base_projection_legacy(gamelog, market_type, games_window)

    return float(sum(values) / len(values))


# -----------------------------------------------------------------------------
# Fallback: intentar con formato "legacy" (dicts con name/displayValue)
# -----------------------------------------------------------------------------


def _compute_base_projection_legacy(
    gamelog: Dict[str, Any],
    market_type: str,
    games_window: int,
) -> float:
    """
    Fallback para cuando el gamelog NO viene en formato indexado o el stat
    que buscamos no existe ahí.

    Usa la lógica vieja con _extract_stat_from_game.
    """

    # Mapeo "legacy"
    market_stat_legacy: Dict[str, List[str]] = {
        "receiving_yards": ["recYds", "yards", "REC_YDS"],
        "rushing_yards": ["rushYds", "yards", "RUSH_YDS"],
        "passing_yards": ["passYds", "yards", "PASS_YDS"],
    }

    stat_names = market_stat_legacy.get(market_type)
    if not stat_names:
        return 0.0

    # Distintas claves posibles donde la API ya pudo meter la lista de juegos.
    games = gamelog.get("events") or gamelog.get("gamelog") or gamelog.get("games")
    if not isinstance(games, list) or not games:
        return 0.0

    # Usamos los últimos N partidos (más recientes)
    recent_games = list(reversed(games))[:games_window]

    values: List[float] = []
    for g in recent_games:
        val = _extract_stat_from_game(g, stat_names)
        if val is not None:
            values.append(val)

    if not values:
        return 0.0

    return float(sum(values) / len(values))
