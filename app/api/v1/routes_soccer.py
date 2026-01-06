# app/api/v1/routes_soccer.py

from typing import Any, Dict, List, Optional
from math import exp, factorial

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.services.espn_soccer_client import (
    fetch_soccer_scoreboard_data,
    fetch_soccer_game_odds,
)
from app.schemas.nfl import (  # modelos genéricos reutilizados
    TeamInfo,
    GameWithOdds,
    GamesWithOddsResponse,
    GameOddsSummary,
)

router = APIRouter(
    prefix="/soccer",
    tags=["soccer"],
)

# =========================================================
# Modelos Pydantic para proyección de partido
# =========================================================


class SoccerGameProjectionRequest(BaseModel):
    """
    Request para proyección de un partido de soccer.

    Flujo típico:
      1) Llamas a /soccer/games-with-odds?league=laliga
      2) Tomas un event_id de la respuesta
      3) Llamas a /soccer/game-projection con ese event_id
    """
    event_id: str
    league: Optional[str] = None


class SoccerMarketProjection(BaseModel):
    market: str               # "OVER_25", "1X2", "DOUBLE_CHANCE"
    pick: str                 # ej: "OVER 2.5", "1", "X", "2", "1X", "X2", "12", "NO BET"
    confidence: str           # "Alta" | "Media-Alta" | "Media" | "Baja"
    prob: float               # probabilidad estimada (0-1)
    edge_pct: Optional[float] = None
    note: Optional[str] = None


class SoccerGameProjection(BaseModel):
    event_id: str
    league_code: str

    matchup: str
    home_team: TeamInfo
    away_team: TeamInfo

    # Línea del book (total goles) si existe
    book_over_under: Optional[float]

    # Intensidades de gol (modelo de Poisson Bayes)
    lambda_home: float
    lambda_away: float
    expected_goals: float

    # Probabilidades Poisson totales
    prob_over25_poisson: float

    # Probabilidades 1X2
    prob_1: float
    prob_X: float
    prob_2: float

    # Picks
    over25_pick: SoccerMarketProjection
    pick_1x2: SoccerMarketProjection
    double_chance_best: SoccerMarketProjection


# =========================================================
# Helpers: Bayes + Poisson + ajuste tipo "IA"
# =========================================================

def _poisson_pmf(k: int, lam: float) -> float:
    """P(k; λ) clásico de Poisson."""
    if k < 0:
        return 0.0
    return exp(-lam) * (lam ** k) / factorial(k)


