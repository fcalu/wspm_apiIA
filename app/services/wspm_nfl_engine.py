# app/services/wspm_nfl_engine.py

from typing import Any, Dict, List, Optional


def _extract_stat_from_game(game: Any, stat_names: List[str]) -> Optional[float]:
    """
    Intenta extraer un stat numérico de un "game" del gamelog de ESPN.
    (Lógica original, se mantiene por estructura, pero la función principal usa otra lógica)
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

    # Caso 2: categorías con stats
    categories = game.get("categories")
    if isinstance(categories, list):
        for cat in categories:
            if not isinstance(cat, Dict):
                continue
            stats2 = cat.get("stats")
            if not isinstance(stats2, list):
                continue
            for st in stats2:
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


def compute_base_projection_from_gamelog(
    gamelog: Dict[str, Any],
    market_type: str,
    games_window: int = 5,
) -> float:
    """
    Calcula una proyección base (media reciente) usando el gamelog real de ESPN.

    CORRECCIÓN: Implementa la lógica de búsqueda por índice ('names' -> 'events'[i]['stats'])
    para soportar el formato actual de ESPN.
    """

    if not gamelog or not isinstance(gamelog, Dict):
        return 0.0

    # 1. Mapeo de market_type a la clave del JSON "names"
    market_to_name = {
        "receiving_yards": "receivingYards",
        "rushing_yards": "rushingYards",
        "passing_yards": "passingYards",
        "receptions": "receptions",
        "rushing_attempts": "rushingAttempts",
    }

    target_stat_name = market_to_name.get(market_type)
    if not target_stat_name:
        return 0.0

    # 2. Encontrar el índice del stat
    stat_names_list: List[str] = gamelog.get("names", [])
    try:
        stat_idx = stat_names_list.index(target_stat_name)
    except ValueError:
        return 0.0

    # 3. Encontrar los eventos (juegos) de la Temporada Regular
    regular_season_events: List[Any] = []
    season_types = gamelog.get("seasonTypes", [])

    for st in season_types:
        # Busca la Temporada Regular (splitType "2")
        if st.get("splitType") == "2":
            categories = st.get("categories", [])
            for cat in categories:
                events = cat.get("events")
                if isinstance(events, list):
                    regular_season_events.extend(events)
            break

    if not regular_season_events:
        return 0.0

    # 4. Extraer los valores de la estadística usando el índice
    # Se revierte para tomar los más recientes (asumiendo que los eventos se listan cronológicamente)
    recent_events = list(reversed(regular_season_events))

    values: List[float] = []
    for event in recent_events:
        stats_array = event.get("stats", [])

        if len(stats_array) > stat_idx:
            val_str = stats_array[stat_idx]
            try:
                # Se eliminan comas para números grandes (ej. "1,412")
                val = float(val_str.replace(",", ""))

                # Incluir el valor si es positivo o si la ventana no se ha completado
                if val > 0.0 or len(values) < games_window:
                    values.append(val)
                
            except (TypeError, ValueError):
                continue

        if len(values) >= games_window:
            break

    # 5. Calcular el promedio
    if not values:
        return 0.0

    return float(sum(values) / len(values))