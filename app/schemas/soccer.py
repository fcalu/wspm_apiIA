# app/schemas/soccer.py

from typing import Optional
from pydantic import BaseModel, Field

from app.schemas.nfl import TeamInfo


class SoccerGameProjectionRequest(BaseModel):
    event_id: str = Field(..., description="ID del evento ESPN Soccer.")
    line_over25: float = Field(
        default=2.5,
        description="Línea de goles para el mercado principal Over/Under (ej. 2.5).",
    )


class SoccerGameProjectionOutput(BaseModel):
    event_id: str
    matchup: str

    home_team: Optional[TeamInfo] = None
    away_team: Optional[TeamInfo] = None

    book_total: Optional[float] = None
    model_total: Optional[float] = None

    # Over 2.5
    pick_over25: str
    prob_over25: float
    confidence_over25: str
    edge_over25: float
    margin_over25_pct: float

    # Ambos anotan (BTTS)
    pick_btts: str
    prob_btts: float
    confidence_btts: str

    # 1X2 (1 = local, X = empate, 2 = visita)
    pick_1x2: str
    prob_1x2: float
    confidence_1x2: str

    # Doble oportunidad
    pick_double_chance: str   # 1X, X2 o 12
    prob_double_chance: float
    confidence_double_chance: str
