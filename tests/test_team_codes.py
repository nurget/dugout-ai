from app.services.team_codes import (
    game_team_code_candidates,
    normalize_official_team_code,
)


def test_team_code_mapping():
    assert normalize_official_team_code("KIA") == "HT"
    assert normalize_official_team_code("SSG") == "SK"
    assert normalize_official_team_code("HT") == "HT"
    assert normalize_official_team_code("lg") == "LG"


def test_game_team_codes_accept_official_and_legacy_aliases():
    assert game_team_code_candidates("KIA") == ("KIA", "HT")
    assert game_team_code_candidates("HT") == ("KIA", "HT")
    assert game_team_code_candidates("DOO") == ("DOO", "OB")
