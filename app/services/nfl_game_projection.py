# app/services/nfl_game_projection.py

from typing import Dict, Any, Tuple, List

from app.services.espn_nfl_client import fetch_scoreboard_data


def _collect_recent_team_points(
    team_abbr: str,
    current_week: int,
    season_type: int,
    games_window: int = 5,
) -> Tuple[float, float]:
    """
    Recolecta puntos a favor y en contra recientes para un equipo usando el scoreboard de ESPN.
    Busca hacia atrás desde current_week-1 hasta la 1.
    """

    points_for: List[float] = []
    points_against: List[float] = []

    # Recorremos semanas hacia atrás
    for wk in range(current_week - 1, 0, -1):
        sb = fetch_scoreboard_data(wk, season_type)
        if not sb or "events" not in sb:
            continue

        for ev in sb.get("events", []):
            competitions = ev.get("competitions", [])
            if not competitions:
                continue
            comp = competitions[0]
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue

            # Solo partidos finalizados
            status_type = (comp.get("status") or {}).get("type") or {}
            if not status_type.get("completed", False):
                continue

            home = competitors[0]
            away = competitors[1]

            for side in (home, away):
                team = side.get("team", {}) or {}
                abbr = team.get("abbreviation")
                if abbr != team_abbr:
                    continue

                # Rival
                other = away if side is home else home
                try:
                    pf = float(side.get("score", 0))
                    pa = float(other.get("score", 0))
                except (TypeError, ValueError):
                    continue

                points_for.append(pf)
                points_against.append(pa)
                break

            if len(points_for) >= games_window:
                break

        if len(points_for) >= games_window:
            break

    if not points_for:
        return 0.0, 0.0

    avg_pf = sum(points_for) / len(points_for)
    avg_pa = sum(points_against) / len(points_against) if points_against else 0.0
    return float(avg_pf), float(avg_pa)


def compute_game_projection(
    event_id: str,
    week: int,
    season_type: int,
    book_total: float,
    book_spread: float,
    games_window: int = 5,
) -> Dict[str, Any]:
    """
    Calcula una proyección simple de TOTAL y SPREAD para un partido NFL.

    - Identifica home/away con el scoreboard de esa semana.
    - Mira semanas anteriores y calcula:
        * puntos a favor recientes de cada equipo
        * puntos en contra recientes de cada equipo
    - Proyecta:
        * total de puntos del partido
        * spread (home - away)
    - Compara vs líneas del book (total y spread) y calcula edges/márgenes.
    """

    scoreboard = fetch_scoreboard_data(week, season_type)
    if not scoreboard or "events" not in scoreboard:
        raise ValueError("No se pudo obtener el scoreboard para esa semana.")

    event = next((e for e in scoreboard["events"] if e.get("id") == event_id), None)
    if not event:
        raise ValueError(f"No se encontró el evento {event_id} en el scoreboard.")

    name = event.get("name", "Partido NFL")
    competitions = event.get("competitions", [])
    comp = competitions[0] if competitions else {}
    competitors = comp.get("competitors", [])
    if len(competitors) < 2:
        raise ValueError("Formato inesperado de competitors en el scoreboard.")

    # Identificar home / away
    home_team = None
    away_team = None
    for c in competitors:
        side = c.get("homeAway")
        team = c.get("team", {}) or {}
        info = {
            "name": team.get("displayName"),
            "abbr": team.get("abbreviation"),
        }
        if side == "home":
            home_team = info
        elif side == "away":
            away_team = info

    if not home_team or not away_team:
        raise ValueError("No fue posible identificar home/away en el evento.")

    # Medias recientes de puntos anotados / permitidos
    home_pf, home_pa = _collect_recent_team_points(
        home_team["abbr"], week, season_type, games_window
    )
    away_pf, away_pa = _collect_recent_team_points(
        away_team["abbr"], week, season_type, games_window
    )

    # Si no tenemos historial, devolvemos algo trivial basado en el book
    if home_pf == 0.0 and away_pf == 0.0:
        model_total = book_total
        model_spread = book_spread
        home_proj = (book_total + book_spread) / 2.0
        away_proj = (book_total - book_spread) / 2.0
    else:
        # Puntos esperados para cada equipo:
        # promedio de lo que suele anotar y lo que suele permitir el rival
        home_proj = (home_pf + away_pa) / 2.0 if away_pa > 0 else home_pf
        away_proj = (away_pf + home_pa) / 2.0 if home_pa > 0 else away_pf

        model_total = home_proj + away_proj
        model_spread = home_proj - away_proj  # margen home - away

    # Implied totals del book (spread desde perspectiva local)
    # H - A = spread, H + A = total  ->  H = (T + s)/2, A = (T - s)/2
    implied_home = (book_total + book_spread) / 2.0
    implied_away = (book_total - book_spread) / 2.0

    edge_total = model_total - book_total
    edge_spread = model_spread - book_spread

    if book_total != 0:
        margin_total_pct = (edge_total / abs(book_total)) * 100.0
    else:
        margin_total_pct = 0.0

    if book_spread != 0:
        margin_spread_pct = (edge_spread / abs(book_spread)) * 100.0
    else:
        # si spread = 0, normalizamos respecto a 3 pts (ventaja de campo est.)
        margin_spread_pct = (edge_spread / 3.0) * 100.0 if edge_spread != 0 else 0.0

    safety_total = abs(edge_total)
    safety_total_pct = abs(margin_total_pct)

    safety_spread = abs(edge_spread)
    safety_spread_pct = abs(margin_spread_pct)

    def _conf(pct: float) -> str:
        if pct >= 15:
            return "Alta"
        elif pct >= 10:
            return "Media-Alta"
        elif pct >= 5:
            return "Media"
        else:
            return "Baja"

    # Probabilidades aproximadas (misma lógica que WSPM de jugadores)
    def _prob_from_safety(pct: float) -> float:
        if pct >= 15:
            return 70.0
        elif pct >= 10:
            return 65.0
        elif pct >= 5:
            return 60.0
        elif pct >= 2:
            return 55.0
        else:
            return 52.0

    prob_total = _prob_from_safety(safety_total_pct)
    prob_spread = _prob_from_safety(safety_spread_pct)

    direction_total = "OVER" if edge_total > 0 else "UNDER"
    # Valor en spread: si el modelo cree que el margen home debe ser > que la línea,
    # hay valor en el home. Si es menor, valor en el away.
    side_spread = "HOME" if model_spread > book_spread else "AWAY"

    return {
        "event_id": event_id,
        "matchup": name,
        "home_team": home_team,
        "away_team": away_team,
        "book_total": book_total,
        "book_spread": book_spread,
        "implied_home_total": implied_home,
        "implied_away_total": implied_away,
        "model_home_total": home_proj,
        "model_away_total": away_proj,
        "model_total": model_total,
        "model_spread": model_spread,
        "edge_total": edge_total,
        "edge_spread": edge_spread,
        "margin_total_pct": margin_total_pct,
        "margin_spread_pct": margin_spread_pct,
        "safety_total": safety_total,
        "safety_total_pct": safety_total_pct,
        "safety_spread": safety_spread,
        "safety_spread_pct": safety_spread_pct,
        "prob_total": prob_total,
        "prob_spread": prob_spread,
        "direction_total": direction_total,
        "side_spread": side_spread,
        "confidence_total": _conf(safety_total_pct),
        "confidence_spread": _conf(safety_spread_pct),
        "games_window": games_window,
    }
