
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kbo_official_season_pitcher import (
    KboOfficialSeasonPitcher,
)


async def get_team_official_pitchers(
    db: AsyncSession,
    *,
    season: int,
    team_code: str,
) -> list[KboOfficialSeasonPitcher]:
    """지정한 팀의 공식 정규시즌 투수 기록을 조회한다."""

    statement = (
        select(KboOfficialSeasonPitcher)
        .where(
            KboOfficialSeasonPitcher.season == season,
            KboOfficialSeasonPitcher.season_type == "REGULAR",
            KboOfficialSeasonPitcher.team_code == team_code,
        )
        .order_by(
            KboOfficialSeasonPitcher.pitcher_name,
            KboOfficialSeasonPitcher.pitcher_id,
        )
    )

    result = await db.scalars(statement)
    return list(result.all())