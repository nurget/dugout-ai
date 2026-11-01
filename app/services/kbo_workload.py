
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kbo import KboGame
from app.models.kbo_pitcher_appearance import KboPitcherAppearance


async def get_kbo_team_workload(
    db: AsyncSession,
    *,
    season: int,
    team_code: str,
    as_of_date: date,
    lookback_days: int = 3,
) -> dict:
    """
    특정 구단의 기준일 이전 투구 부담을 계산한다.

    동명이인 여부는 시즌 전체에서 검사하며,
    선수 식별이 모호하면 개인별 투구 수를 합산하지 않는다.
    """
    if lookback_days < 1:
        raise ValueError("lookback_days는 1 이상이어야 합니다.")

    if not team_code.strip():
        raise ValueError("team_code가 필요합니다.")

    team_code = team_code.upper()
    start_date = as_of_date - timedelta(days=lookback_days)

    # 같은 시즌, 같은 팀, 같은 경기에서 동일 이름이
    # 두 번 나타났다면 개인 식별에 주의가 필요하다.
    ambiguous_query = (
        select(KboPitcherAppearance.pitcher_name)
        .join(
            KboGame,
            KboGame.game_pk == KboPitcherAppearance.game_pk,
        )
        .where(
            KboGame.season == season,
            KboGame.season_type == "REGULAR",
            KboPitcherAppearance.team_code == team_code,
        )
        .group_by(
            KboPitcherAppearance.game_pk,
            KboPitcherAppearance.pitcher_name,
        )
        .having(func.count(KboPitcherAppearance.id) > 1)
    )

    ambiguous_result = await db.scalars(ambiguous_query)
    ambiguous_names = set(ambiguous_result.all())

    # 경기 날짜는 KboGame에서 가져온다.
    # 기준일 당일 기록은 분석에 포함하지 않는다.
    statement = (
        select(
            KboPitcherAppearance.game_pk,
            KboPitcherAppearance.pitcher_name,
            KboPitcherAppearance.appearance_order,
            KboPitcherAppearance.pitcher_id,
            KboPitcherAppearance.pitches,
            KboGame.game_date,
        )
        .join(
            KboGame,
            KboGame.game_pk == KboPitcherAppearance.game_pk,
        )
        .where(
            KboGame.season == season,
            KboGame.season_type == "REGULAR",
            KboGame.status == "Final",
            KboPitcherAppearance.team_code == team_code,
            KboGame.game_date >= start_date,
            KboGame.game_date < as_of_date,
        )
        .order_by(
            KboGame.game_date,
            KboPitcherAppearance.appearance_order,
        )
    )

    result = await db.execute(statement)
    records = result.mappings().all()

    by_name = defaultdict(list)

    for record in records:
        by_name[record["pitcher_name"]].append(
            dict(record)
        )

    pitchers = []

    for name, appearances in sorted(by_name.items()):
        # 고유 선수 ID가 없다면 동명이인 기록은
        # 한 선수의 기록인 것처럼 합산하지 않는다.
        if name in ambiguous_names:
            pitchers.append({
                "pitcher_name": name,
                "pitcher_id": None,
                "workload_status": "AMBIGUOUS_IDENTITY",
                "pitches_last_3_days": None,
                "consecutive_days": None,
                "days_rest": None,
                "reason": "동명이인으로 개인별 기록을 확정할 수 없습니다.",
            })
            continue

        # 여러 공식 ID가 혼재해 있어도 임의로 합치지 않는다.
        known_ids = {
            row["pitcher_id"]
            for row in appearances
            if row["pitcher_id"] is not None
        }

        if len(known_ids) > 1:
            pitchers.append({
                "pitcher_name": name,
                "pitcher_id": None,
                "workload_status": "AMBIGUOUS_IDENTITY",
                "pitches_last_3_days": None,
                "consecutive_days": None,
                "days_rest": None,
                "reason": "동일 이름에 서로 다른 선수 ID가 존재합니다.",
            })
            continue

        # NULL은 0구가 아니다. 실제 투구 수가 없으면
        # 피로도를 계산할 수 없는 상태로 둔다.
        if any(row["pitches"] is None for row in appearances):
            pitchers.append({
                "pitcher_name": name,
                "pitcher_id": next(iter(known_ids), None),
                "workload_status": "UNKNOWN",
                "pitches_last_3_days": None,
                "consecutive_days": None,
                "days_rest": None,
                "reason": "경기별 투구 수가 누락되었습니다.",
            })
            continue

        total_pitches = sum(
            row["pitches"] for row in appearances
        )

        appearance_dates = {
            row["game_date"] for row in appearances
        }

        last_date = max(appearance_dates)

        # 어제 등판했다면 휴식일은 0일이다.
        days_rest = (as_of_date - last_date).days - 1

        consecutive_days = 0
        check_date = as_of_date - timedelta(days=1)

        while check_date in appearance_dates:
            consecutive_days += 1
            check_date -= timedelta(days=1)

        # 아직 3일 이전의 연속 등판 여부까지
        # 검증하지 않았으므로 조회 범위 안에서만 계산한다.
        review_required = (
            consecutive_days >= 2
            or total_pitches >= 40
        )

        pitchers.append({
            "pitcher_name": name,
            "pitcher_id": next(iter(known_ids), None),
            "workload_status": (
                "REVIEW_REQUIRED"
                if review_required
                else "NO_HIGH_LOAD_FLAG"
            ),
            "pitches_last_3_days": total_pitches,
            "appearances_last_3_days": len(appearance_dates),
            "consecutive_days": consecutive_days,
            "days_rest": days_rest,
            "reason": (
                "최근 연속 등판 또는 투구 수 부담 검토 필요"
                if review_required
                else "조회 범위에서 높은 투구 부담 신호가 발견되지 않음"
            ),
        })

    return {
        "team_code": team_code,
        "season": season,
        "as_of_date": as_of_date.isoformat(),
        "lookback_days": lookback_days,
        "season_type": "REGULAR",
        "data_scope": "저장된 정규시즌 경기별 공식 기록",
        "availability_verified": False,
        "pitchers": pitchers,
    }