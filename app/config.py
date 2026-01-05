from typing import Dict
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    app_name: str = "WSPM API"
    environment: str = "development"

    # =====================================================
    # ESPN NFL
    # =====================================================
    espn_nfl_site_base_url: str = (
        "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
    )
    espn_nfl_core_base_url: str = (
        "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
    )
    espn_nfl_web_base_url: str = (
        "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl"
    )

    # =====================================================
    # ESPN NBA
    # =====================================================
    espn_nba_site_base_url: str = (
        "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
    )
    espn_nba_core_base_url: str = (
        "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"
    )
    espn_nba_web_base_url: str = (
        "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba"
    )

    # =====================================================
    # ESPN SOCCER (compat + multi-torneo)
    # =====================================================
    # Siguen existiendo estas 2 (para no romper nada):
    # Por defecto apuntan a Premier League (eng.1)
    espn_soccer_site_base_url: str = (
        "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1"
    )
    espn_soccer_core_base_url: str = (
        "https://sports.core.api.espn.com/v2/sports/soccer/leagues/eng.1"
    )

    # Liga por defecto que usarán los nuevos endpoints/templates
    espn_soccer_default_league: str = Field(default="eng.1")

    # Plantillas para construir URL según liga
    # Ej: template.format(league_code="esp.1")
    espn_soccer_site_base_url_template: str = Field(
        default="https://site.api.espn.com/apis/site/v2/sports/soccer/{league_code}"
    )
    espn_soccer_core_base_url_template: str = Field(
        default="https://sports.core.api.espn.com/v2/sports/soccer/leagues/{league_code}"
    )

    # 8 torneos preconfigurados (puedes usar estos códigos en tus endpoints)
    espn_soccer_leagues: Dict[str, str] = Field(
        default_factory=lambda: {
            # 1) Premier League (Inglaterra)
            "premier_league": "eng.1",
            # 2) LaLiga (España)
            "laliga": "esp.1",
            # 3) Serie A (Italia)
            "serie_a": "ita.1",
            # 4) Bundesliga (Alemania)
            "bundesliga": "ger.1",
            # 5) Ligue 1 (Francia)
            "ligue_1": "fra.1",
            # 6) Liga MX (México)
            "liga_mx": "mex.1",
            # 7) MLS (Estados Unidos)
            "mls": "usa.1",
            # 8) UEFA Champions League
            "champions_league": "uefa.champions",
        }
    )

    # =====================================================
    # Comunes ESPN
    # =====================================================
    espn_cache_ttl_seconds: int = 900
    espn_timeout_seconds: int = 10

    class Config:
        env_file = ".env"


settings = Settings()
