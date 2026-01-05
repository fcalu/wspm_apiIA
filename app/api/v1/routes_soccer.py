# app/api/v1/routes_soccer.py

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
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

router = APIRouter(
    prefix="/soccer",
    tags=["soccer"],
)


# ---------------------------------------------------------
# 1) Listar torneos disponibles (para el frontend)
# ---------------------------------------------------------
@router.get("/tournaments")
async def list_soccer_tournaments() -> Dict[str, Any]:
    """
    Devuelve la lista de torneos (ligas) configurados en el backend.

    Esto sirve para que el frontend pinte un combo:
      - id (alias interno)
      - league_code (código ESPN)
      - label (para mostrar)
      - is_default (la liga que se usa si no mandas nada)
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


# ---------------------------------------------------------
# 2) Juegos con odds por torneo
# ---------------------------------------------------------
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

    Ejemplos de uso desde el frontend:
      - /api/v1/soccer/games-with-odds              -> usa default (ej. Premier)
      - /api/v1/soccer/games-with-odds?league=laliga
      - /api/v1/soccer/games-with-odds?league=esp.1
      - /api/v1/soccer/games-with-odds?league=liga_mx
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
            # No rompemos toda la respuesta por un partido
            print(f"Error procesando juego de soccer con odds: {e}")
            continue

    return GamesWithOddsResponse(
        week=0,        # no aplica a soccer, pero reutilizamos el schema
        season_type=0, # idem
        games=games_out,
    )
