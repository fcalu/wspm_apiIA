# app/api/v1/routes_soccer.py

from typing import Any, Dict, List, Optional
from math import exp

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
# Modelos para proyección de partido
# =========================================================


class SoccerGameProjectionRequest(BaseModel):
    """
    Request para proyección de un partido de soccer.

    Flujo típico:
      1) Llamas a /soccer/games-with-odds?league=laliga
      2) Tomas un event_id de la respuesta
      3) Llamas a /soccer/game-projection con ese event_id y la misma liga
    """
    event_id: str
    league: Optional[str] = None


class SoccerMarketProjection(BaseModel):
    market: str               # "OVER_25", "1X2", "DOUBLE_CHANCE"
    pick: str                 # ej: "OVER 2.5", "1", "X", "2", "1X", "X2", "12", "NO BET"
    confidence: str           # "Alta" | "Media-Alta" | "Media" | "Baja"
    prob: float               # probabilidad estimada (0-1)
    edge_pct: Optional[float] = None  # opcional, solo se usa en Over 2.5
    note: Optional[str] = None


class SoccerGameProjection(BaseModel):
    event_id: str
    league_code: str

    matchup: str
    home_team: TeamInfo
    away_team: TeamInfo

    # Línea del book (total goles) si existe
    book_over_under: Optional[float]

    # Modelo interno
    expected_goals: float
    prob_over25: float

    # Probabilidades 1X2
    prob_1: float
    prob_X: float
    prob_2: float

    # Picks de alto nivel
    over25_pick: SoccerMarketProjection
    pick_1x2: SoccerMarketProjection
    double_chance_best: SoccerMarketProjection


# =========================================================
# Helpers internos (modelo heurístico simple)
# =========================================================


def _confidence_from_prob(p: float) -> str:
    if p >= 0.70:
        return "Alta"
    elif p >= 0.60:
        return "Media-Alta"
    elif p >= 0.55:
        return "Media"
    else:
        return "Baja"


