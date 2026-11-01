from collections import Counter
from datetime import date, timedelta
from typing import Any


def aggregate_bullpen_workload(
    rows: list[dict[str, Any]],
    pitcher_id: str,
    as_of_date: date,
    data_through: date | None = None,
) -> dict[str, Any]:
    # 경기 시작 전 기준으로 분석하며, 당일과 이후 기록은 제외한다.
    pitch_keys = set()
    pitches_by_date = Counter()

    for row in rows:
        if str(row.get("pitcher")) != pitcher_id:
            continue

        game_date_value = row.get("game_date")
        if not game_date_value:
            continue

        game_date = (
            game_date_value
            if isinstance(game_date_value, date)
            else date.fromisoformat(game_date_value)
        )

        if game_date >= as_of_date:
            continue

        pitch_key = (
            row["game_pk"],
            row["at_bat_number"],
            row["pitch_number"],
        )

        # 같은 투구가 중복 저장되어도 투구 수가 증가하지 않도록 한다.
        if pitch_key in pitch_keys:
            continue

        pitch_keys.add(pitch_key)
        pitches_by_date[game_date] += 1

    appearance_dates = sorted(pitches_by_date)

    if not appearance_dates:
        return {
            "pitcher_id": pitcher_id,
            "as_of_date": as_of_date.isoformat(),
            "last_appearance": None,
            "days_rest": None,
            "appearances_last_3_days": 0,
            "pitches_last_3_days": 0,
            "consecutive_days": 0,
            "workload_status": "UNKNOWN",
            "data_through": (
                data_through.isoformat() if data_through else None
            ),
            "data_warning": "분석 기준일 이전의 등판 기록이 없습니다.",
        }

    # 기준일 전날부터 3일간의 기록을 집계한다.
    window_start = as_of_date - timedelta(days=3)

    recent_dates = [
        day
        for day in appearance_dates
        if window_start <= day < as_of_date
    ]

    last_appearance = appearance_dates[-1]
    days_rest = (as_of_date - last_appearance).days - 1

    # 연투는 기준일 전날부터 이어진 연속 등판 일수로 정의한다.
    consecutive_days = 0
    day = as_of_date - timedelta(days=1)

    while day in pitches_by_date:
        consecutive_days += 1
        day -= timedelta(days=1)

    pitches_last_3_days = sum(
        pitches_by_date[day]
        for day in recent_dates
    )

    # 의료적 판단이 아닌, 코치가 확인할 투구 부담 신호다.
    if (
        consecutive_days >= 2
        or pitches_last_3_days >= 40
    ):
        workload_status = "REVIEW_REQUIRED"
    else:
        workload_status = "NO_HIGH_LOAD_FLAG"

    warnings = []

    if data_through is not None and as_of_date > (
        data_through + timedelta(days=1)
    ):
        warnings.append(
            "분석 기준일보다 데이터 수집 범위가 오래되어 "
            "최근 등판 기록이 누락되었을 수 있습니다."
        )

        # 최근 기록을 확인할 수 없으므로 낮은 부담으로 판단하지 않는다.
        workload_status = "UNKNOWN"

    return {
        "pitcher_id": pitcher_id,
        "as_of_date": as_of_date.isoformat(),
        "last_appearance": last_appearance.isoformat(),
        "days_rest": days_rest,
        "appearances_last_3_days": len(recent_dates),
        "pitches_last_3_days": pitches_last_3_days,
        "consecutive_days": consecutive_days,
        "workload_status": workload_status,
        "data_through": (
            data_through.isoformat() if data_through else None
        ),
        "data_warning": " ".join(warnings) if warnings else None,
    }