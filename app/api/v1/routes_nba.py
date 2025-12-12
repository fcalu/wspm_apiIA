# app/api/v1/routes_nba.py

from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.services.espn_nba_client import (
    fetch_nba_scoreboard,
    fetch_nba_game_odds,
    fetch_nba_team_with_roster,
)
from app.services.espn_nba_players_client import fetch_nba_player_gamelog
from app.services.espn_nba_roster_client import fetch_nba_team_roster_by_abbr
from app.services.wspm_nba_engine import compute_base_projection_from_gamelog

# Reutilizamos schemas genéricos ya existentes (como hiciste en NFL)
from app.schemas.nfl import (
    TeamInfo,
    GameWithOdds,
    GamesWithOddsResponse,
    GameOddsSummary,
    WSPMAutoRequest,
    WSPMOutput,
    WSPMFullReport,
    WSPMVariableBreakdown,
)

router = APIRouter(
    prefix="/nba",
    tags=["nba"],
)


# -----------------------------------------------------------------------------
# 1) GAMES WITH ODDS (LISTA DE JUEGOS + TOTAL DEL BOOK)
# -----------------------------------------------------------------------------
@router.get("/games-with-odds", response_model=GamesWithOddsResponse)
async def get_nba_games_with_odds(
    date: str = Query(
        ...,
        description="Fecha en formato YYYYMMDD (ej. 20251209)",
        min_length=8,
        max_length=8,
        pattern=r"^\d{8}$",
    ),
):
    """
    Devuelve lista de juegos NBA para una fecha específica con un resumen simple
    de odds (primer proveedor disponible).

    Nota:
    - Reutiliza el schema de NFL, por eso week/season_type se devuelven en 0.
    """
    date = date.strip()

    sb = fetch_nba_scoreboard(date)
    if not sb:
        raise HTTPException(
            status_code=502,
            detail="No se pudo obtener el scoreboard NBA desde ESPN. Verifica date=YYYYMMDD.",
        )

    events = sb.get("events", [])
    if not events:
        raise HTTPException(
            status_code=404,
            detail="No hay eventos NBA para esa fecha.",
        )

    games_out: List[GameWithOdds] = []

    for ev in events:
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

            odds_raw = fetch_nba_game_odds(str(event_id))
            odds_summary: Optional[GameOddsSummary] = None

            if odds_raw and "items" in odds_raw and odds_raw["items"]:
                item = odds_raw["items"][0]
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
            print(f"[NBA] Error procesando juego: {e}")
            continue

    return GamesWithOddsResponse(
        week=0,
        season_type=0,
        games=games_out,
    )


# -----------------------------------------------------------------------------
# 2) ROSTER POR EQUIPO
# -----------------------------------------------------------------------------
@router.get("/team/{team_abbr}/roster")
async def get_nba_team_roster(team_abbr: str) -> Dict[str, Any]:
    """
    Devuelve el roster NBA de un equipo (abreviatura, ej: LAL, BOS, DAL).

    Respuesta:
    {
      "team_abbr": "LAL",
      "team_name": "Los Angeles Lakers",
      "players": [
        {
          "athlete_id": "3032977",
          "name": "LeBron James",
          "position": "SF",
          "jersey": "23",
          "depth": null,
          "team_abbr": "LAL"
        },
        ...
      ]
    }
    """
    team_abbr = team_abbr.upper()

    data = fetch_nba_team_with_roster(team_abbr)
    if not data:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo obtener información de roster para {team_abbr}.",
        )

    # ESPN suele envolver en "team"
    team = data.get("team") or data
    team_name = (
        team.get("displayName")
        or team.get("name")
        or team.get("location")
        or team_abbr
    )

    # ------------------------------------------------------------------
    # Diferentes estructuras posibles de roster:
    #
    # 1) team["roster"]["entries"] -> cada entry tiene "player" o "athlete"
    # 2) team["athletes"] -> lista directa de atletas
    # 3) team["roster"]["athletes"] -> también se ve a veces
    # ------------------------------------------------------------------
    roster_obj = (
        team.get("roster")
        or team.get("athletes")
        or data.get("roster")
    )

    entries: List[Dict[str, Any]] = []

    if isinstance(roster_obj, dict):
        entries = (
            roster_obj.get("entries")
            or roster_obj.get("athletes")
            or roster_obj.get("items")
            or []
        )
    elif isinstance(roster_obj, list):
        entries = roster_obj
    else:
        entries = []

    players_out: List[Dict[str, Any]] = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        # Intentar distintos nombres
        p = (
            entry.get("player")
            or entry.get("athlete")
            or entry.get("athlete", {})
        )

        # En algunos casos el propio entry ya es el jugador
        if not p and "id" in entry:
            p = entry

        if not isinstance(p, dict):
            continue

        athlete_id = p.get("id")
        name = (
            p.get("fullName")
            or p.get("displayName")
            or p.get("shortName")
        )
        pos_info = p.get("position") or {}
        position = (
            pos_info.get("abbreviation")
            or pos_info.get("displayName")
            or pos_info.get("name")
        )
        jersey = p.get("jersey")

        players_out.append(
            {
                "athlete_id": str(athlete_id) if athlete_id else None,
                "name": name,
                "position": position,
                "jersey": jersey,
                "depth": entry.get("status") or entry.get("depth") or None,
                "team_abbr": team_abbr,
            }
        )

    return {
        "team_abbr": team_abbr,
        "team_name": team_name,
        "players": players_out,
    }

