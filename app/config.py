from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "WSPM API"
    environment: str = "development"

    # --- ESPN NFL ---
    espn_nfl_site_base_url: str = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
    espn_nfl_core_base_url: str = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
    espn_nfl_web_base_url: str = "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl"
    # --- ESPN NBA ---
    espn_nba_site_base_url: str = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
    espn_nba_core_base_url: str = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"

    # --- ESPN Soccer (ejemplos: Premier League eng.1) ---
    # Luego puedes agregar más ligas (espn_soccer_league_codes tipo eng.1, esp.1, mex.1, etc.)
    espn_soccer_site_base_url: str = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1"
    espn_soccer_core_base_url: str = "https://sports.core.api.espn.com/v2/sports/soccer/leagues/eng.1"

    # TTL del cache en segundos para llamadas a ESPN
    espn_cache_ttl_seconds: int = 60

    class Config:
        env_file = ".env"


settings = Settings()
