from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kbo import KboGame
from app.models.kbo_season_pitcher import KboSeasonPitcher

PITCHER_TEAM_CODE_MAP = {
    # 계정/경기 데이터의 표준 코드와 PBP 원본 코드가 일부 다르다.
    "KIA": "HT",
    "LOT": "LT",
    "SAM": "SS",
    "HAN": "HH",
    "KIW": "WO",
    "DOO": "OB",
}

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
            KboSeasonPitcher.team_code == PITCHER_TEAM_CODE_MAP.get(
                team_code,
                team_code,
            ),
        )
    )

    result = await session.execute(statement)
    return list(result.scalars().all())
