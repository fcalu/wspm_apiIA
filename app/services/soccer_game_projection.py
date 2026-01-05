# app/services/soccer_game_projection.py

from typing import Any, Dict, Optional, Tuple

from app.schemas.nfl import TeamInfo


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_team_info_from_event(event: Dict[str, Any]) -> Tuple[Optional[TeamInfo], Optional[TeamInfo]]:
    comp = (event.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []

    home_team: Optional[TeamInfo] = None
    away_team: Optional[TeamInfo] = None

    for c in competitors:
        side = c.get("homeAway")
        team = c.get("team") or {}
        info = TeamInfo(
            name=team.get("displayName") or team.get("name"),
            abbr=team.get("abbreviation"),
        )
        if side == "home":
            home_team = info
        elif side == "away":
            away_team = info

    return home_team, away_team


def _form_score(competitor: Dict[str, Any]) -> float:
    """
    Intenta derivar una métrica simple de forma reciente usando algo tipo 'WDLDW'.

    Si ESPN no trae esa info, devolvemos 0.0 y el modelo sigue funcionando.
    """
    records = competitor.get("records") or []
    form_str = None

    for rec in records:
        # ESPN suele usar type='form' o 'recent' con summary='WDLDW'
        if rec.get("type") in ("form", "recent"):
            form_str = rec.get("summary") or rec.get("displayValue")
            break

    if not form_str or not isinstance(form_str, str):
        return 0.0

    score = 0.0
    for ch in form_str:
        u = ch.upper()
        if u == "W":
            score += 1.0
        elif u == "D":
            score += 0.4
        elif u == "L":
            score -= 1.0

    return score


def _edge_to_prob_and_conf(edge_pct: float) -> Tuple[float, str]:
    abs_edge = abs(edge_pct)
    if abs_edge < 2:
        return 0.53, "Baja"
    if abs_edge < 5:
        return 0.56, "Media"
    if abs_edge < 10:
        return 0.60, "Media-Alta"
    return 0.65, "Alta"


def compute_soccer_game_projection(
    event: Dict[str, Any],
    odds_item: Dict[str, Any],
    line_over25: float = 2.5,
) -> Dict[str, Any]:
    """
    Modelo WQM simplificado para Fútbol.

    - Usa la línea de totales del book como expectativa base de goles.
    - Ajusta suavemente por "forma" de los equipos (si está disponible).
    - Genera picks para:
        * Over/Under 2.5 goles
        * Ambos Anotan (BTTS)
        * 1X2 (1, X, 2)
        * Doble oportunidad (1X, X2, 12)
    """
    home_team, away_team = _get_team_info_from_event(event)

    comp = (event.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []

    home_comp = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away_comp = next((c for c in competitors if c.get("homeAway") == "away"), {})

    home_form = _form_score(home_comp)
    away_form = _form_score(away_comp)

    # ----------------- Odds base -----------------
    book_total = _safe_float(odds_item.get("overUnder")) or line_over25

    home_odds = odds_item.get("homeTeamOdds") or {}
    away_odds = odds_item.get("awayTeamOdds") or {}

    home_spread = _safe_float(home_odds.get("spread"))
    away_spread = _safe_float(away_odds.get("spread"))

    # Si sólo viene un spread, asumimos el opuesto para el otro
    if home_spread is None and away_spread is not None:
        home_spread = -away_spread
    if away_spread is None and home_spread is not None:
        away_spread = -home_spread

    # Diferencial de gol esperado: típico -0.5 / -1.0 para local favorito
    goal_handicap = home_spread or 0.0

    # ----------------- Modelo de totales -----------------
    # Ajuste suave por forma: delta_form * 0.10 goles
    form_delta = (home_form - away_form) * 0.10
    model_total = book_total + form_delta

    # Over 2.5
    edge_goals = model_total - line_over25
    if line_over25 <= 0:
        margin_over_pct = 0.0
    else:
        margin_over_pct = (edge_goals / line_over25) * 100.0

    pick_over = "OVER_2_5" if edge_goals > 0 else "UNDER_2_5"
    prob_over, conf_over = _edge_to_prob_and_conf(margin_over_pct)

    # ----------------- Ambos anotan (BTTS) -----------------
    # Heurística: totales altos + partido parejo favorecen "Sí".
    total_factor = max(0.0, min(1.0, (model_total - 2.2)))  # 0 → 1 aprox entre 2.2 y 3.2
    balance_factor = 1.0 - min(1.0, abs(goal_handicap)) * 0.3

    base_btts_prob = 0.45 + 0.20 * total_factor * balance_factor
    base_btts_prob = max(0.10, min(0.90, base_btts_prob))

    pick_btts = "YES" if base_btts_prob >= 0.53 else "NO"

    diff_btts_pct = abs(base_btts_prob - 0.5) * 100.0
    if diff_btts_pct < 3:
        conf_btts = "Baja"
    elif diff_btts_pct < 7:
        conf_btts = "Media"
    elif diff_btts_pct < 12:
        conf_btts = "Media-Alta"
    else:
        conf_btts = "Alta"

    # ----------------- 1X2 -----------------
    # Usamos el handicap como proxy de fuerza local/visita.
    hcap_clamped = max(-1.5, min(1.5, goal_handicap))
    strength = -hcap_clamped  # negativo spread => local favorito

    prob_home = 0.33 + 0.18 * max(0.0, strength) / 1.5
    prob_away = 0.33 + 0.18 * max(0.0, -strength) / 1.5

    remaining = 1.0 - (prob_home + prob_away)
    prob_draw = max(0.15, remaining)

    s = prob_home + prob_away + prob_draw
    prob_home /= s
    prob_away /= s
    prob_draw /= s

    probs = {"1": prob_home, "X": prob_draw, "2": prob_away}
    pick_1x2 = max(probs.items(), key=lambda kv: kv[1])[0]
    prob_1x2 = probs[pick_1x2]

    sorted_probs = sorted(probs.values(), reverse=True)
    gap = (sorted_probs[0] - sorted_probs[1]) * 100.0
    if gap < 4:
        conf_1x2 = "Baja"
    elif gap < 8:
        conf_1x2 = "Media"
    elif gap < 12:
        conf_1x2 = "Media-Alta"
    else:
        conf_1x2 = "Alta"

    # ----------------- Doble oportunidad -----------------
    if pick_1x2 == "1":
        pick_dc = "1X"
        prob_dc = prob_home + prob_draw
    elif pick_1x2 == "2":
        pick_dc = "X2"
        prob_dc = prob_away + prob_draw
    else:
        pick_dc = "12"
        prob_dc = prob_home + prob_away

    diff_dc_pct = (prob_dc - 0.5) * 100.0
    if diff_dc_pct < 5:
        conf_dc = "Baja"
    elif diff_dc_pct < 10:
        conf_dc = "Media"
    elif diff_dc_pct < 15:
        conf_dc = "Media-Alta"
    else:
        conf_dc = "Alta"

    return {
        "event_id": str(event.get("id")),
        "matchup": event.get("name") or "",
        "home_team": home_team,
        "away_team": away_team,
        "book_total": float(book_total),
        "model_total": float(model_total),
        "pick_over25": pick_over,
        "prob_over25": round(prob_over * 100.0, 1),
        "confidence_over25": conf_over,
        "edge_over25": round(edge_goals, 3),
        "margin_over25_pct": round(margin_over_pct, 2),
        "pick_btts": pick_btts,
        "prob_btts": round(base_btts_prob * 100.0, 1),
        "confidence_btts": conf_btts,
        "pick_1x2": pick_1x2,
        "prob_1x2": round(prob_1x2 * 100.0, 1),
        "confidence_1x2": conf_1x2,
        "pick_double_chance": pick_dc,
        "prob_double_chance": round(prob_dc * 100.0, 1),
        "confidence_double_chance": conf_dc,
    }
