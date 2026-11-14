OFFICIAL_TEAM_CODES = {
    "KIA": "HT",
    "SAM": "SS",
    "SSG": "SK",
    "HAN": "HH",
    "DOO": "OB",
    "LOT": "LT",
    "KIW": "WO",
    "DOOSAN": "OB",
    "SAMSUNG": "SS",
    "HANWHA": "HH",
    "LOTTE": "LT",
    "KIWOOM": "WO",
}

GAME_TEAM_CODE_ALIASES = {
    "HT": ("KIA", "HT"),
    "SS": ("SAM", "SS"),
    "LG": ("LG",),
    "KT": ("KT",),
    "SK": ("SSG", "SK"),
    "NC": ("NC",),
    "OB": ("DOO", "OB"),
    "LT": ("LOT", "LT"),
    "HH": ("HAN", "HH"),
    "WO": ("KIW", "WO"),
}


def game_team_code_candidates(team_code: str) -> tuple[str, ...]:
    code = team_code.strip().upper()
    official_code = normalize_official_team_code(code)
    return GAME_TEAM_CODE_ALIASES.get(official_code, (code,))


def normalize_official_team_code(team_code: str) -> str:
    code = team_code.strip().upper()
    return OFFICIAL_TEAM_CODES.get(code, code)
