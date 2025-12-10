from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "WSPM API"
    environment: str = "development"

    espn_nfl_site_base_url: str = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
    espn_nfl_core_base_url: str = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
    espn_nfl_web_base_url: str = "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl"

    espn_nba_site_base_url: str = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
    espn_nba_core_base_url: str = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"
    espn_nba_web_base_url: str = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba"

    espn_soccer_site_base_url: str = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1"
    espn_soccer_core_base_url: str = "https://sports.core.api.espn.com/v2/sports/soccer/leagues/eng.1"

    espn_cache_ttl_seconds: int = 900
    espn_timeout_seconds: int = 10

    class Config:
        env_file = ".env"


settings = Settings()
