import argparse
import asyncio

import app.models
from sqlalchemy import text
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.services.kbo_official_pitching import fetch_official_pitchers, import_official_pitchers


async def main() -> None:
    parser = argparse.ArgumentParser(description="KBO 공식 1군 정규시즌 투수 기록을 적재합니다.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--include-postseason", action="store_true")
    args = parser.parse_args()
    rows = fetch_official_pitchers(args.season, include_postseason=args.include_postseason)
    print(f"공식 KBO 정규시즌 투수 기록: {len(rows)}명")
    if not args.apply:
        print("미리보기 모드: DB는 변경하지 않았습니다.")
        return
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text("ALTER TABLE kbo_official_season_pitchers ADD COLUMN IF NOT EXISTS season_type VARCHAR(16) NOT NULL DEFAULT 'REGULAR'"))
        await connection.execute(text("ALTER TABLE kbo_official_season_pitchers DROP CONSTRAINT IF EXISTS uq_kbo_official_season_pitcher"))
        await connection.execute(text("ALTER TABLE kbo_official_season_pitchers ADD CONSTRAINT uq_kbo_official_season_pitcher UNIQUE (season, season_type, pitcher_id, team_code)"))
        for column, kind in (("batters_faced", "INTEGER"), ("k_pct", "DOUBLE PRECISION"), ("bb_pct", "DOUBLE PRECISION"), ("k_minus_bb_pct", "DOUBLE PRECISION")):
            await connection.execute(text(f"ALTER TABLE kbo_official_season_pitchers ADD COLUMN IF NOT EXISTS {column} {kind}"))
    async with AsyncSessionLocal() as db:
        print(f"DB 저장 완료: {await import_official_pitchers(db, rows, season=args.season)}명")


if __name__ == "__main__":
    asyncio.run(main())
