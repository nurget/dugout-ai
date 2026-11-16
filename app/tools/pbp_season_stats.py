from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pbp_season_stats import search_team_batters, get_team_pbp_pitching_stats


async def search_season_batters_tool(
    session: AsyncSession,
    *,
    season: int,
    name: str,
    team: str,
    as_of_date: date,
) -> dict:
    return await search_team_batters(
        session,
        season=season,
        team_code=team,
        as_of_date=as_of_date,
        name=name,
    )


async def search_pbp_pitchers_tool(
    session: AsyncSession,
    *,
    season: int,
    name: str,
    team: str,
    as_of_date: date,
) -> dict:
    result = await get_team_pbp_pitching_stats(
        session,
        season=season,
        team_code=team,
        as_of_date=as_of_date,
        name=name,
        limit=20,
    )
    return {
        **result,
        "note": "PBP 파생 투수 지표입니다. 혼합 투수 타석은 제외하며 공식 누적 기록과 다를 수 있습니다.",
    }
