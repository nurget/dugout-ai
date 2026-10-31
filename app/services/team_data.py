from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kbo import KboGame
from app.models.kbo_season_pitcher import KboSeasonPitcher


async def get_team_games(
    session: AsyncSession,
    team_code: str,
    season: int = 2026,
) -> list[KboGame]:
    # 팀이 홈 또는 원정으로 참가한 경기 모두 조회한다.
    statement = (
        select(KboGame)
        .where(
            KboGame.season == season,
            or_(
                KboGame.home_team_code == team_code,
                KboGame.away_team_code == team_code,
            ),
        )
        .order_by(KboGame.game_date.desc())
    )

    result = await session.execute(statement)
    return list(result.scalars().all())


async def get_team_pitchers(
    session: AsyncSession,
    team_code: str,
    season: int = 2026,
) -> list[KboSeasonPitcher]:
    statement = (
        select(KboSeasonPitcher)
        .where(
            KboSeasonPitcher.season == season,
            KboSeasonPitcher.team_code == team_code,
        )
    )

    result = await session.execute(statement)
    return list(result.scalars().all())