def _parse_points_per_game(competitor: Dict[str, Any]) -> float:
    """
    Intenta estimar fuerza del equipo a partir de su record tipo '10-5-3'.

    Retorna puntos por partido en escala 0..1 aprox.
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
        # fallback neutro
        return 0.5

    try:
        parts = summary_str.replace(" ", "").split("-")
        if len(parts) < 2:
            return 0.5
        w = int(parts[0])
        l = int(parts[1])
        d = int(parts[2]) if len(parts) >= 3 else 0
        games = w + l + d
        if games <= 0:
            return 0.5

        pts = 3 * w + d
        ppg = pts / (3.0 * games)  # 0..1
        return max(0.2, min(0.95, ppg))
    except Exception:
        return 0.5


def _compute_1x2_probs(home_comp: Dict[str, Any], away_comp: Dict[str, Any]) -> Dict[str, float]:
    """
    Genera probabilidades 1X2 en base a 'fuerza' de equipos + pequeña ventaja local.
    """
    home_strength = _parse_points_per_game(home_comp)
    away_strength = _parse_points_per_game(away_comp)

    # ventaja local moderada
    home_strength += 0.05
    delta = home_strength - away_strength  # positivo => local favorito

    # logistic around 0.5
    scale = 3.0
    p_home_raw = 1.0 / (1.0 + exp(-scale * delta))  # 0..1
    p_away_raw = 1.0 - p_home_raw

    # prob de empate base, ajustada por lo cerrado del partido
    draw_raw = max(0.15, 0.30 - 0.10 * abs(delta))

    remaining = 1.0 - draw_raw
    p_home = p_home_raw * remaining
    p_away = p_away_raw * remaining

    # normalizamos a 1
    s = p_home + draw_raw + p_away
    p_home /= s
    draw = draw_raw / s
    p_away /= s

    return {
        "1": p_home,
        "X": draw,
        "2": p_away,
    }


def _compute_expected_goals(
    book_over_under: Optional[float],
    home_comp: Dict[str, Any],
    away_comp: Dict[str, Any],
) -> float:
    """
    Estimación muy simple de goles esperados:
      - se parte de la línea del book si existe
      - se ajusta un poco según la diferencia de 'fuerza'
    """
    base = book_over_under if book_over_under is not None else 2.5

    home_strength = _parse_points_per_game(home_comp)
    away_strength = _parse_points_per_game(away_comp)
    delta = home_strength - away_strength

    # partidos desbalanceados suelen tener más goles
    adjust = 0.6 * abs(delta)  # 0..~0.45

    expected = base + adjust
    return max(1.5, min(4.5, expected))


# =========================================================
# 1) Listar torneos
# ==========================================================


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
# ==========================================================


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
# 3) Proyección de partido (Over 2.5, 1X2, Doble Oportunidad)
# ==========================================================
@router.post("/game-projection", response_model=SoccerGameProjection)
async def soccer_game_projection(payload: SoccerGameProjectionRequest):
    """
    Proyección simple para:
      - Mercado Over 2.5 goles
      - Mercado 1X2
      - Doble oportunidad (1X, X2, 12)

    Usa:
      - event_id del partido
      - la liga (alias o código). Si no se manda, se usa la liga por defecto.
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

    # ============================
    # Modelo de goles / Over 2.5
    # ============================
    expected_goals = _compute_expected_goals(
        book_over_under=book_over_under,
        home_comp=home_comp_raw,
        away_comp=away_comp_raw,
    )

    # probabilidad "suave" de Over 2.5
    line_25 = 2.5
    k = 1.1
    prob_over25 = 1.0 / (1.0 + exp(-k * (expected_goals - line_25)))

    # edge aproximado vs 2.5
    edge_over25_pct = ((expected_goals - line_25) / max(line_25, 1.0)) * 100.0

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
        edge_pct=edge_over25_pct,
        note="Modelo heurístico basado en línea del book + diferencia de fuerzas.",
    )

    # ============================
    # Modelo 1X2
    # ============================
    probs_1x2 = _compute_1x2_probs(
        home_comp=home_comp_raw,
        away_comp=away_comp_raw,
    )
    p1 = probs_1x2["1"]
    pX = probs_1x2["X"]
    p2 = probs_1x2["2"]

    # Mejor pick 1X2
    best_outcome = max(probs_1x2, key=probs_1x2.get)
    best_prob = probs_1x2[best_outcome]
    pick1x2_conf = _confidence_from_prob(best_prob)

    pick_1x2 = SoccerMarketProjection(
        market="1X2",
        pick=best_outcome,
        confidence=pick1x2_conf,
        prob=best_prob,
        edge_pct=None,
        note="Probabilidades 1X2 derivadas de rendimiento histórico (records).",
    )

    # ============================
    # Doble oportunidad
    # ============================
    p_1X = p1 + pX
    p_X2 = pX + p2
    p_12 = p1 + p2

    dc_probs = {
        "1X": p_1X,
        "X2": p_X2,
        "12": p_12,
    }
    best_dc = max(dc_probs, key=dc_probs.get)
    best_dc_prob = dc_probs[best_dc]
    dc_conf = _confidence_from_prob(best_dc_prob)

    double_chance_best = SoccerMarketProjection(
        market="DOUBLE_CHANCE",
        pick=best_dc,
        confidence=dc_conf,
        prob=best_dc_prob,
        edge_pct=None,
        note="Combinación de probabilidades 1X2 (doble oportunidad).",
    )

    # ============================
    # Respuesta
    # ============================
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
        expected_goals=expected_goals,
        prob_over25=prob_over25,
        prob_1=p1,
        prob_X=pX,
        prob_2=p2,
        over25_pick=over25_pick,
        pick_1x2=pick_1x2,
        double_chance_best=double_chance_best,
    )
