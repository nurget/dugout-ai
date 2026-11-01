from app.services.team_codes import normalize_official_team_code


def test_team_code_mapping():
    assert normalize_official_team_code("KIA") == "HT"
    assert normalize_official_team_code("SSG") == "SK"
    assert normalize_official_team_code("HT") == "HT"
    assert normalize_official_team_code("lg") == "LG"
