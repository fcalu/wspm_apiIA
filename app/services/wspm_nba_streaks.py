from typing import Any, Dict, List, Optional, Tuple

from app.services.espn_nba_client import fetch_nba_scoreboard
from app.services.espn_nba_roster_client import fetch_nba_team_roster_by_abbr
from app.services.espn_nba_players_client import fetch_nba_player_gamelog
from app.services.wspm_nba_engine import _find_stat_index, _extract_regular_season_events


DEFAULT_THRESHOLDS = {
    "points": [23, 18, 16, 15, 14, 13, 12, 11],
    "rebounds": [7, 5, 4],
    "assists": [5, 4, 3, 2],
    "threes_made": [1],
}

ALIASES = {
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


def _compute_streak(values: List[float], threshold: float) -> int:
    """
    Cuenta cuántos juegos consecutivos (desde el más reciente hacia atrás)
    cumplen >= threshold.
    """
    streak = 0
    for v in values:
        if v >= threshold:
            streak += 1
        else:
            break
    return streak


def _extract_stat_series(
    gamelog: Dict[str, Any],
    stat_key: str,
) -> List[float]:
    names = gamelog.get("names", [])
    idx = _find_stat_index(names, ALIASES[stat_key])
    if idx is None:
        return []

    events = _extract_regular_season_events(gamelog)
    if not events:
        return []

    # Order cronológico -> tomamos recientes desde el final
    recent = list(reversed(events))

    out: List[float] = []
    for ev in recent:
        stats = ev.get("stats", [])
        if isinstance(stats, list) and len(stats) > idx:
            raw = stats[idx]
            try:
                out.append(float(str(raw).replace(",", "")))
            except (TypeError, ValueError):
                out.append(0.0)
    return out


def _get_teams_playing(date: str) -> List[str]:
    sb = fetch_nba_scoreboard(date)
    if not sb:
        return []

    teams: List[str] = []
    for ev in sb.get("events", []) or []:
        comps = ev.get("competitions", [])
        comp = comps[0] if comps else {}
        competitors = comp.get("competitors", [])

        for c in competitors:
            team = c.get("team", {}) or {}
            abbr = team.get("abbreviation")
            if abbr:
                teams.append(abbr)

    # unique
    return sorted(list(set(teams)))


def build_streaks_for_date(
    date: str,
    season: int,
    season_type: int = 2,
) -> Dict[str, Any]:
    """
    Arma el output final tipo imagen:
    - detecta equipos por scoreboard del día
    - trae roster por team_abbr
    - consulta gamelog por jugador
    - calcula rachas por thresholds base
    """

    team_abbrs = _get_teams_playing(date)

    players: List[Dict[str, Any]] = []

    for abbr in team_abbrs:
        roster = fetch_nba_team_roster_by_abbr(abbr)
        if not roster:
            continue

        for p in roster.get("players", []):
            if p.get("position") in ("G", "F", "C", "PG", "SG", "SF", "PF"):
                players.append(p)
            else:
                # si no trae posición clara, igual lo dejamos pasar
                players.append(p)

    # Unique por athlete_id
    seen = set()
    unique_players = []
    for p in players:
        aid = p.get("athlete_id")
        if not aid or aid in seen:
            continue
        seen.add(aid)
        unique_players.append(p)

    # Contenedores de resultados
    buckets = {
        "points": [],
        "rebounds": [],
        "assists": [],
        "threes_made": [],
    }

    for p in unique_players:
        athlete_id = p["athlete_id"]
        name = p.get("name", "N/A")

        try:
            gamelog = fetch_nba_player_gamelog(
                athlete_id=athlete_id,
                season=season,
                season_type=season_type,
            )
        except Exception:
            continue

        for stat_key in buckets.keys():
            series = _extract_stat_series(gamelog, stat_key)
            if not series:
                continue

            # Probamos thresholds en orden descendente
            for th in DEFAULT_THRESHOLDS[stat_key]:
                streak_len = _compute_streak(series, th)
                if streak_len >= 5:
                    # Guardamos una entrada por el primer threshold válido
                    buckets[stat_key].append(
                        {
                            "player_name": name,
                            "team_abbr": p.get("team_abbr"),
                            "threshold": th,
                            "streak": streak_len,
                        }
                    )
                    break

    # Ordenar por streak desc
    for k in buckets.keys():
        buckets[k] = sorted(buckets[k], key=lambda x: x["streak"], reverse=True)

    # Formato final amigable
    return {
        "date": date,
        "season": season,
        "season_type": season_type,
        "teams_detected": team_abbrs,
        "PTS_Streaks": [
            f"{x['player_name']} ({x.get('team_abbr','')}) – {x['streak']} straight with {x['threshold']}+ PTS"
            for x in buckets["points"]
        ],
        "REB_Streaks": [
            f"{x['player_name']} ({x.get('team_abbr','')}) – {x['streak']} straight with {x['threshold']}+ REB"
            for x in buckets["rebounds"]
        ],
        "AST_Streaks": [
            f"{x['player_name']} ({x.get('team_abbr','')}) – {x['streak']} straight with {x['threshold']}+ AST"
            for x in buckets["assists"]
        ],
        "FG3M_Streaks": [
            f"{x['player_name']} ({x.get('team_abbr','')}) – {x['streak']} straight with {x['threshold']}+ FG3M"
            for x in buckets["threes_made"]
        ],
        "raw": buckets,
    }
