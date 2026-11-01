
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.kbo_workload import get_kbo_team_workload
from app.services.pitching_recommendation import recommend_bullpen
from app.services.team_bullpen import normalize_official_team_code


VALID_TEAMS = frozenset({
    "HT", "SS", "LG", "HH", "OB",
    "LT", "SK", "KT", "NC", "WO",
})


async def compare_verified_bullpen_candidates(
    db: AsyncSession,
    *,
    season: int,
    team_code: str,
    as_of_date: date,
    verified_candidate_ids: list[str],
) -> dict:
    """
    코치가 별도로 확인한 후보들을 실제 공식 기록으로 비교한다.

    이 함수는 후보의 실시간 엔트리나 가용성을 검증하지 않는다.
    verified_candidate_ids는 신뢰된 서버 계층에서 전달해야 한다.
    """
    team = normalize_official_team_code(
        team_code.strip().upper()
    )

    if team not in VALID_TEAMS:
        raise ValueError("지원하지 않는 KBO 구단입니다.")

    if season != 2026 or as_of_date.year != season:
        raise ValueError("현재 2026시즌 기록만 지원합니다.")

    if not verified_candidate_ids:
        raise ValueError("확인된 불펜 후보 ID가 필요합니다.")

    # 아직 전체 기록을 검증한 기간에서만 정확한
    # 최근 3일 미등판 여부를 해석한다.
    if not date(2026, 3, 31) <= as_of_date <= date(2026, 10, 13):
        raise ValueError(
            "현재 검증된 정규시즌 기록 범위 밖입니다."
        )

    season_result = await db.execute(
        text("""
            SELECT
                pitcher_id,
                pitcher_name,
                team_code,
                batters_faced,
                k_minus_bb_pct
            FROM kbo_official_season_pitchers
            WHERE season = :season
              AND season_type = 'REGULAR'
              AND team_code = :team
        """),
        {"season": season, "team": team},
    )

    season_pitchers = [
        {
            **dict(row),
            "pitcher_id": str(row["pitcher_id"]),
        }
        for row in season_result.mappings()
    ]

    workload_result = await get_kbo_team_workload(
        db,
        season=season,
        team_code=team,
        as_of_date=as_of_date,
        lookback_days=3,
    )

    workloads = list(workload_result["pitchers"])

    # 최근 3일 등판 기록이 없어도 선수의 신원이
    # 안전하게 연결되는지는 시즌 전체 기록으로 확인해야 한다.
    identity_result = await db.execute(
        text("""
            SELECT
                pitcher_id::text AS pitcher_id,
                pitcher_name,
                pitcher_id_source,
                COUNT(*) AS record_count
            FROM kbo_pitcher_appearances a
            JOIN kbo_games g ON g.game_pk = a.game_pk
            WHERE g.season = :season
              AND g.season_type = 'REGULAR'
              AND a.team_code = :team
              AND a.pitcher_id IS NOT NULL
            GROUP BY pitcher_id, pitcher_name, pitcher_id_source
        """),
        {"season": season, "team": team},
    )

    mapping_rows = identity_result.mappings().all()
    safe_ids = set()
    names_by_id = {}

    for row in mapping_rows:
        pid = row["pitcher_id"]
        names_by_id.setdefault(pid, set()).add(
            (row["pitcher_name"], row["pitcher_id_source"])
        )

    for pid, identities in names_by_id.items():
        if len(identities) == 1:
            name, source = next(iter(identities))
            if source in {"TEAM_NAME_UNIQUE", "OFFICIAL_VERIFIED"}:
                safe_ids.add(pid)

    # 같은 팀에서 동명이인이 확인된 이름은
    # ID가 잠정 매핑되었더라도 자동 복원하지 않는다.
    ambiguous_result = await db.execute(
        text("""
            SELECT DISTINCT pitcher_name
            FROM (
                SELECT a.game_pk, a.pitcher_name
                FROM kbo_pitcher_appearances a
                JOIN kbo_games g ON g.game_pk = a.game_pk
                WHERE g.season = :season
                  AND g.season_type = 'REGULAR'
                  AND a.team_code = :team
                GROUP BY a.game_pk, a.pitcher_name
                HAVING COUNT(*) > 1
            ) duplicates
        """),
        {"season": season, "team": team},
    )
    ambiguous_names = set(ambiguous_result.scalars().all())

    safe_ids = {
        pid
        for pid in safe_ids
        if next(iter(names_by_id[pid]))[0] not in ambiguous_names
    }

    # 최근 기록이 없는 선수는 0구로 처리할 수 있지만,
    # 과거 기록이 존재하고 신원 매핑이 일관된 선수만 허용한다.
    # 단, 휴식일은 이번 조회 결과만으로 계산할 수 없다.
    workloads_by_id = {
        str(row["pitcher_id"]): row
        for row in workloads
        if row.get("pitcher_id") is not None
    }

    for pitcher in season_pitchers:
        pid = pitcher["pitcher_id"]

        if pid not in safe_ids or pid in workloads_by_id:
            continue

        workloads.append({
            "pitcher_id": pid,
            "pitcher_name": pitcher["pitcher_name"],
            "workload_status": "NO_HIGH_LOAD_FLAG",
            "pitches_last_3_days": 0,
            "appearances_last_3_days": 0,
            "appearance_days_last_3_days": 0,
            "consecutive_days": 0,
            "days_rest": None,
            "pitcher_id_source": "TEAM_NAME_UNIQUE",
            "reason": (
                "최근 3일 공식 정규시즌 등판 기록 없음. "
                "실제 등판 가능 여부는 별도 확인 필요."
            ),
        })

    # 검증되지 않은 선수 ID는 추천 엔진에
    # 전달하지 않고 보류 사유를 명시한다.
    trusted_ids = [
        pid for pid in verified_candidate_ids
        if pid in safe_ids
    ]

    unverified_ids = [
        pid for pid in verified_candidate_ids
        if pid not in safe_ids
    ]

    if trusted_ids:
        result = recommend_bullpen(
            team_code=team,
            verified_candidate_ids=trusted_ids,
            season_pitchers=season_pitchers,
            workloads=workloads,
        )
    else:
        result = {
            "team_code": team,
            "ranking": [],
            "withheld": [],
            "verified_candidate_count": 0,
        }

    result["withheld"].extend(
        {
            "pitcher_id": pid,
            "reason": (
                "시즌 기록과 경기별 기록의 선수 ID 연결이 "
                "충분히 확인되지 않았습니다."
            ),
        }
        for pid in unverified_ids
    )

    result["verified_candidate_count"] = len(
        verified_candidate_ids
    )
    result["as_of_date"] = as_of_date.isoformat()
    result["season"] = season
    result["availability_source"] = (
        "코치가 별도로 확인한 후보 명단"
    )
    result["identity_note"] = (
        "TEAM_NAME_UNIQUE는 잠정 선수 식별이며 "
        "공식 고유 ID 직접 검증은 아닙니다."
    )

    return result