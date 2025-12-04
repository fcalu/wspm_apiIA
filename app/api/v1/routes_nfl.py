from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.espn_nfl_client import fetch_scoreboard_data, fetch_game_odds
from app.services.espn_nfl_players_client import fetch_player_gamelog
from app.services.espn_nfl_roster_client import fetch_team_roster_by_abbr
from app.services.espn_nfl_teams_client import fetch_nfl_teams_simplified
from app.services.wspm_nfl_engine import compute_base_projection_from_gamelog

from app.schemas.nfl import (
    ScoreboardResponse,
    ScoreboardEvent,
    TeamInfo,
    OddsResponse,
    OddsBook,
    WSPMInput,
    WSPMOutput,
    WSPMAutoRequest,
    GameWithOdds,
    GamesWithOddsResponse,
    GameOddsSummary,
    NFLTeamsResponse,
    WSPMFullReport,
    WSPMVariableBreakdown,
)

router = APIRouter(
    prefix="/nfl",
    tags=["nfl"],
)


# ---------------------------------------------------------------------------
# 1) SCOREBOARD (JUEGOS POR SEMANA)
# ---------------------------------------------------------------------------

@router.get("/scoreboard", response_model=ScoreboardResponse)
async def get_nfl_scoreboard(
    week: int = Query(..., description="Semana de NFL, ej. 1 o 15", ge=1),
    season_type: int = Query(
        2,
        description="Tipo de temporada: 1=Pre, 2=Regular, 3=Post",
        ge=1,
        le=3,
    ),
):
    data = fetch_scoreboard_data(week, season_type)

    if not data or "events" not in data or not data["events"]:
        raise HTTPException(
            status_code=404,
            detail="No se encontraron eventos para esa semana/tipo de temporada.",
        )

    events_out: List[ScoreboardEvent] = []

    for ev in data.get("events", []):
        try:
            event_id = ev.get("id")
            name = ev.get("name")

            competitions = ev.get("competitions", [])
            comp = competitions[0] if competitions else {}
            competitors = comp.get("competitors", [])

            home_team: Optional[TeamInfo] = None
            away_team: Optional[TeamInfo] = None

            for c in competitors:
                side = c.get("homeAway")  # 'home' o 'away'
                team = c.get("team", {}) or {}
                t_info = TeamInfo(
                    name=team.get("displayName"),
                    abbr=team.get("abbreviation"),
                )
                if side == "home":
                    home_team = t_info
                elif side == "away":
                    away_team = t_info

            events_out.append(
                ScoreboardEvent(
                    event_id=event_id,
                    matchup=name,
                    home_team=home_team,
                    away_team=away_team,
                )
            )
        except Exception as e:
            print(f"Error parseando evento NFL: {e}")
            continue

    return ScoreboardResponse(
        week=week,
        season_type=season_type,
        events=events_out,
    )


# ---------------------------------------------------------------------------
# 2) ODDS POR PARTIDO
# ---------------------------------------------------------------------------

@router.get("/odds/{event_id}", response_model=OddsResponse)
async def get_nfl_odds(event_id: str):
    odds_data = fetch_game_odds(event_id)

    if not odds_data or "items" not in odds_data or not odds_data["items"]:
        raise HTTPException(
            status_code=404,
            detail="No se encontraron odds para ese Event ID.",
        )

    books_out: List[OddsBook] = []

    for item in odds_data["items"]:
        provider = item.get("provider", {}).get("name", "N/A")
        details = item.get("details", "N/A")
        ou_raw = item.get("overUnder")

        try:
            over_under = float(ou_raw) if ou_raw is not None else None
        except (TypeError, ValueError):
            over_under = None

        books_out.append(
            OddsBook(
                provider=provider,
                details=details,
                over_under=over_under,
            )
        )

    return OddsResponse(
        event_id=event_id,
        books=books_out,
        raw_count=len(books_out),
    )


# ---------------------------------------------------------------------------
# 3) WSPM MANUAL (USUARIO ENVÍA BASE_PROJECTION Y AJUSTES)
# ---------------------------------------------------------------------------

