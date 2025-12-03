# app/data/nfl_players_core.py

"""
Catálogo base de jugadores NFL para el motor WSPM.

- Cada entrada representa a un jugador identificado por un athlete_id (string).
- Este catálogo se usa en:
    - /nfl/wspm/auto-projection
    - /nfl/wspm/auto-week

Campos esperados por el backend:
- athlete_id (clave del dict)
- name: Nombre del jugador
- team: Abreviatura del equipo (DAL, DET, KC, etc.)
- position: Posición (QB, RB, WR, TE...)
- rank: Prioridad dentro del equipo (1 = más importante para props)
- default_markets: dict con mercados por defecto y su "book_line" aproximada:
    - "passing_yards"
    - "rushing_yards"
    - "receiving_yards"

NOTA:
- Los athlete_id de ejemplo (ATH_XXX_YYY) los puedes reemplazar por los IDs reales de ESPN.
- Los valores de default_markets son ejemplos, ajústalos según tu criterio/modelo.
"""

NFL_PLAYERS_CORE = {
    # ---------------------------------------------------------
    # DALLAS COWBOYS (DAL)
    # ---------------------------------------------------------
    # CeeDee Lamb - WR1 (ya lo usas con 3043078)
    "3043078": {
        "name": "CeeDee Lamb",
        "team": "DAL",
        "position": "WR",
        "rank": 1,
        "default_markets": {
            "receiving_yards": 78.0,
        },
    },
    # QB Cowboys
    "ATH_DAL_QB": {
        "name": "Dak Prescott",
        "team": "DAL",
        "position": "QB",
        "rank": 1,
        "default_markets": {
            "passing_yards": 265.5,
        },
    },
    # RB1 Cowboys
    "ATH_DAL_RB1": {
        "name": "RB1 Cowboys",
        "team": "DAL",
        "position": "RB",
        "rank": 2,
        "default_markets": {
            "rushing_yards": 62.5,
            "receiving_yards": 18.5,
        },
    },
    # WR2 / TE Cowboys
    "ATH_DAL_WR2": {
        "name": "WR2 Cowboys",
        "team": "DAL",
        "position": "WR",
        "rank": 3,
        "default_markets": {
            "receiving_yards": 48.5,
        },
    },

    # ---------------------------------------------------------
    # DETROIT LIONS (DET)
    # ---------------------------------------------------------
    # WR1 Lions
    "ATH_DET_AMONRA": {
        "name": "Amon-Ra St. Brown",
        "team": "DET",
        "position": "WR",
        "rank": 1,
        "default_markets": {
            "receiving_yards": 82.5,
        },
    },
    # QB Lions
    "ATH_DET_QB": {
        "name": "QB Lions",
        "team": "DET",
        "position": "QB",
        "rank": 1,
        "default_markets": {
            "passing_yards": 265.0,
        },
    },
    # RB1 Lions
    "ATH_DET_RB1": {
        "name": "RB1 Lions",
        "team": "DET",
        "position": "RB",
        "rank": 2,
        "default_markets": {
            "rushing_yards": 64.5,
            "receiving_yards": 20.5,
        },
    },
    # TE / WR2 Lions
    "ATH_DET_LAPORTA": {
        "name": "Sam LaPorta",
        "team": "DET",
        "position": "TE",
        "rank": 3,
        "default_markets": {
            "receiving_yards": 49.5,
        },
    },

    # ---------------------------------------------------------
    # KANSAS CITY CHIEFS (KC)
    # ---------------------------------------------------------
    # QB Chiefs
    "ATH_KC_MAHOMES": {
        "name": "Patrick Mahomes",
        "team": "KC",
        "position": "QB",
        "rank": 1,
        "default_markets": {
            "passing_yards": 280.5,
        },
    },
    # TE1 Chiefs
    "ATH_KC_KELCE": {
        "name": "Travis Kelce",
        "team": "KC",
        "position": "TE",
        "rank": 1,
        "default_markets": {
            "receiving_yards": 71.5,
        },
    },
    # WR1 Chiefs
    "ATH_KC_WR1": {
        "name": "WR1 Chiefs",
        "team": "KC",
        "position": "WR",
        "rank": 2,
        "default_markets": {
            "receiving_yards": 60.5,
        },
    },
    # RB1 Chiefs
    "ATH_KC_RB1": {
        "name": "RB1 Chiefs",
        "team": "KC",
        "position": "RB",
        "rank": 3,
        "default_markets": {
            "rushing_yards": 55.5,
            "receiving_yards": 16.5,
        },
    },

    # ---------------------------------------------------------
    # PHILADELPHIA EAGLES (PHI)
    # ---------------------------------------------------------
    # QB Eagles
    "ATH_PHI_QB": {
        "name": "QB Eagles",
        "team": "PHI",
        "position": "QB",
        "rank": 1,
        "default_markets": {
            "passing_yards": 245.5,
            "rushing_yards": 35.5,  # si es QB dual
        },
    },
    # WR1 Eagles
    "ATH_PHI_WR1": {
        "name": "WR1 Eagles",
        "team": "PHI",
        "position": "WR",
        "rank": 1,
        "default_markets": {
            "receiving_yards": 78.5,
        },
    },
    # WR2 Eagles
    "ATH_PHI_WR2": {
        "name": "WR2 Eagles",
        "team": "PHI",
        "position": "WR",
        "rank": 2,
        "default_markets": {
            "receiving_yards": 62.5,
        },
    },
    # RB1 Eagles
    "ATH_PHI_RB1": {
        "name": "RB1 Eagles",
        "team": "PHI",
        "position": "RB",
        "rank": 3,
        "default_markets": {
            "rushing_yards": 63.5,
            "receiving_yards": 15.5,
        },
    },

    # ---------------------------------------------------------
    # SAN FRANCISCO 49ERS (SF)
    # ---------------------------------------------------------
    # QB 49ers
    "ATH_SF_QB": {
        "name": "QB 49ers",
        "team": "SF",
        "position": "QB",
        "rank": 1,
        "default_markets": {
            "passing_yards": 255.5,
        },
    },
    # RB1 49ers
    "ATH_SF_RB1": {
        "name": "RB1 49ers",
        "team": "SF",
        "position": "RB",
        "rank": 1,
        "default_markets": {
            "rushing_yards": 82.5,
            "receiving_yards": 28.5,
        },
    },
    # WR1 49ers
    "ATH_SF_WR1": {
        "name": "WR1 49ers",
        "team": "SF",
        "position": "WR",
        "rank": 2,
        "default_markets": {
            "receiving_yards": 72.5,
        },
    },
    # WR2 / TE 49ers
    "ATH_SF_WR2": {
        "name": "WR2/TE 49ers",
        "team": "SF",
        "position": "TE",
        "rank": 3,
        "default_markets": {
            "receiving_yards": 55.5,
        },
    },

    # ---------------------------------------------------------
    # BALTIMORE RAVENS (BAL)
    # ---------------------------------------------------------
    # QB Ravens
    "ATH_BAL_QB": {
        "name": "QB Ravens",
        "team": "BAL",
        "position": "QB",
        "rank": 1,
        "default_markets": {
            "passing_yards": 225.5,
            "rushing_yards": 45.5,  # si es QB corredor
        },
    },
    # TE1 Ravens
    "ATH_BAL_TE1": {
        "name": "TE1 Ravens",
        "team": "BAL",
        "position": "TE",
        "rank": 1,
        "default_markets": {
            "receiving_yards": 60.5,
        },
    },
    # WR1 Ravens
    "ATH_BAL_WR1": {
        "name": "WR1 Ravens",
        "team": "BAL",
        "position": "WR",
        "rank": 2,
        "default_markets": {
            "receiving_yards": 58.5,
        },
    },
    # RB1 Ravens
    "ATH_BAL_RB1": {
        "name": "RB1 Ravens",
        "team": "BAL",
        "position": "RB",
        "rank": 3,
        "default_markets": {
            "rushing_yards": 68.5,
            "receiving_yards": 12.5,
        },
    },
}
