from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kbo_official_season_pitcher import KboOfficialSeasonPitcher
from app.services.season_pitcher import compare_pitchers
from app.services.team_codes import normalize_official_team_code


def present_official_pitcher(pitcher: KboOfficialSeasonPitcher) -> dict:
    return {
        "pitcher_id": pitcher.pitcher_id,
        "pitcher_name": pitcher.pitcher_name,
        "team_code": pitcher.team_code,
        "games": pitcher.games,
        "batters_faced": pitcher.batters_faced,
        "strikeouts": pitcher.strikeouts,
        "walks": pitcher.walks,
        "k_pct": pitcher.k_pct,
        "bb_pct": pitcher.bb_pct,
        "k_minus_bb_pct": pitcher.k_minus_bb_pct,
        "source": "KBO_OFFICIAL",
    }


async def compare_pitchers_tool(
    session: AsyncSession,
    season: int,
    first_pitcher_id: str,
    second_pitcher_id: str,
    team: str | None = None,
) -> dict:
    pitcher_ids = [first_pitcher_id, second_pitcher_id]
    if first_pitcher_id == second_pitcher_id:
        raise ValueError("서로 다른 두 투수를 선택해야 합니다.")

    query = select(KboOfficialSeasonPitcher).where(
        KboOfficialSeasonPitcher.season == season,
        KboOfficialSeasonPitcher.season_type == "REGULAR",
        KboOfficialSeasonPitcher.pitcher_id.in_(pitcher_ids),
    )
    if team:
        query = query.where(
            KboOfficialSeasonPitcher.team_code
            == normalize_official_team_code(team)
        )

    rows = list((await session.scalars(query)).all())
    by_id = {row.pitcher_id: row for row in rows}

    if len(rows) == 2 and all(
        pitcher_id in by_id for pitcher_id in pitcher_ids
    ):
        first, second = (by_id[pitcher_id] for pitcher_id in pitcher_ids)
        if (
            first.k_minus_bb_pct is not None
            and second.k_minus_bb_pct is not None
        ):
            difference = round(
                first.k_minus_bb_pct - second.k_minus_bb_pct,
                2,
            )
            higher_id = (
                first.pitcher_id
                if difference > 0
                else second.pitcher_id
                if difference < 0
                else None
            )
            return {
                "season": season,
                "pitchers": [
                    present_official_pitcher(first),
                    present_official_pitcher(second),
                ],
                "k_minus_bb_pct_gap": difference,
                "higher_k_minus_bb_pitcher_id": higher_id,
            }

    return await compare_pitchers(
        session,
        season=season,
        first_pitcher_id=first_pitcher_id,
        second_pitcher_id=second_pitcher_id,
        team=team,
    )


async def search_season_pitchers_tool(
    session: AsyncSession,
    season: int,
    name: str,
    team: str | None = None,
) -> dict:
    query = select(KboOfficialSeasonPitcher).where(
        KboOfficialSeasonPitcher.season == season,
        KboOfficialSeasonPitcher.season_type == "REGULAR",
        KboOfficialSeasonPitcher.pitcher_name.ilike(f"%{name.strip()}%"),
    )
    if team:
        query = query.where(
            KboOfficialSeasonPitcher.team_code
            == normalize_official_team_code(team)
        )

    result = await session.scalars(
        query.order_by(
            KboOfficialSeasonPitcher.team_code,
            KboOfficialSeasonPitcher.pitcher_name,
            KboOfficialSeasonPitcher.pitcher_id,
        ).limit(20)
    )
    return {
        "pitchers": [present_official_pitcher(row) for row in result],
        "note": "KBO 공식 정규시즌 기록입니다.",
    }