@router.post("/wspm/projection", response_model=WSPMOutput)
async def wspm_projection(input_data: WSPMInput):
    net_adjust = (
        input_data.adj_matchup
        + input_data.adj_volume
        + input_data.adj_risk
        + input_data.adj_tempo
    )

    if input_data.model_projection is not None:
        wspm_projection = input_data.model_projection
    else:
        wspm_projection = input_data.base_projection + net_adjust

    edge = wspm_projection - input_data.book_line

    if input_data.book_line != 0:
        margin_pct = (edge / abs(input_data.book_line)) * 100.0
    else:
        margin_pct = 0.0

    safety_margin_value = abs(edge)
    safety_margin_pct = abs(margin_pct)

    abs_m = safety_margin_pct
    if abs_m < 2:
        prob_cover = 52.0
    elif abs_m < 5:
        prob_cover = 55.0
    elif abs_m < 10:
        prob_cover = 60.0
    elif abs_m < 15:
        prob_cover = 65.0
    else:
        prob_cover = 70.0

    direction = "OVER" if edge > 0 else "UNDER"

    if safety_margin_pct >= 15:
        confidence = "Alta"
    elif safety_margin_pct >= 10:
        confidence = "Media-Alta"
    elif safety_margin_pct >= 5:
        confidence = "Media"
    else:
        confidence = "Baja"

    return WSPMOutput(
        event_id=input_data.event_id,
        player_name=input_data.player_name,
        player_team=input_data.player_team,
        opponent_team=input_data.opponent_team,
        position=input_data.position,
        market_type=input_data.market_type,
        book_line=input_data.book_line,
        base_projection=input_data.base_projection,
        adj_matchup=input_data.adj_matchup,
        adj_volume=input_data.adj_volume,
        adj_risk=input_data.adj_risk,
        adj_tempo=input_data.adj_tempo,
        net_adjust=net_adjust,
        wspm_projection=wspm_projection,
        edge=edge,
        margin_pct=margin_pct,
        safety_margin_value=safety_margin_value,
        safety_margin_pct=safety_margin_pct,
        prob_cover=prob_cover,
        direction=direction,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# 4) WSPM AUTO (USA GAMELOG + ODDS, DEVUELVE SALIDA NUMÉRICA)
# ---------------------------------------------------------------------------

@router.post("/wspm/auto-projection", response_model=WSPMOutput)
async def wspm_auto_projection(payload: WSPMAutoRequest):
    scoreboard = fetch_scoreboard_data(payload.week, payload.season_type)
    if not scoreboard or "events" not in scoreboard:
        raise HTTPException(
            status_code=502,
            detail="No se pudo obtener el scoreboard desde ESPN.",
        )

    event = next((e for e in scoreboard["events"] if e.get("id") == payload.event_id), None)
    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró el evento {payload.event_id} en el scoreboard.",
        )

    odds_data = fetch_game_odds(payload.event_id)
    game_total: Optional[float] = None
    if odds_data and "items" in odds_data and odds_data["items"]:
        first_item = odds_data["items"][0]
        ou_raw = first_item.get("overUnder")
        try:
            game_total = float(ou_raw) if ou_raw is not None else None
        except (TypeError, ValueError):
            game_total = None

    gamelog = fetch_player_gamelog(
        payload.athlete_id,
        season=payload.season,
        season_type=payload.season_type,
    )

    base_projection = compute_base_projection_from_gamelog(
        gamelog=gamelog,
        market_type=payload.market_type,
        games_window=5,
    )

    # 👇 Protegemos contra casos donde no hay datos suficientes.
    if base_projection <= 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "No se pudo calcular una base_projection confiable para este jugador/mercado "
                "(muy pocos juegos o stats no disponibles). Usa modo manual /wspm/projection "
                "o ajusta la función compute_base_projection_from_gamelog."
            ),
        )

    if game_total is not None and game_total >= 50:
        adj_tempo = 3.0
    elif game_total is not None and game_total >= 46:
        adj_tempo = 1.0
    else:
        adj_tempo = 0.0

    adj_matchup = 0.0
    adj_volume = 0.0
    adj_risk = 0.0

    net_adjust = adj_matchup + adj_volume + adj_risk + adj_tempo
    wspm_projection = base_projection + net_adjust

    book_line = payload.book_line
    edge = wspm_projection - book_line

    if book_line != 0:
        margin_pct = (edge / abs(book_line)) * 100.0
    else:
        margin_pct = 0.0

    safety_margin_value = abs(edge)
    safety_margin_pct = abs(margin_pct)

    if safety_margin_pct < 2:
        prob_cover = 52.0
    elif safety_margin_pct < 5:
        prob_cover = 55.0
    elif safety_margin_pct < 10:
        prob_cover = 60.0
    elif safety_margin_pct < 15:
        prob_cover = 65.0
    else:
        prob_cover = 70.0

    direction = "OVER" if edge > 0 else "UNDER"

    if safety_margin_pct >= 15:
        confidence = "Alta"
    elif safety_margin_pct >= 10:
        confidence = "Media-Alta"
    elif safety_margin_pct >= 5:
        confidence = "Media"
    else:
        confidence = "Baja"

    return WSPMOutput(
        event_id=payload.event_id,
        player_name=payload.player_name,
        player_team=payload.player_team,
        opponent_team=payload.opponent_team,
        position=payload.position,
        market_type=payload.market_type,
        book_line=book_line,
        base_projection=base_projection,
        adj_matchup=adj_matchup,
        adj_volume=adj_volume,
        adj_risk=adj_risk,
        adj_tempo=adj_tempo,
        net_adjust=net_adjust,
        wspm_projection=wspm_projection,
        edge=edge,
        margin_pct=margin_pct,
        safety_margin_value=safety_margin_value,
        safety_margin_pct=safety_margin_pct,
        prob_cover=prob_cover,
        direction=direction,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# 5) WSPM AUTO REPORT (VERSIÓN "VENDIBLE" CON TEXTO FORMATEADO)
# ---------------------------------------------------------------------------

@router.post("/wspm/auto-projection-report", response_model=WSPMFullReport)
async def wspm_auto_projection_report(payload: WSPMAutoRequest):
    scoreboard = fetch_scoreboard_data(payload.week, payload.season_type)
    if not scoreboard or "events" not in scoreboard:
        raise HTTPException(
            status_code=502,
            detail="No se pudo obtener el scoreboard desde ESPN.",
        )

    event = next((e for e in scoreboard["events"] if e.get("id") == payload.event_id), None)
    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró el evento {payload.event_id} en el scoreboard.",
        )

    matchup = event.get("name", f"{payload.player_team} vs {payload.opponent_team}")

    odds_data = fetch_game_odds(payload.event_id)
    game_total: Optional[float] = None
    if odds_data and "items" in odds_data and odds_data["items"]:
        first_item = odds_data["items"][0]
        ou_raw = first_item.get("overUnder")
        try:
            game_total = float(ou_raw) if ou_raw is not None else None
        except (TypeError, ValueError):
            game_total = None

    gamelog = fetch_player_gamelog(
        payload.athlete_id,
        season=payload.season,
        season_type=payload.season_type,
    )

    base_projection = compute_base_projection_from_gamelog(
        gamelog=gamelog,
        market_type=payload.market_type,
        games_window=5,
    )

    if base_projection <= 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "No se pudo calcular una base_projection confiable para este jugador/mercado "
                "en el reporte. Revisa el gamelog o ajusta la lógica de extracción de stats."
            ),
        )

    if game_total is not None and game_total >= 50:
        adj_tempo = 3.0
    elif game_total is not None and game_total >= 46:
        adj_tempo = 1.0
    else:
        adj_tempo = 0.0

    adj_matchup = 0.0
    adj_volume = 0.0
    adj_risk = 0.0

    net_adjust = adj_matchup + adj_volume + adj_risk + adj_tempo
    wspm_projection = base_projection + net_adjust

    book_line = payload.book_line
    edge = wspm_projection - book_line

    if book_line != 0:
        margin_pct = (edge / abs(book_line)) * 100.0
    else:
        margin_pct = 0.0

    safety_margin_value = abs(edge)
    safety_margin_pct = abs(margin_pct)

    if safety_margin_pct < 2:
        prob_cover = 52.0
    elif safety_margin_pct < 5:
        prob_cover = 55.0
    elif safety_margin_pct < 10:
        prob_cover = 60.0
    elif safety_margin_pct < 15:
        prob_cover = 65.0
    else:
        prob_cover = 70.0

    direction = "OVER" if edge > 0 else "UNDER"

    if safety_margin_pct >= 15:
        confidence = "Alta"
    elif safety_margin_pct >= 10:
        confidence = "Media-Alta"
    elif safety_margin_pct >= 5:
        confidence = "Media"
    else:
        confidence = "Baja"

    variables = [
        WSPMVariableBreakdown(
            name="Matchup Defensivo Avanzado (DVOA/YAC)",
            description=(
                "Ajuste según la calidad de la defensa rival vs el tipo de mercado "
                "(pase terrestre/aéreo). Actualmente simplificado; se puede mejorar "
                "con DVOA/YAC reales."
            ),
            weight=adj_matchup,
        ),
        WSPMVariableBreakdown(
            name="Volumen de Juego Proyectado (Targets/Carries/Pases)",
            description=(
                "Proyección de uso basada en el gamelog reciente (targets/carries) "
                "y rol en el esquema ofensivo."
            ),
            weight=adj_volume,
        ),
        WSPMVariableBreakdown(
            name="Riesgo / Reversión de Margen",
            description=(
                "Factor de riesgo por volatilidad, script de partido, lesiones o posible "
                "regresión a la media."
            ),
            weight=adj_risk,
        ),
        WSPMVariableBreakdown(
            name="Game Flow (Ritmo Proyectado / Tempo)",
            description=(
                "Impacto del total del partido y ritmo esperado. Totales altos suelen "
                "favorecer OVER en mercados de producción ofensiva."
            ),
            weight=adj_tempo,
        ),
    ]

    ajuste_neto_str = f"{net_adjust:.1f}"
    margen_seguridad_str = f"{safety_margin_value:.1f}"
    prob_str = f"{prob_cover:.1f}%"

    line_str = f"{book_line:.1f}"
    proj_str = f"{wspm_projection:.1f}"
    market_label = payload.market_type.replace("_", " ")

    pick_str = f"{direction} {line_str}"

    markdown_report = f"""### 📈 Proyección del Modelo WSPM

*Partido:* {matchup}
*Jugador:* {payload.player_name}  
*Posición:* {payload.position}  
*Línea del book (Proyección O/U):* {line_str} {market_label}  
*Proyección del modelo WSPM:* {proj_str} {market_label}  
*Pick del modelo WSPM:* {pick_str}

#### ⚖️ Ponderación de Variables Clave (vs Línea Base):

* **Variable 1: Matchup Defensivo Avanzado (DVOA/YAC)**  
  - *Ponderación:* {adj_matchup:+.1f} unidades

* **Variable 2: Volumen de Juego Proyectado (Targets/Carries/Pases)**  
  - *Ponderación:* {adj_volume:+.1f} unidades

* **Variable 3: Riesgo/Reversión de Margen**  
  - *Ponderación:* {adj_risk:+.1f} unidades

* **Variable 4: Game Flow (Ritmo Proyectado/Tempo)**  
  - *Ponderación:* {adj_tempo:+.1f} unidades

#### 🎯 Análisis y Justificación:

El modelo parte de una proyección base de **{base_projection:.1f}** basada en el rendimiento reciente del jugador
(gamelog de ESPN). Sobre esa base se aplican ajustes por matchup, volumen esperado, riesgo y ritmo de partido, para
un **Ajuste Neto Total de {ajuste_neto_str}** unidades, resultando en una proyección final WSPM de **{proj_str}**.

El margen de seguridad respecto a la línea del book es de **{margen_seguridad_str}** unidades
({safety_margin_pct:.1f}%), con una probabilidad estimada de cubrir la línea de **{prob_str}**.

#### 💡 Conclusión:

*Dirección Esperada (Valor WSPM):* **{direction}**  
*Confianza del Pick (Rigurosa):* **{confidence}**
"""

    return WSPMFullReport(
        event_id=payload.event_id,
        matchup=matchup,
        player_name=payload.player_name,
        player_team=payload.player_team,
        opponent_team=payload.opponent_team,
        position=payload.position,
        market_type=payload.market_type,
        book_line=book_line,
        wspm_projection=wspm_projection,
        pick=pick_str,
        base_projection=base_projection,
        adj_matchup=adj_matchup,
        adj_volume=adj_volume,
        adj_risk=adj_risk,
        adj_tempo=adj_tempo,
        net_adjust=net_adjust,
        edge=edge,
        margin_pct=margin_pct,
        safety_margin_value=safety_margin_value,
        safety_margin_pct=safety_margin_pct,
        prob_cover=prob_cover,
        confidence=confidence,
        game_total=game_total,
        variables=variables,
        markdown_report=markdown_report,
    )


