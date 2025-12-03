# app/schemas/nfl.py

from typing import List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 1) MODELOS BÁSICOS: EQUIPOS, SCOREBOARD, ODDS
# ---------------------------------------------------------------------------

class TeamInfo(BaseModel):
    name: Optional[str] = None
    abbr: Optional[str] = None


class ScoreboardEvent(BaseModel):
    event_id: str
    matchup: str
    home_team: Optional[TeamInfo] = None
    away_team: Optional[TeamInfo] = None


class ScoreboardResponse(BaseModel):
    week: int
    season_type: int
    events: List[ScoreboardEvent]


class OddsBook(BaseModel):
    provider: str
    details: str
    over_under: Optional[float] = None


class OddsResponse(BaseModel):
    event_id: str
    books: List[OddsBook]
    raw_count: int


# ---------------------------------------------------------------------------
# 2) WSPM MANUAL (INPUT / OUTPUT)
# ---------------------------------------------------------------------------

class WSPMInput(BaseModel):
    """
    Payload manual para /wspm/projection
    El usuario define base_projection y los ajustes.
    """
    event_id: str
    player_name: str
    player_team: str
    opponent_team: str
    position: str
    market_type: str  # ej. "receiving_yards", "rushing_yards", "passing_yards"
    book_line: float

    base_projection: float
    adj_matchup: float
    adj_volume: float
    adj_risk: float
    adj_tempo: float

    # Si la quieres forzar, se usa en lugar de base + ajustes
    model_projection: Optional[float] = None


class WSPMOutput(BaseModel):
    """
    Salida estándar del modelo WSPM (manual o auto).
    """
    event_id: str
    player_name: str
    player_team: str
    opponent_team: str
    position: str
    market_type: str

    book_line: float
    base_projection: float
    adj_matchup: float
    adj_volume: float
    adj_risk: float
    adj_tempo: float

    net_adjust: float
    wspm_projection: float
    edge: float
    margin_pct: float

    safety_margin_value: float
    safety_margin_pct: float

    prob_cover: float
    direction: str    # "OVER" / "UNDER"
    confidence: str   # "Alta", "Media-Alta", "Media", "Baja"

    # Campos opcionales que algunos endpoints rellenan
    game_total: Optional[float] = None
    analysis: Optional[str] = None


# ---------------------------------------------------------------------------
# 3) WSPM AUTO (REQUEST)
# ---------------------------------------------------------------------------

class WSPMAutoRequest(BaseModel):
    """
    Payload para /wspm/auto-projection y /wspm/auto-projection-report.
    El backend hace casi todo solo usando ESPN.
    """
    athlete_id: str = Field(..., description="ID de atleta en ESPN (ej. 3043078)")
    event_id: str = Field(..., description="ID del evento, viene del scoreboard (ej. 401772694)")

    season: int = Field(..., description="Temporada NFL, ej. 2024, 2025")
    season_type: int = Field(
        2,
        description="Tipo de temporada: 1=Pre, 2=Regular, 3=Post",
        ge=1,
        le=3,
    )
    week: int = Field(..., description="Semana de NFL, ej. 1..18", ge=1)

    player_name: str
    player_team: str
    opponent_team: str
    position: str

    market_type: str  # ej. "receiving_yards", "rushing_yards", "passing_yards"
    book_line: float


# ---------------------------------------------------------------------------
# 4) JUEGOS + ODDS (PARA FRONTEND)
# ---------------------------------------------------------------------------

class GameOddsSummary(BaseModel):
    provider: str
    details: str
    over_under: Optional[float] = None


class GameWithOdds(BaseModel):
    event_id: str
    matchup: str
    home_team: Optional[TeamInfo] = None
    away_team: Optional[TeamInfo] = None
    odds: Optional[GameOddsSummary] = None


class GamesWithOddsResponse(BaseModel):
    week: int
    season_type: int
    games: List[GameWithOdds]


# ---------------------------------------------------------------------------
# 5) CATÁLOGO DE EQUIPOS NFL
# ---------------------------------------------------------------------------

class NFLTeam(BaseModel):
    team_id: str
    abbr: str
    name: str
    location: Optional[str] = None
    short_name: Optional[str] = None
    logo: Optional[str] = None


class NFLTeamsResponse(BaseModel):
    count: int
    teams: List[NFLTeam]


# ---------------------------------------------------------------------------
# 6) WSPM FULL REPORT (FORMATO “VENDIBLE”)
# ---------------------------------------------------------------------------

class WSPMVariableBreakdown(BaseModel):
    name: str
    description: str
    weight: float


class WSPMFullReport(BaseModel):
    # Datos básicos del contexto
    event_id: str
    matchup: str
    player_name: str
    player_team: str
    opponent_team: str
    position: str
    market_type: str

    # Book y proyección
    book_line: float
    wspm_projection: float
    pick: str  # "OVER 68.5", "UNDER 42.5", etc.

    # Breakdown numérico
    base_projection: float
    adj_matchup: float
    adj_volume: float
    adj_risk: float
    adj_tempo: float
    net_adjust: float
    edge: float
    margin_pct: float
    safety_margin_value: float
    safety_margin_pct: float
    prob_cover: float
    confidence: str

    # Info de partido
    game_total: Optional[float] = None

    # Desglose textual de variables
    variables: List[WSPMVariableBreakdown]

    # Reporte ya formateado tipo prompt que quieres vender
    markdown_report: str
