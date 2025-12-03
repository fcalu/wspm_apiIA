# app/services/wspm_nfl_engine.py

from typing import Any, Dict, List, Optional


def _extract_stat_from_game(game: Any, stat_names: List[str]) -> Optional[float]:
    """
    Intenta extraer un stat numérico de un "game" del gamelog de ESPN.

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

    - gamelog: JSON devuelto por el endpoint de gamelog de ESPN.
    - market_type: "receiving_yards", "rushing_yards", "passing_yards".
    - games_window: cuántos partidos recientes considerar.

    Estrategia:
    - Buscamos dentro de gamelog["splits"] los partidos individuales.
    - De cada partido, extraemos el stat relevante (recYds, rushYds, passYds, etc.).
    - Calculamos la media de los últimos N con valor.
    """

    if not gamelog or not isinstance(gamelog, Dict):
        return 0.0

    stat_map = {
        "receiving_yards": ["recYds", "yards"],
        "rushing_yards": ["rushYds", "yards"],
        "passing_yards": ["passYds", "yards"],
    }

    stat_names = stat_map.get(market_type)
    if not stat_names:
        # Mercado desconocido: por ahora devolvemos 0.0
        return 0.0

    splits_root = gamelog.get("splits", {})
    games: List[Any] = []

    # Intento 1: splits_root["splits"] es directamente la lista de partidos
    if isinstance(splits_root, Dict):
        if isinstance(splits_root.get("splits"), list):
            games = splits_root["splits"]
        else:
            # Intento 2: categories -> cada categoría tiene "splits"
            categories = splits_root.get("categories")
            if isinstance(categories, list):
                for cat in categories:
                    if not isinstance(cat, Dict):
                        continue
                    cat_splits = cat.get("splits")
                    if isinstance(cat_splits, list):
                        games.extend(cat_splits)

    if not games or not isinstance(games, list):
        return 0.0

    # Usamos los últimos N partidos (más recientes)
    # ESPN suele ordenar cronológicamente, pero para estar seguros invertimos.
    recent_games = list(reversed(games))[:games_window]

    values: List[float] = []
    for g in recent_games:
        val = _extract_stat_from_game(g, stat_names)
        if val is not None:
            values.append(val)

    if not values:
        return 0.0

    return float(sum(values) / len(values))
