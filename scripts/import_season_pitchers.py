import argparse
import asyncio
from pathlib import Path

from app.db.session import AsyncSessionLocal
from app.services.season_pitcher import parse_season_pitchers, import_season_pitchers


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--source", type=str, default="")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows = parse_season_pitchers(args.path)
    print(f"검증 통과: {len(rows)}명 / 시즌: {args.season}")
    print("주의: 부분 PBP 집계이며 공식 시즌 전체 기록은 아닙니다.")
    if not args.apply:
        print("미리보기 모드: DB는 변경하지 않았습니다.")
        return
    if not args.source.strip():
        parser.error("실제 적재에는 --source 출처가 필요합니다")
    async with AsyncSessionLocal() as db:
        saved = await import_season_pitchers(db, rows, season=args.season, source=args.source)
    print(f"DB 저장 완료: {saved}명")


if __name__ == "__main__":
    asyncio.run(main())
