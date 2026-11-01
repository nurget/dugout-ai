
from collections import defaultdict
from datetime import date, timedelta
from typing import Any


def calculate_appearance_workloads(
    rows: list[dict[str, Any]],
    *,
    as_of_date: date,
) -> list[dict[str, Any]]:
    """
    경기별 공식 투구 수에서 최근 부담을 집계한다.

    같은 팀 + 같은 이름을 임시 식별자로 사용한다.
    실제 선수 ID 매칭은 별도 검증이 필요하다.

    기록 부재는 실제 미등판을 의미하지 않을 수 있으므로
    등판 가능 여부를 확정하지 않는다.
    """

    grouped = defaultdict(lambda: defaultdict(int))
    seen_games = set()
    unknown_pitch_counts = set()

    for row in rows:
        game_date = row["game_date"]

        if isinstance(game_date, str):
            game_date = date.fromisoformat(game_date)

        if game_date >= as_of_date:
            continue

        team_code = row["team_code"]
        pitcher_name = row["pitcher_name"]

        identity = (team_code, pitcher_name)
        game_key = (row["game_pk"], *identity)

        # 같은 경기의 동일 투수 기록을 중복 계산하지 않는다.
        if game_key in seen_games:
            raise ValueError(
                f"경기별 투수 기록 중복: {game_key}"
            )

        seen_games.add(game_key)

        pitches = row["pitches"]

        if pitches is None:
            unknown_pitch_counts.add(identity)
            continue

        if type(pitches) is not int or pitches < 0:
            raise ValueError(
                f"유효하지 않은 투구 수: {identity}, {pitches}"
            )

        grouped[identity][game_date] += pitches

    # 투구 수가 없는 선수도 결과에서 누락되지 않도록 한다.
    all_identities = set(grouped) | unknown_pitch_counts

    results = []

    for team_code, pitcher_name in sorted(all_identities):
        identity = (team_code, pitcher_name)
        daily = grouped[identity]

        recent_dates = [
            day
            for day in daily
            if as_of_date - timedelta(days=3) <= day < as_of_date
        ]

        last_appearance = max(daily) if daily else None

        days_rest = (
            (as_of_date - last_appearance).days - 1
            if last_appearance
            else None
        )

        consecutive_days = 0
        current_day = as_of_date - timedelta(days=1)

        while current_day in daily:
            consecutive_days += 1
            current_day -= timedelta(days=1)

        pitches_last_3_days = sum(
            daily[day] for day in recent_dates
        )

        # 2일 연투 / 최근 3일 40구는 MVP 예시 기준이다.
        requires_review = (
            consecutive_days >= 2
            or pitches_last_3_days >= 40
        )

        status = (
            "UNKNOWN"
            if identity in unknown_pitch_counts
            else (
                "REVIEW_REQUIRED"
                if requires_review
                else "NO_HIGH_LOAD_FLAG"
            )
        )

        results.append({
            "team_code": team_code,
            "pitcher_name": pitcher_name,
            "as_of_date": as_of_date.isoformat(),
            "last_appearance": (
                last_appearance.isoformat()
                if last_appearance else None
            ),
            "days_rest": days_rest,
            "appearances_last_3_days": len(recent_dates),
            "pitches_last_3_days": pitches_last_3_days,
            "consecutive_days": consecutive_days,
            "workload_status": status,
            "data_warning": (
                "투구 수가 누락된 경기 기록이 있습니다."
                if identity in unknown_pitch_counts
                else None
            ),
            "data_completeness": "NOT_VERIFIED",
        })

    return results