from pathlib import Path
import pytest
from app.services.season_pitcher import parse_season_pitchers, SeasonPitcherDataError


def test_parse_valid_aggregates(tmp_path: Path):
    f = tmp_path / 's.csv'
    f.write_text('pitcher_id,pitcher_name,team_code,games,batters_faced,strikeouts,walks,k_pct,bb_pct,k_minus_bb_pct\n'
                 '11,Test Pitcher,KIA,3,25,5,2,20.0,8.0,12.0\n')
    rows = parse_season_pitchers(f)
    assert rows[0]['k_minus_bb_pct'] == 12.0
    assert rows[0]['batters_faced'] == 25


def test_reject_inconsistent_rate(tmp_path: Path):
    f = tmp_path / 's.csv'
    f.write_text('pitcher_id,pitcher_name,team_code,games,batters_faced,strikeouts,walks,k_pct,bb_pct,k_minus_bb_pct\n'
                 '11,Test Pitcher,KIA,3,25,5,2,20.0,8.0,99.0\n')
    with pytest.raises(SeasonPitcherDataError):
        parse_season_pitchers(f)


def test_reject_duplicate_pitcher_team(tmp_path: Path):
    f = tmp_path / 's.csv'
    f.write_text('pitcher_id,pitcher_name,team_code,games,batters_faced,strikeouts,walks,k_pct,bb_pct,k_minus_bb_pct\n'
                 '11,Test Pitcher,KIA,3,25,5,2,20.0,8.0,12.0\n'
                 '11,Test Pitcher,KIA,3,25,5,2,20.0,8.0,12.0\n')
    with pytest.raises(SeasonPitcherDataError):
        parse_season_pitchers(f)
