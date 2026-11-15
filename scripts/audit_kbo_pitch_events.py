"""Show DB counts for pitch-level PBP imports by season."""
import asyncio

from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.kbo_pitch_event import KboPitchEvent
from app.models.kbo_plate_appearance import KboPlateAppearance


async def main() -> None:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(KboPitchEvent.season, func.count())
            .group_by(KboPitchEvent.season)
            .order_by(KboPitchEvent.season)
        )
        print("dataset,season,records")
        for season, count in rows:
            print(f"pitch_events,{season},{count}")
        pa_rows = await session.execute(
            select(KboPlateAppearance.season, func.count())
            .group_by(KboPlateAppearance.season)
            .order_by(KboPlateAppearance.season)
        )
        for season, count in pa_rows:
            print(f"plate_appearances,{season},{count}")


if __name__ == "__main__":
    asyncio.run(main())