# -----------------------------------------------------------------------------
# 3) GAMELOG CRUDO DE JUGADOR NBA
# -----------------------------------------------------------------------------
@router.get("/player/{athlete_id}/gamelog")
async def get_nba_player_gamelog(
    athlete_id: str,
    season: int = Query(..., description="Temporada, ej. 2024"),
    season_type: int = Query(2, description="1=Pre, 2=Regular, 3=Playoffs", ge=1, le=3),
) -> Dict[str, Any]:
    """
    Devuelve el gamelog crudo de ESPN para un jugador NBA específico.
    """
    try:
        data = fetch_nba_player_gamelog(
            athlete_id,
            season=season,
            season_type=season_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not data:
        raise HTTPException(
            status_code=502,
            detail="No se pudo obtener el gamelog del jugador NBA.",
        )

    return data


# -----------------------------------------------------------------------------
# 4) WSPM AUTO (NUMÉRICO) PARA JUGADOR NBA
# -----------------------------------------------------------------------------
@router.post("/wspm/auto-projection", response_model=WSPMOutput)
async def nba_wspm_auto_projection(payload: WSPMAutoRequest):
    """
    Versión automática WSPM para NBA.

    Reutiliza WSPMAutoRequest (NFL) para acelerar desarrollo.
    Para NBA, si agregas scoreboard_date en el schema más adelante,
    este endpoint lo usará sin romper compatibilidad.

    Requiere:
    - event_id
    - athlete_id
    - season
    - season_type
    - market_type (ej. points, rebounds, assists, threes_made, etc.)
    - book_line
    """

    # 1) Resolver fecha de scoreboard de forma tolerante
    scoreboard_date = getattr(payload, "scoreboard_date", None) or getattr(payload, "date", None)
    if scoreboard_date:
        scoreboard_date = str(scoreboard_date).strip()
    else:
        # fallback razonable: hoy en UTC como YYYYMMDD
        scoreboard_date = datetime.utcnow().strftime("%Y%m%d")

    sb = fetch_nba_scoreboard(scoreboard_date)
    if not sb:
        raise HTTPException(
            status_code=502,
            detail="No se pudo obtener el scoreboard NBA desde ESPN.",
        )

    event = next((e for e in sb.get("events", []) if e.get("id") == payload.event_id), None)
    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró el evento {payload.event_id} en el scoreboard NBA para {scoreboard_date}.",
        )

    # 2) Odds del partido (para tempo)
    odds_data = fetch_nba_game_odds(payload.event_id)
    game_total: Optional[float] = None

    if odds_data and "items" in odds_data and odds_data["items"]:
        ou_raw = odds_data["items"][0].get("overUnder")
        try:
            game_total = float(ou_raw) if ou_raw is not None else None
        except (TypeError, ValueError):
            game_total = None

    # 3) Gamelog del jugador
    try:
        gamelog = fetch_nba_player_gamelog(
            payload.athlete_id,
            season=payload.season,
            season_type=payload.season_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    base_projection = compute_base_projection_from_gamelog(
        gamelog=gamelog,
        market_type=payload.market_type,
        games_window=5,
    )

    if base_projection <= 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "No se pudo calcular una base_projection confiable para este jugador/mercado en NBA. "
                "Revisa el gamelog o el mapeo de market_type."
            ),
        )

    # 4) Ajustes automáticos simples por tempo (placeholder)
    if game_total is not None and game_total >= 235:
        adj_tempo = 3.0
    elif game_total is not None and game_total >= 225:
        adj_tempo = 1.5
    else:
        adj_tempo = 0.0

    adj_matchup = 0.0
    adj_volume = 0.0
    adj_risk = 0.0

    net_adjust = adj_matchup + adj_volume + adj_risk + adj_tempo
    wspm_projection = base_projection + net_adjust

    book_line = payload.book_line
    edge = wspm_projection - book_line
    margin_pct = (edge / abs(book_line)) * 100.0 if book_line != 0 else 0.0

    safety_margin_value = abs(edge)
    safety_margin_pct = abs(margin_pct)

    # 5) Prob cover simple
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


