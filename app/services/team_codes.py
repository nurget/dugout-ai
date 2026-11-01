OFFICIAL_TEAM_CODES = {
    "KIA": "HT",
    "DOOSAN": "OB",
    "SSG": "SK",
    "SAMSUNG": "SS",
    "HANWHA": "HH",
    "LOTTE": "LT",
    "KIWOOM": "WO",
}


def normalize_official_team_code(team_code: str) -> str:
    code = team_code.strip().upper()
    return OFFICIAL_TEAM_CODES.get(code, code)
