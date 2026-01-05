# app/api/v1/routes_soccer.py

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from app.services.espn_soccer_client import (
    fetch_soccer_scoreboard_data,
    fetch_soccer_game_odds,
)
from app.schemas.nfl import (
    TeamInfo,
    GameWithOdds,
    GamesWithOddsResponse,
    GameOddsSummary,
)
from app.schemas.soccer import (
    SoccerGameProjectionRequest,
    SoccerGameProjectionOutput,
)
from app.services.soccer_game_projection import compute_soccer_game_projection


router = APIRouter(
    prefix="/soccer",
    tags=["soccer"],
)


# ---------------------------------------------------------------------
# 1) LISTA DE JUEGOS CON ODDS (YA EXISTÍA)
# ---------------------------------------------------------------------
@router.get("/games-with-odds", response_model=GamesWithOddsResponse)
async def get_soccer_games_with_odds() -> GamesWithOddsResponse:
    """
    Lista de juegos de la liga de soccer configurada (ej. Premier League) con odds resumidas.
    """
    scoreboard = fetch_soccer_scoreboard_data()

    if not scoreboard or "events" not in scoreboard or not scoreboard["events"]:
        raise HTTPException(
            status_code=404,
            detail="No se encontraron juegos de soccer en el scoreboard actual.",
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
                team: Dict[str, Any] = c.get("team") or {}
                t_info = TeamInfo(
                    name=team.get("displayName"),
                    abbr=team.get("abbreviation"),
                )
                if side == "home":
                    home_team = t_info
                elif side == "away":
                    away_team = t_info

            odds_data = fetch_soccer_game_odds(str(event_id))
            odds_summary: Optional[GameOddsSummary] = None

            if odds_data and "items" in odds_data and odds_data["items"]:
                item = odds_data["items"][0]
                provider = item.get("provider", {}).get("name", "N/A")
                details = item.get("details", "N/A")
                ou_raw = item.get("overUnder")

                try:
                    over_under = float(ou_raw) if ou_raw is not None else None
                except (TypeError, ValueError):
                    over_under = None

                odds_summary = GameOddsSummary(
                    provider=provider,
                    details=details,
                    over_under=over_under,
                )

            games_out.append(
                GameWithOdds(
                    event_id=str(event_id),
                    matchup=name,
                    home_team=home_team,
                    away_team=away_team,
                    odds=odds_summary,
                )
            )

        except Exception as e:
            print(f"[SOCCER][games-with-odds] Error procesando juego: {e}")
            continue

    return GamesWithOddsResponse(
        week=0,
        season_type=0,
        games=games_out,
    )


# ---------------------------------------------------------------------
# 2) WQM SOCCER – REPORTE DE PREDICCIÓN POR JUEGO
# ---------------------------------------------------------------------
@router.post(
    "/game-projection-report",
    response_model=SoccerGameProjectionOutput,
)
async def soccer_game_projection_report(
    payload: SoccerGameProjectionRequest,
) -> SoccerGameProjectionOutput:
    """
    Genera predicciones WQM para un partido de soccer:

    - Over/Under 2.5 goles
    - Ambos Anotan (BTTS)
    - 1X2 (1, X, 2)
    - Doble oportunidad (1X, X2 o 12)
    """
    scoreboard = fetch_soccer_scoreboard_data()
    if not scoreboard or "events" not in scoreboard or not scoreboard["events"]:
        raise HTTPException(
            status_code=502,
            detail="No se pudo obtener el scoreboard de soccer.",
        )

    events = scoreboard.get("events", [])
    ev: Optional[Dict[str, Any]] = next(
        (e for e in events if str(e.get("id")) == payload.event_id), None
    )

    if not ev:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró el evento {payload.event_id} en el scoreboard de soccer.",
        )

    odds_data = fetch_soccer_game_odds(payload.event_id)
    if not odds_data or "items" not in odds_data or not odds_data["items"]:
        raise HTTPException(
            status_code=404,
            detail=f"No hay odds disponibles para el evento {payload.event_id}.",
        )

    odds_item = odds_data["items"][0]

    result_dict = compute_soccer_game_projection(
        ev,
        odds_item,
        line_over25=payload.line_over25,
    )

    return SoccerGameProjectionOutput(**result_dict)