def _extract_record_data(competitor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrae W-D-L y puntos/partido de summaries tipo '10-5-3'.
    Devuelve dict con: w, d, l, games, ppg.
    """
    records = competitor.get("records", [])
    summary_str = None

    for r in records:
        r_type = (r.get("type") or "").lower()
        if r_type in ("total", "league", "overall", ""):
            summary_str = r.get("summary")
            if summary_str:
                break

    if not summary_str or not isinstance(summary_str, str):
        return {"w": 0, "d": 0, "l": 0, "games": 0, "ppg": 0.5}

    try:
        parts = summary_str.replace(" ", "").split("-")
        if len(parts) < 2:
            return {"w": 0, "d": 0, "l": 0, "games": 0, "ppg": 0.5}

        w = int(parts[0])
        l = int(parts[1])
        d = int(parts[2]) if len(parts) >= 3 else 0
        games = w + l + d
        if games <= 0:
            return {"w": 0, "d": 0, "l": 0, "games": 0, "ppg": 0.5}

        pts = 3 * w + d
        ppg = pts / (3.0 * games)  # escala 0..1 aprox
        ppg = max(0.2, min(0.95, ppg))
        return {"w": w, "d": d, "l": l, "games": games, "ppg": ppg}
    except Exception:
        return {"w": 0, "d": 0, "l": 0, "games": 0, "ppg": 0.5}


def _confidence_from_prob(p: float) -> str:
    """Escala de confianza basada en probabilidad."""
    if p >= 0.70:
        return "Alta"
    elif p >= 0.60:
        return "Media-Alta"
    elif p >= 0.55:
        return "Media"
    else:
        return "Baja"


def _compute_bayesian_lambdas(
    book_over_under: Optional[float],
    home_comp: Dict[str, Any],
    away_comp: Dict[str, Any],
) -> Dict[str, float]:
    """
    Modelo Bayes + Poisson para intensidades de gol de cada equipo.

    - Prior de liga: total goles promedio ~ 2.6 (ajustable)
    - Si hay línea de OU del book, usamos eso como prior de total (market wisdom).
    - PPG de cada equipo (a partir de W-D-L) modula ataque/defensa.
    - Shrinkage Bayesiano contra el prior según nº de partidos.
    """
    # Prior de liga
    league_total_prior = 2.6

    if book_over_under is not None and book_over_under > 0:
        total_prior = 0.7 * book_over_under + 0.3 * league_total_prior
    else:
        total_prior = league_total_prior

    # Dividimos prior en home/away con ligera ventaja local
    prior_lambda_home = total_prior * 0.55
    prior_lambda_away = total_prior * 0.45

    home_stats = _extract_record_data(home_comp)
    away_stats = _extract_record_data(away_comp)

    h_ppg = home_stats["ppg"]
    a_ppg = away_stats["ppg"]
    h_games = home_stats["games"]
    a_games = away_stats["games"]

    # Centro en 0 (0 = equipo medio de liga)
    h_strength = h_ppg - 0.5
    a_strength = a_ppg - 0.5

    # Modelo lineal de ataque crudo (antes de Bayes):
    base_each = total_prior / 2.0

    # El home se beneficia más de su propia fuerza y castiga la del rival
    lambda_home_raw = base_each * (
        1.0
        + 0.9 * h_strength   # ataque local
        - 0.5 * a_strength   # defensa rival
        + 0.08               # ventaja local fija
    )

    lambda_away_raw = base_each * (
        1.0
        + 0.9 * a_strength
        - 0.5 * h_strength
        - 0.02               # pequeño castigo visitante
    )

    lambda_home_raw = max(0.2, lambda_home_raw)
    lambda_away_raw = max(0.2, lambda_away_raw)

    # Shrinkage Bayesiano contra el prior
    prior_weight = 5.0  # "equivalente" a 5 partidos

    lambda_home_post = (
        lambda_home_raw * h_games + prior_lambda_home * prior_weight
    ) / max(h_games + prior_weight, 1.0)

    lambda_away_post = (
        lambda_away_raw * a_games + prior_lambda_away * prior_weight
    ) / max(a_games + prior_weight, 1.0)

    lambda_home_post = max(0.2, min(3.8, lambda_home_post))
    lambda_away_post = max(0.2, min(3.8, lambda_away_post))

    return {
        "lambda_home": lambda_home_post,
        "lambda_away": lambda_away_post,
    }


def _poisson_score_matrix(lambda_home: float, lambda_away: float, max_goals: int = 10):
    """
    Construye matrices Poisson para goles de home y away, y devuelve:
      - pmf_home[k]
      - pmf_away[k]
      - P(total=g) hasta g=max_goals*2 (con último bucket como cola)
      - P(home>away), P(empate), P(away>home)
    """
    pmf_home = [0.0] * (max_goals + 1)
    pmf_away = [0.0] * (max_goals + 1)

    for k in range(max_goals):
        pmf_home[k] = _poisson_pmf(k, lambda_home)
        pmf_away[k] = _poisson_pmf(k, lambda_away)

    # añadimos cola al último bucket para no perder probabilidad
    pmf_home[max_goals] = max(0.0, 1.0 - sum(pmf_home[:-1]))
    pmf_away[max_goals] = max(0.0, 1.0 - sum(pmf_away[:-1]))

    # matriz conjunta y totales
    max_total = max_goals * 2
    p_total = [0.0] * (max_total + 1)
    p_home_win = 0.0
    p_draw = 0.0
    p_away_win = 0.0

    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p_ij = pmf_home[i] * pmf_away[j]
            total = i + j
            if total > max_total:
                total = max_total
            p_total[total] += p_ij

            if i > j:
                p_home_win += p_ij
            elif i == j:
                p_draw += p_ij
            else:
                p_away_win += p_ij

    # normalización ligera por redondeos
    s1x2 = p_home_win + p_draw + p_away_win
    if s1x2 > 0:
        p_home_win /= s1x2
        p_draw /= s1x2
        p_away_win /= s1x2

    return {
        "p_total": p_total,
        "p_home_win": p_home_win,
        "p_draw": p_draw,
        "p_away_win": p_away_win,
    }


def _ai_adjust_over25_prob(
    prob_poisson_over25: float,
    lambda_home: float,
    lambda_away: float,
    book_over_under: Optional[float],
) -> float:
    """
    Capa tipo 'IA': logistic que ajusta la probabilidad de Over 2.5 combinando
    Poisson con señales sencillas (intensidad total vs línea del book).

    No es una red entrenada, pero imita una corrección de modelo:
      prob_final = 0.7 * prob_poisson + 0.3 * prob_logistic
    """
    total_lambda = lambda_home + lambda_away
    thresh = book_over_under if book_over_under is not None else 2.5

    # Feature: cuánto se separa la intensidad total de la línea clave (2.5 o la del book)
    delta = total_lambda - thresh

    # Logistic centrada en delta=0
    k = 1.6
    prob_logistic = 1.0 / (1.0 + exp(-k * delta))

    prob_final = 0.7 * prob_poisson_over25 + 0.3 * prob_logistic
    return max(0.0, min(1.0, prob_final))


# =========================================================
# 1) Listar torneos configurados
# =========================================================

@router.get("/tournaments")
async def list_soccer_tournaments() -> Dict[str, Any]:
    """
    Devuelve la lista de torneos (ligas) configurados en el backend.
    """
    out: List[Dict[str, Any]] = []

    for alias, code in settings.espn_soccer_leagues.items():
        label = alias.replace("_", " ").title()
        out.append(
            {
                "id": alias,
                "league_code": code,
                "label": label,
                "is_default": code == settings.espn_soccer_default_league,
            }
        )

    return {"tournaments": out}


# =========================================================
# 2) Juegos con odds por torneo
# =========================================================

@router.get("/games-with-odds", response_model=GamesWithOddsResponse)
async def get_soccer_games_with_odds(
    league: Optional[str] = Query(
        None,
        description=(
            "Liga/tornéo de soccer. "
            "Puede ser alias (ej. 'laliga', 'premier_league', 'liga_mx') "
            "o código ESPN (ej. 'esp.1', 'eng.1', 'mex.1'). "
            "Si no se envía, se usa la liga por defecto."
        ),
    )
):
    """
    Lista de juegos de soccer para la liga seleccionada, con odds resumidas.
    """
    scoreboard = fetch_soccer_scoreboard_data(league=league)

    if (
        not scoreboard
        or "events" not in scoreboard
        or not scoreboard["events"]
    ):
        raise HTTPException(
            status_code=404,
            detail="No se encontraron juegos de soccer en el scoreboard para esta liga.",
        )

    games_out: List[GameWithOdds] = []

    for ev in scoreboard.get("events", []):
        try:
            event_id = ev.get("id")
            name = ev.get("name")

            competitions = ev.get("competitions", [])
            comp = competitions[0] if competitions else {}
            competitors = comp.get("competitors", [])

            home_team: Optional[TeamInfo] = None
            away_team: Optional[TeamInfo] = None

            for c in competitors:
                side = c.get("homeAway")
                team = c.get("team", {}) or {}
                t_info = TeamInfo(
                    name=team.get("displayName"),
                    abbr=team.get("abbreviation"),
                )
                if side == "home":
                    home_team = t_info
                elif side == "away":
                    away_team = t_info

            odds_data = fetch_soccer_game_odds(event_id, league=league)
            odds_summary: Optional[GameOddsSummary] = None

            if odds_data and "items" in odds_data and odds_data["items"]:
                item = odds_data["items"][0]
                provider = item.get("provider", {}).get("name", "N/A")
                details = item.get("details", "N/A")
                ou_raw = item.get("overUnder")

                try:
                    over_under = (
                        float(ou_raw) if ou_raw is not None else None
                    )
                except (TypeError, ValueError):
                    over_under = None

                odds_summary = GameOddsSummary(
                    provider=provider,
                    details=details,
                    over_under=over_under,
                )

            games_out.append(
                GameWithOdds(
                    event_id=event_id,
                    matchup=name,
                    home_team=home_team,
                    away_team=away_team,
                    odds=odds_summary,
                )
            )

        except Exception as e:
            print(f"Error procesando juego de soccer con odds: {e}")
            continue

    return GamesWithOddsResponse(
        week=0,
        season_type=0,
        games=games_out,
    )


# =========================================================
# 3) Proyección de partido: Bayes + Poisson + "IA"
# =========================================================

@router.post("/game-projection", response_model=SoccerGameProjection)
async def soccer_game_projection(payload: SoccerGameProjectionRequest):
    """
    Proyección cuantitativa para un partido de soccer:

      - Mercado Over 2.5 goles (probabilidad + edge vs la línea)
      - Mercado 1X2 (probabilidades y pick)
      - Doble oportunidad (1X, X2, 12) usando las probs 1X2

    El modelo combina:
      • Shrinkage Bayesiano contra el promedio de liga y línea del book.
      • Modelo de goles Poisson (matriz de resultados).
      • Ajuste tipo 'IA' (logistic) para calibrar Over 2.5.
    """
    league = payload.league

    scoreboard = fetch_soccer_scoreboard_data(league=league)
    if not scoreboard or "events" not in scoreboard:
        raise HTTPException(
            status_code=404,
            detail="No se encontró scoreboard para la liga solicitada.",
        )

    events = scoreboard.get("events", [])
    ev = next((e for e in events if e.get("id") == payload.event_id), None)
    if not ev:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró el evento {payload.event_id} en esta liga.",
        )

    name = ev.get("name", "Partido Soccer")

    competitions = ev.get("competitions", [])
    comp = competitions[0] if competitions else {}
    competitors = comp.get("competitors", [])

    home_team_info: Optional[TeamInfo] = None
    away_team_info: Optional[TeamInfo] = None
    home_comp_raw: Optional[Dict[str, Any]] = None
    away_comp_raw: Optional[Dict[str, Any]] = None

    for c in competitors:
        side = c.get("homeAway")
        team = c.get("team", {}) or {}
        t_info = TeamInfo(
            name=team.get("displayName"),
            abbr=team.get("abbreviation"),
        )

        if side == "home":
            home_team_info = t_info
            home_comp_raw = c
        elif side == "away":
            away_team_info = t_info
            away_comp_raw = c

    if not home_team_info or not away_team_info or not home_comp_raw or not away_comp_raw:
        raise HTTPException(
            status_code=500,
            detail="No fue posible identificar home/away en el evento de soccer.",
        )

    # Odds (para total de goles)
    odds_data = fetch_soccer_game_odds(payload.event_id, league=league)
    book_over_under: Optional[float] = None

    if odds_data and "items" in odds_data and odds_data["items"]:
        item = odds_data["items"][0]
        ou_raw = item.get("overUnder")
        try:
            book_over_under = float(ou_raw) if ou_raw is not None else None
        except (TypeError, ValueError):
            book_over_under = None

    # 1) Intensidades de gol λ_home, λ_away (Bayes + prior de liga + OU)
    lambdas = _compute_bayesian_lambdas(
        book_over_under=book_over_under,
        home_comp=home_comp_raw,
        away_comp=away_comp_raw,
    )
    lambda_home = lambdas["lambda_home"]
    lambda_away = lambdas["lambda_away"]
    expected_goals = lambda_home + lambda_away

    # 2) Matriz Poisson para totales y 1X2
    mat = _poisson_score_matrix(lambda_home, lambda_away, max_goals=10)
    p_total = mat["p_total"]
    p_home_win = mat["p_home_win"]
    p_draw = mat["p_draw"]
    p_away_win = mat["p_away_win"]

    # Probabilidad Poisson de Over 2.5 (goles >= 3)
    prob_over25_poisson = sum(p_total[g] for g in range(3, len(p_total)))

    # 3) Ajuste tipo "IA" para Over 2.5
    prob_over25 = _ai_adjust_over25_prob(
        prob_poisson_over25=prob_over25_poisson,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        book_over_under=book_over_under,
    )

    # Edge vs línea 2.5 (o la del book si la tienes)
    thresh = book_over_under if book_over_under is not None else 2.5
    edge_pct = ((expected_goals - thresh) / max(thresh, 1.0)) * 100.0

    if prob_over25 >= 0.55:
        over25_pick_label = "OVER 2.5"
    else:
        over25_pick_label = "NO BET"

    over25_conf = _confidence_from_prob(prob_over25)

    over25_pick = SoccerMarketProjection(
        market="OVER_25",
        pick=over25_pick_label,
        confidence=over25_conf,
        prob=prob_over25,
        edge_pct=edge_pct,
        note=(
            "Probabilidad combinada (Poisson + ajuste logístico). "
            "λ_home y λ_away estimados con prior de liga + récord de equipos."
        ),
    )

    # 4) 1X2 con probabilidades Poisson
    probs_1x2 = {"1": p_home_win, "X": p_draw, "2": p_away_win}
    best_outcome = max(probs_1x2, key=probs_1x2.get)
    best_prob = probs_1x2[best_outcome]
    pick1x2_conf = _confidence_from_prob(best_prob)

    pick_1x2 = SoccerMarketProjection(
        market="1X2",
        pick=best_outcome,
        confidence=pick1x2_conf,
        prob=best_prob,
        edge_pct=None,
        note="Probabilidades 1X2 derivadas de la matriz Poisson de goles.",
    )

    # 5) Doble oportunidad
    p_1X = p_home_win + p_draw
    p_X2 = p_draw + p_away_win
    p_12 = p_home_win + p_away_win

    dc_probs = {"1X": p_1X, "X2": p_X2, "12": p_12}
    best_dc = max(dc_probs, key=dc_probs.get)
    best_dc_prob = dc_probs[best_dc]
    dc_conf = _confidence_from_prob(best_dc_prob)

    double_chance_best = SoccerMarketProjection(
        market="DOUBLE_CHANCE",
        pick=best_dc,
        confidence=dc_conf,
        prob=best_dc_prob,
        edge_pct=None,
        note="Doble oportunidad construida a partir de las probabilidades 1X2 Poisson.",
    )

    league_code = settings.espn_soccer_leagues.get(
        payload.league, settings.espn_soccer_default_league
    )

    return SoccerGameProjection(
        event_id=payload.event_id,
        league_code=league_code,
        matchup=name,
        home_team=home_team_info,
        away_team=away_team_info,
        book_over_under=book_over_under,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        expected_goals=expected_goals,
        prob_over25_poisson=prob_over25_poisson,
        prob_1=p_home_win,
        prob_X=p_draw,
        prob_2=p_away_win,
        over25_pick=over25_pick,
        pick_1x2=pick_1x2,
        double_chance_best=double_chance_best,
    )
