from collections import defaultdict
from typing import Any


HIT_EVENTS = {
    "single",
    "double",
    "triple",
    "home_run",
}


def aggregate_pitcher_matchup(
    rows: list[dict[str, Any]],
    pitcher_id: str,
    batter_id: str,
) -> dict[str, Any]:
    # 먼저 전체 타석을 묶어야 투수 교체가 있었는지 확인할 수 있다.
    plate_appearances = defaultdict(list)
    seen_pitches = set()

    for row in rows:
        pitch_key = (
            row["game_pk"],
            row["at_bat_number"],
            row["pitch_number"],
        )

        if pitch_key in seen_pitches:
            continue

        seen_pitches.add(pitch_key)

        pa_key = (
            row["game_pk"],
            row["at_bat_number"],
        )
        plate_appearances[pa_key].append(row)

    result = {
        "pitcher_id": pitcher_id,
        "batter_id": batter_id,
        "plate_appearances": 0,
        "hits": 0,
        "strikeouts": 0,
        "walks": 0,
        "home_runs": 0,
        "excluded_mixed_pitcher_pa": 0,
        "excluded_incomplete_pa": 0,
        "sample_size_warning": True,
    }

    for pitches in plate_appearances.values():
        if not any(
            str(row["pitcher"]) == pitcher_id
            and str(row["batter"]) == batter_id
            for row in pitches
        ):
            continue

        pitchers = {
            str(row["pitcher"])
            for row in pitches
            if row.get("pitcher")
        }

        if len(pitchers) != 1:
            result["excluded_mixed_pitcher_pa"] += 1
            continue

        events = {
            row["events"]
            for row in pitches
            if row.get("events")
        }

        # 완료되지 않았거나 결과가 충돌하는 타석은 제외한다.
        if len(events) != 1:
            result["excluded_incomplete_pa"] += 1
            continue

        event = next(iter(events))

        result["plate_appearances"] += 1

        if event in HIT_EVENTS:
            result["hits"] += 1

        if event == "strikeout":
            result["strikeouts"] += 1

        if event == "walk":
            result["walks"] += 1

        if event == "home_run":
            result["home_runs"] += 1

    result["sample_size_warning"] = (
        result["plate_appearances"] < 20
    )

    return result