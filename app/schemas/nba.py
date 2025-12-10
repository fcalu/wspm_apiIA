from typing import List, Optional
from pydantic import BaseModel, Field


class NBAAthleteInput(BaseModel):
    athlete_id: str
    player_name: str
    player_team: str = Field(..., description="Abreviatura: LAL, BOS, PHX...")
    position: Optional[str] = None


class NBAStreakRequest(BaseModel):
    season: int
    season_type: int = 2
    athletes: List[NBAAthleteInput]

    min_streak: int = 5
    games_lookup: int = 20


class NBAStreakGroup(BaseModel):
    title: str
    lines: List[str] = []


class NBAStreakResponse(BaseModel):
    season: int
    season_type: int
    min_streak: int
    games_lookup: int

    pts: NBAStreakGroup
    reb: NBAStreakGroup
    ast: NBAStreakGroup
    fg3m: NBAStreakGroup
