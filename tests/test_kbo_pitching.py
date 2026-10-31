from datetime import date
import pytest
from app.services.kbo_pitching import DailyPitching, aggregate_pitchers, load_pitching_csv, PitchingDataError

def test_rate_with_complete_pa():
    x = DailyPitching(2026, date(2026, 4, 1), "KIA", "Example", 5, 1, 24, 18)
    result = aggregate_pitchers([x])[0]
    assert result["k_minus_bb_pct"] == 16.67


def test_missing_pa_is_not_guessed():
    a = DailyPitching(2026, date(2026, 4, 1), "KIA", "Example", 5, 1, 24, 18)
    b = DailyPitching(2026, date(2026, 4, 2), "KIA", "Example", 4, 2, None, 15)
    result = aggregate_pitchers([a, b])[0]
    assert result["k_minus_bb_pct"] is None
    assert result["batters_faced"] is None


def test_csv_rejects_unknown_players(tmp_path):
    p = tmp_path / "pitching.csv"
    p.write_text("Name,Date,Tm,SO,BB,Season,PitOuts,PA\nUnknown_123,03/28/2026,KIA,1,0,2026,3,4\n")
    with pytest.raises(PitchingDataError, match="선수 식별 불가"):
        load_pitching_csv(p)


def test_identical_duplicates_are_not_counted_twice(tmp_path):
    p = tmp_path / "pitching.csv"
    row = "Example,03/28/2026,KIA,2,1,2026,9,12\n"
    p.write_text("Name,Date,Tm,SO,BB,Season,PitOuts,PA\n" + row + row)
    records, stats = load_pitching_csv(p)
    assert len(records) == 1
    assert stats["duplicates"] == 1

def test_unknown_pitcher_can_be_skipped(tmp_path):
    csv_path = tmp_path / "pitching.csv"

    csv_path.write_text(
        "Name,Date,Tm,SO,BB,Season,PitOuts,PA\n"
        "Unknown_55633,03/28/2026,KIA,2,1,2026,3,5\n"
        "Test Pitcher,03/28/2026,KIA,5,1,2026,18,24\n",
        encoding="utf-8",
    )

    records, quality = load_pitching_csv(
        csv_path,
        skip_unknown=True,
    )

    assert len(records) == 1
    assert records[0].pitcher_name == "Test Pitcher"
    assert quality["skipped_unknown"] == 1
    assert quality["unknown_players"][0]["line"] == 2