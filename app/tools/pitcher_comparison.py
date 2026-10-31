from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.season_pitcher import compare_pitchers


class ComparePitchersInput(BaseModel):
    season: int = Field(ge=1982, le=2100)
    first_pitcher_id: str = Field(min_length=1)
    second_pitcher_id: str = Field(min_length=1)
    team: str | None = None


async def compare_pitchers_tool(session: AsyncSession, season: int, first_pitcher_id: str,
                                second_pitcher_id: str, team: str | None = None) -> dict:
    return await compare_pitchers(session, season=season,
                                  first_pitcher_id=first_pitcher_id,
                                  second_pitcher_id=second_pitcher_id, team=team)


class SearchSeasonPitchersInput(BaseModel):
    season: int = Field(ge=1982, le=2100)
    name: str = Field(min_length=1)
    team: str | None = None


async def search_season_pitchers_tool(
    session: AsyncSession, season: int, name: str, team: str | None = None,
) -> dict:
    from sqlalchemy import select
    from app.models.kbo_season_pitcher import KboSeasonPitcher
    from app.services.season_pitcher import present_pitcher

    query = select(KboSeasonPitcher).where(
        KboSeasonPitcher.season == season,
        KboSeasonPitcher.pitcher_name.ilike(f"%{name}%"),
    )
    if team:
        query = query.where(KboSeasonPitcher.team_code == team.upper())
    result = await session.execute(query.limit(20))
    return {"pitchers": [present_pitcher(p) for p in result.scalars()],
            "note": "2026년 부분 PBP 데이터 기반으로 검색했습니다."}
