from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.season_pitcher import compare_pitchers, get_pitchers
from app.services.team_codes import normalize_official_team_code
from app.services.as_of_pitcher import (
    compare_pitcher_stats_as_of,
    get_pitcher_stats_as_of,
)


async def compare_pitchers_tool(
    session: AsyncSession,
    season: int,
    first_pitcher_id: str,
    second_pitcher_id: str,
    team: str | None = None,
    as_of_date: date | None = None,
) -> dict:
    if first_pitcher_id == second_pitcher_id:
        raise ValueError("서로 다른 두 투수를 선택해야 합니다.")

    if as_of_date is not None:
        if team is None:
            raise ValueError("기준일 누적 비교에는 인증된 구단 범위가 필요합니다.")
        return await compare_pitcher_stats_as_of(
            session,
            season=season,
            team_code=team,
            as_of_date=as_of_date,
            first_pitcher_id=first_pitcher_id,
            second_pitcher_id=second_pitcher_id,
        )

    # KBO official player records may only be displayed directly. Keep them
    # out of generative AI tool inputs under the written KBO usage permission.
    return await compare_pitchers(
        session,
        season=season,
        first_pitcher_id=first_pitcher_id,
        second_pitcher_id=second_pitcher_id,
        team=normalize_official_team_code(team) if team else None,
    )


async def search_season_pitchers_tool(
    session: AsyncSession,
    season: int,
    name: str,
    team: str | None = None,
    as_of_date: date | None = None,
) -> dict:
    if as_of_date is not None:
        if team is None:
            raise ValueError("기준일 누적 검색에는 인증된 구단 범위가 필요합니다.")
        as_of = await get_pitcher_stats_as_of(
            session,
            season=season,
            team_code=team,
            as_of_date=as_of_date,
        )
        needle = name.strip().casefold()
        return {
            **as_of,
            "pitchers": [
                row for row in as_of["pitchers"]
                if needle in row["pitcher_name"].casefold()
            ][:20],
            "withheld": [
                row for row in as_of["withheld"]
                if row.get("pitcher_name") and needle in row["pitcher_name"].casefold()
            ][:20],
            "note": "요청 기준일 이전 종료 경기의 등판 기록을 합산한 누적 성적입니다.",
        }

    rows = await get_pitchers(
        session,
        season=season,
        team=normalize_official_team_code(team) if team else None,
    )
    needle = name.strip().casefold()
    return {
        "pitchers": [row for row in rows if needle in row["pitcher_name"].casefold()][:20],
        "note": "PBP 파생 투수 기록입니다. KBO 공식 시즌 기록은 AI 도구에서 제외됩니다.",
    }
