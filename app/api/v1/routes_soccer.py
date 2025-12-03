from fastapi import APIRouter, HTTPException

from app.services.espn_soccer_client import fetch_soccer_scoreboard_data, fetch_soccer_game_odds
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


@router.get("/games-with-odds", response_model=GamesWithOddsResponse)
async def get_soccer_games_with_odds():
    """
    Lista de juegos de la liga de soccer configurada (ej. Premier League) con odds resumidas.
    """
    scoreboard = fetch_soccer_scoreboard_data()

    if not scoreboard or "events" not in scoreboard or not scoreboard["events"]:
        raise HTTPException(
            status_code=404,
            detail="No se encontraron juegos de soccer en el scoreboard actual.",
        )

    games_out = []

    for ev in scoreboard.get("events", []):
        try:
            event_id = ev.get("id")
            name = ev.get("name")

            competitions = ev.get("competitions", [])
            comp = competitions[0] if competitions else {}
            competitors = comp.get("competitors", [])

            home_team = None
            away_team = None

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

            odds_data = fetch_soccer_game_odds(event_id)
            odds_summary = None

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