# -----------------------------------------------------------------------------
# 5) WSPM AUTO REPORT (CON TEXTO FORMATEADO)
# -----------------------------------------------------------------------------
@router.post("/wspm/auto-projection-report", response_model=WSPMFullReport)
async def nba_wspm_auto_projection_report(payload: WSPMAutoRequest):
    """
    Reporte 'premium' para jugador NBA:
    - base_projection desde gamelog ESPN
    - adj_tempo por total de puntos del partido
    - breakdown de variables
    - markdown listo para frontend/newsletter
    """

    scoreboard_date = getattr(payload, "scoreboard_date", None) or getattr(payload, "date", None)
    if scoreboard_date:
        scoreboard_date = str(scoreboard_date).strip()
    else:
        scoreboard_date = datetime.utcnow().strftime("%Y%m%d")

    sb = fetch_nba_scoreboard(scoreboard_date)
    if not sb:
        raise HTTPException(
            status_code=502,
            detail="No se pudo obtener el scoreboard NBA desde ESPN.",
        )

    event = next((e for e in sb.get("events", []) if e.get("id") == payload.event_id), None)
    if not event:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró el evento {payload.event_id} en el scoreboard NBA para {scoreboard_date}.",
        )

    matchup = event.get("name", f"{payload.player_team} vs {payload.opponent_team}")

    odds_data = fetch_nba_game_odds(payload.event_id)
    game_total: Optional[float] = None

    if odds_data and "items" in odds_data and odds_data["items"]:
        ou_raw = odds_data["items"][0].get("overUnder")
        try:
            game_total = float(ou_raw) if ou_raw is not None else None
        except (TypeError, ValueError):
            game_total = None

    try:
        gamelog = fetch_nba_player_gamelog(
            payload.athlete_id,
            season=payload.season,
            season_type=payload.season_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    base_projection = compute_base_projection_from_gamelog(
        gamelog=gamelog,
        market_type=payload.market_type,
        games_window=5,
    )

    if base_projection <= 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "No se pudo calcular una base_projection confiable para este jugador/mercado en el reporte NBA. "
                "Revisa el gamelog o ajusta el mapeo de market_type."
            ),
        )

    # Ajustes por tempo
    if game_total is not None and game_total >= 235:
        adj_tempo = 3.0
    elif game_total is not None and game_total >= 225:
        adj_tempo = 1.5
    else:
        adj_tempo = 0.0

    adj_matchup = 0.0
    adj_volume = 0.0
    adj_risk = 0.0

    net_adjust = adj_matchup + adj_volume + adj_risk + adj_tempo
    wspm_projection = base_projection + net_adjust

    book_line = payload.book_line
    edge = wspm_projection - book_line
    margin_pct = (edge / abs(book_line)) * 100.0 if book_line != 0 else 0.0

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
            name="Matchup Defensivo Avanzado (On/Off, DRtg, perfiles)",
            description=(
                "Ajuste según calidad defensiva rival vs el tipo de mercado "
                "(puntos, rebotes, asistencias, triples). Placeholder inicial."
            ),
            weight=adj_matchup,
        ),
        WSPMVariableBreakdown(
            name="Volumen de Juego Proyectado (uso/minutos/roles)",
            description=(
                "Proyección de uso basada en gamelog reciente y rol en la rotación. "
                "Placeholder inicial."
            ),
            weight=adj_volume,
        ),
        WSPMVariableBreakdown(
            name="Riesgo / Volatilidad",
            description=(
                "Factor de riesgo por back-to-back, status de lesión, blowout risk, "
                "rotaciones. Placeholder inicial."
            ),
            weight=adj_risk,
        ),
        WSPMVariableBreakdown(
            name="Game Flow (Ritmo / Total del partido)",
            description=(
                "Impacto del total del partido y ritmo esperado. Totales altos suelen "
                "favorecer OVER en mercados de producción."
            ),
            weight=adj_tempo,
        ),
    ]

    market_label = payload.market_type.replace("_", " ")
    line_str = f"{book_line:.1f}"
    proj_str = f"{wspm_projection:.1f}"
    pick_str = f"{direction} {line_str}"

    markdown_report = f"""### 📈 Proyección del Modelo WSPM (NBA)

*Partido:* {matchup}
*Jugador:* {payload.player_name}  
*Posición:* {payload.position}  
*Línea del book (Proyección O/U):* {line_str} {market_label}  
*Proyección del modelo WSPM:* {proj_str} {market_label}  
*Pick del modelo WSPM:* {pick_str}

#### ⚖️ Ponderación de Variables Clave (vs Línea Base):

* **Variable 1: Matchup Defensivo Avanzado**  
  - *Ponderación:* {adj_matchup:+.1f} unidades

* **Variable 2: Volumen de Juego Proyectado**  
  - *Ponderación:* {adj_volume:+.1f} unidades

* **Variable 3: Riesgo/Volatilidad**  
  - *Ponderación:* {adj_risk:+.1f} unidades

* **Variable 4: Game Flow (Tempo/Total)**  
  - *Ponderación:* {adj_tempo:+.1f} unidades

#### 🎯 Análisis y Justificación:

El modelo parte de una proyección base de **{base_projection:.1f}** basada en el rendimiento reciente del jugador
(gamelog de ESPN). Sobre esa base se aplican ajustes por matchup, volumen esperado, riesgo y ritmo de partido, para
un **Ajuste Neto Total de {net_adjust:.1f}** unidades, resultando en una proyección final WSPM de **{proj_str}**.

El margen de seguridad respecto a la línea del book es de **{safety_margin_value:.1f}** unidades
({safety_margin_pct:.1f}%), con una probabilidad estimada de cubrir la línea de **{prob_cover:.1f}%**.

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
