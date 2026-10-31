from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.kbo_pitching import KboPitchingAppearance
from app.services.kbo_pitching import aggregate_pitchers, DailyPitching

router = APIRouter(prefix="/api/kbo", tags=["KBO pitching"])


@router.get("/pitchers")
async def list_pitchers(team: str = Query(..., min_length=2), season: int = 2026,
                        db: AsyncSession = Depends(get_db)):
    records = (await db.execute(select(KboPitchingAppearance).where(
        KboPitchingAppearance.season == season,
        KboPitchingAppearance.team_code == team.upper(),
    ))).scalars().all()
    data = [DailyPitching(r.season, r.game_date, r.team_code, r.pitcher_name,
                          r.strikeouts, r.walks, r.batters_faced, r.outs_recorded)
            for r in records]
    return {"season": season, "team": team.upper(), "pitchers": aggregate_pitchers(data),
            "source": sorted({r.source for r in records})}
