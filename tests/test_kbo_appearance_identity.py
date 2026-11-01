import json

from scripts.import_kbo_regular_appearances import (
    parse_pitcher_table,
)


def make_row(name: str, pitches: int):
    values = [
        name, "구원", "", "0", "1", "0", "0",
        "4", str(pitches), "0", "0", "0", "0", "1",
    ]

    return {
        "row": [{"Text": value} for value in values]
    }


def test_same_name_pitchers_have_different_orders():
    table = {
        "table": json.dumps({
            "rows": [
                make_row("이승현", 68),
                make_row("이승현", 34),
            ],
        }),
    }

    result = parse_pitcher_table(table, "SS")

    assert len(result) == 2

    assert result[0]["pitcher_name"] == "이승현"
    assert result[1]["pitcher_name"] == "이승현"

    assert result[0]["appearance_order"] == 1
    assert result[1]["appearance_order"] == 2

    assert result[0]["pitches"] == 68
    assert result[1]["pitches"] == 34

    assert result[0]["pitcher_id"] is None
    assert result[1]["pitcher_id"] is None


def test_different_teams_have_independent_orders():
    table = {
        "table": json.dumps({
            "rows": [make_row("테스트 투수", 20)],
        }),
    }

    away = parse_pitcher_table(table, "OB")
    home = parse_pitcher_table(table, "SS")

    assert away[0]["appearance_order"] == 1
    assert home[0]["appearance_order"] == 1