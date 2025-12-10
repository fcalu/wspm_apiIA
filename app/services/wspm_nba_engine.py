from typing import Any, Dict, List, Optional


def _find_stat_index(names: List[str], aliases: List[str]) -> Optional[int]:
    if not isinstance(names, list):
        return None

    lowered = [n.lower() for n in names]

    for a in aliases:
        a_l = a.lower()
        if a_l in lowered:
            return lowered.index(a_l)

    # fallback: match parcial
    for i, n in enumerate(lowered):
        for a in aliases:
            if a.lower() in n:
                return i

    return None


def _extract_regular_season_events(gamelog: Dict[str, Any]) -> List[Dict[str, Any]]:
    season_types = gamelog.get("seasonTypes", [])
    for st in season_types:
        if st.get("splitType") == "2" or str(st.get("displayName", "")).endswith("Regular Season"):
            events: List[Dict[str, Any]] = []
            for cat in st.get("categories", []) or []:
                evs = cat.get("events")
                if isinstance(evs, list):
                    events.extend(evs)
            return events

    # fallback: si no encuentra splitType 2, intenta unir todo
    events: List[Dict[str, Any]] = []
    for st in season_types:
        for cat in st.get("categories", []) or []:
            evs = cat.get("events")
            if isinstance(evs, list):
                events.extend(evs)
    return events


def compute_base_projection_from_gamelog(
    gamelog: Dict[str, Any],
    market_type: str,
    games_window: int = 5,
) -> float:
    """
    Proyección base NBA usando formato indexado:
    - names: [ "points", "rebounds", ... ]
    - events[].stats: [ "25", "7", ... ]

    market_type esperados:
    - points
    - rebounds
    - assists
    - threes_made
    """

    if not gamelog or not isinstance(gamelog, Dict):
        return 0.0

    market_aliases = {
        "points": ["points", "pts"],
        "rebounds": ["rebounds", "reb", "totalRebounds"],
        "assists": ["assists", "ast"],
        "threes_made": [
            "threePointFieldGoalsMade",
            "threePointFGM",
            "3ptFieldGoalsMade",
            "3ptfgm",
            "fg3m",
        ],
    }

    aliases = market_aliases.get(market_type)
    if not aliases:
        return 0.0

    stat_names_list: List[str] = gamelog.get("names", [])
    stat_idx = _find_stat_index(stat_names_list, aliases)
    if stat_idx is None:
        return 0.0

    events = _extract_regular_season_events(gamelog)
    if not events:
        return 0.0

    recent_events = list(reversed(events))

    values: List[float] = []
    for ev in recent_events:
        stats_array = ev.get("stats", [])
        if not isinstance(stats_array, list):
            continue

        if len(stats_array) > stat_idx:
            raw = stats_array[stat_idx]
            try:
                val = float(str(raw).replace(",", ""))
                values.append(val)
            except (TypeError, ValueError):
                continue

        if len(values) >= games_window:
            break

    if not values:
        return 0.0

    return float(sum(values) / len(values))
