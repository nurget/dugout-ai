
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
    if lookback_days < 1:
        raise ValueError("lookback_days는 1 이상이어야 합니다.")

    if not team_code.strip():
        raise ValueError("team_code가 필요합니다.")

    team_code = team_code.strip().upper()
    start_date = as_of_date - timedelta(days=lookback_days)

    # 같은 시즌 같은 팀에서 동명이인이 함께 출전한 이름은
    # 선수 ID 매핑 여부와 관계없이 별도 검증 전까지 보류한다.
    ambiguous_stmt = (
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

    ambiguous_names = set(
        (await db.scalars(ambiguous_stmt)).all()
    )

    stmt = (
        select(
            KboPitcherAppearance.game_pk,
            KboPitcherAppearance.pitcher_name,
            KboPitcherAppearance.pitcher_id,
            KboPitcherAppearance.pitcher_id_source,
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
            KboPitcherAppearance.id,
        )
    )

    rows = (await db.execute(stmt)).mappings().all()

    # ID가 존재하면 ID로, 없으면 이름으로 그룹을 나눈다.
    # 단, 이름만 있는 그룹은 확정적인 개인 집계를 하지 않는다.
    grouped = defaultdict(list)

    for row in rows:
        record = dict(row)
        name = record["pitcher_name"]
        pitcher_id = record["pitcher_id"]

        if name in ambiguous_names:
            key = ("ambiguous", name)
        elif pitcher_id is None:
            key = ("unidentified", name)
        else:
            key = ("identified", str(pitcher_id))

        grouped[key].append(record)

    pitchers = []

    for key, appearances in grouped.items():
        kind, identity = key
        names = {row["pitcher_name"] for row in appearances}
        sources = {
            row["pitcher_id_source"]
            for row in appearances
        }

        name = sorted(names)[0]

        # 이름 충돌이나 ID 부재가 있으면 서로 다른 사람의
        # 투구 기록을 합산하지 않는다.
        if kind != "identified" or len(names) != 1:
            pitchers.append({
                "pitcher_id": None,
                "pitcher_name": name,
                "pitcher_id_source": None,
                "workload_status": "AMBIGUOUS_IDENTITY",
                "pitches_last_3_days": None,
                "appearances_last_3_days": None,
                "consecutive_days": None,
                "days_rest": None,
                "reason": "선수 신원을 확정할 수 없습니다.",
            })
            continue

        # 같은 ID에 여러 매핑 출처가 혼재되어 있다면
        # 출처를 검토하기 전까지 분석 결과를 보류한다.
        if len(sources) != 1 or None in sources:
            pitchers.append({
                "pitcher_id": identity,
                "pitcher_name": name,
                "pitcher_id_source": None,
                "workload_status": "UNKNOWN",
                "pitches_last_3_days": None,
                "appearances_last_3_days": None,
                "consecutive_days": None,
                "days_rest": None,
                "reason": "선수 ID의 매핑 근거가 불완전합니다.",
            })
            continue

        source = next(iter(sources))

        if any(row["pitches"] is None for row in appearances):
            pitchers.append({
                "pitcher_id": identity,
                "pitcher_name": name,
                "pitcher_id_source": source,
                "workload_status": "UNKNOWN",
                "pitches_last_3_days": None,
                "appearances_last_3_days": len(appearances),
                "consecutive_days": None,
                "days_rest": None,
                "reason": "투구 수가 누락된 기록이 있습니다.",
            })
            continue

        # 동일 날짜의 복수 등판은 연속 등판 일수 계산에서
        # 한 날짜로 취급하되 등판 횟수는 따로 계산한다.
        appearance_dates = {
            row["game_date"] for row in appearances
        }

        last_date = max(appearance_dates)
        days_rest = (as_of_date - last_date).days - 1

        consecutive_days = 0
        checking = as_of_date - timedelta(days=1)

        while checking in appearance_dates:
            consecutive_days += 1
            checking -= timedelta(days=1)

        total_pitches = sum(
            row["pitches"] for row in appearances
        )

        review_required = (
            consecutive_days >= 2
            or total_pitches >= 40
        )

        pitchers.append({
            "pitcher_id": identity,
            "pitcher_name": name,
            "pitcher_id_source": source,
            "workload_status": (
                "REVIEW_REQUIRED"
                if review_required
                else "NO_HIGH_LOAD_FLAG"
            ),
            "pitches_last_3_days": total_pitches,
            "appearances_last_3_days": len(appearances),
            "appearance_days_last_3_days": len(
                appearance_dates
            ),
            "consecutive_days": consecutive_days,
            "days_rest": days_rest,
            "reason": (
                "최근 연투 또는 투구 수 부담 검토 필요"
                if review_required
                else "조회 기간에서 높은 부담 신호가 발견되지 않음"
            ),
        })

    pitchers.sort(
        key=lambda p: (
            p["pitcher_name"],
            p["pitcher_id"] or "",
        )
    )

    return {
        "team_code": team_code,
        "season": season,
        "season_type": "REGULAR",
        "as_of_date": as_of_date.isoformat(),
        "lookback_days": lookback_days,
        "availability_verified": False,
        "identity_note": (
            "TEAM_NAME_UNIQUE는 팀과 이름으로 연결한 "
            "잠정 선수 ID이며 공식 신원 검증을 의미하지 않습니다."
        ),
        "pitchers": pitchers,
    }