# ---------------------------------------------------------------------------
# 6) GAMELOG CRUDO DE UN JUGADOR
# ---------------------------------------------------------------------------

@router.get("/player/{athlete_id}/gamelog")
async def get_nfl_player_gamelog(
    athlete_id: str,
    season: int = Query(..., description="Temporada NFL, ej. 2024"),
    season_type: int = Query(
        2,
        description="Tipo de temporada: 1=Pre, 2=Regular, 3=Post",
        ge=1,
        le=3,
    ),
) -> Dict[str, Any]:
    data = fetch_player_gamelog(athlete_id, season=season, season_type=season_type)

    if not data:
        raise HTTPException(
            status_code=502,
            detail="No se pudo obtener el gamelog del jugador desde ESPN.",
        )

    return data


# ---------------------------------------------------------------------------
# 7) LISTA DE JUEGOS CON UNA ODDS RESUMIDA (PARA FRONTEND)
# ---------------------------------------------------------------------------

@router.get("/games-with-odds", response_model=GamesWithOddsResponse)
async def get_nfl_games_with_odds(
    week: int = Query(..., description="Semana de NFL, ej. 1 o 15", ge=1),
    season_type: int = Query(
        2,
        description="Tipo de temporada: 1=Pre, 2=Regular, 3=Post",
        ge=1,
        le=3,
    ),
):
    scoreboard = fetch_scoreboard_data(week, season_type)

    if not scoreboard or "events" not in scoreboard or not scoreboard["events"]:
        raise HTTPException(
            status_code=404,
            detail="No se encontraron eventos para esa semana/tipo de temporada.",
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
                side = c.get("homeAway")  # 'home' o 'away'
                team = c.get("team", {}) or {}
                t_info = TeamInfo(
                    name=team.get("displayName"),
                    abbr=team.get("abbreviation"),
                )
                if side == "home":
                    home_team = t_info
                elif side == "away":
                    away_team = t_info

            odds_data = fetch_game_odds(event_id)

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
                    event_id=event_id,
                    matchup=name,
                    home_team=home_team,
                    away_team=away_team,
                    odds=odds_summary,
                )
            )

        except Exception as e:
            print(f"Error procesando juego con odds: {e}")
            continue

    return GamesWithOddsResponse(
        week=week,
        season_type=season_type,
        games=games_out,
    )


# ---------------------------------------------------------------------------
# 8) ROSTER POR EQUIPO (ABREVIATURA → JUGADORES ESPN)
# ---------------------------------------------------------------------------

@router.get("/team/{team_abbr}/roster")
async def get_team_roster(team_abbr: str) -> Dict[str, Any]:
    roster = fetch_team_roster_by_abbr(team_abbr)
    if not roster:
        raise HTTPException(
            status_code=502,
            detail=(
                f"No se pudo obtener el roster para el equipo {team_abbr}. "
                "Verifica que la abreviatura esté soportada por ESPN."
            ),
        )
    return roster


# ---------------------------------------------------------------------------
# 9) CATÁLOGO DE EQUIPOS NFL (PARA FRONTEND)
# ---------------------------------------------------------------------------

@router.get("/teams", response_model=NFLTeamsResponse)
async def get_nfl_teams():
    teams_data = fetch_nfl_teams_simplified()

    if not teams_data:
        raise HTTPException(
            status_code=502,
            detail="No se pudieron obtener los equipos NFL desde ESPN.",
        )

    return NFLTeamsResponse(
        count=len(teams_data),
        teams=teams_data,
    )
