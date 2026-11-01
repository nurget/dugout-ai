from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.season_pitcher import compare_pitchers


class ComparePitchersInput(BaseModel):
    season: int = Field(ge=1982, le=2100)
    first_pitcher_id: str = Field(min_length=1)
    second_pitcher_id: str = Field(min_length=1)
    team: str | None = None


async def compare_pitchers_tool(session: AsyncSession, season: int, first_pitcher_id: str,
                                second_pitcher_id: str, team: str | None = None) -> dict:
    from app.models.kbo_official_season_pitcher import KboOfficialSeasonPitcher
    rows = list((await session.execute(select(KboOfficialSeasonPitcher).where(KboOfficialSeasonPitcher.season == season, KboOfficialSeasonPitcher.season_type == "REGULAR", KboOfficialSeasonPitcher.pitcher_id.in_([first_pitcher_id, second_pitcher_id])))).scalars())
    if len(rows) == 2:
        data = [{"pitcher_id": p.pitcher_id, "pitcher_name": p.pitcher_name, "team_code": p.team_code, "games": p.games, "batters_faced": p.batters_faced, "strikeouts": p.strikeouts, "walks": p.walks, "k_pct": p.k_pct, "bb_pct": p.bb_pct, "k_minus_bb_pct": p.k_minus_bb_pct, "source": "KBO_OFFICIAL"} for p in rows]
        return {"season": season, "pitchers": data, "k_minus_bb_pct_gap": round(rows[0].k_minus_bb_pct - rows[1].k_minus_bb_pct, 2), "higher_k_minus_bb_pitcher_id": rows[0].pitcher_id if rows[0].k_minus_bb_pct > rows[1].k_minus_bb_pct else rows[1].pitcher_id}
    return await compare_pitchers(session, season=season, first_pitcher_id=first_pitcher_id, second_pitcher_id=second_pitcher_id, team=team)


class SearchSeasonPitchersInput(BaseModel):
    season: int = Field(ge=1982, le=2100)
    name: str = Field(min_length=1)
    team: str | None = None


async def search_season_pitchers_tool(
    session: AsyncSession, season: int, name: str, team: str | None = None,
) -> dict:
    from app.models.kbo_official_season_pitcher import KboOfficialSeasonPitcher

    query = select(KboOfficialSeasonPitcher).where(KboOfficialSeasonPitcher.season == season, KboOfficialSeasonPitcher.season_type == "REGULAR", KboOfficialSeasonPitcher.pitcher_name.ilike(f"%{name}%"))
    result = await session.execute(query.limit(20))
    return {"pitchers": [{"pitcher_id": p.pitcher_id, "pitcher_name": p.pitcher_name, "team_code": p.team_code, "games": p.games, "batters_faced": p.batters_faced, "strikeouts": p.strikeouts, "walks": p.walks, "k_pct": p.k_pct, "bb_pct": p.bb_pct, "k_minus_bb_pct": p.k_minus_bb_pct, "source": "KBO_OFFICIAL"} for p in result.scalars()], "note": "KBO 공식 정규시즌 기록입니다."}
