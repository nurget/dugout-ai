"""재사용 권한을 확인한 원본 JSON을 적재한다.

사용법: uv run python -m scripts.import_kbo_games path/to/2025.json
--apply를 지정하지 않으면 검증과 통계 출력만 수행한다.
"""
import argparse
import asyncio
import json
from pathlib import Path

from app.db.session import AsyncSessionLocal
from app.services.kbo_import import normalize_dataset, import_games


async def main(path: Path, apply: bool) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    games = normalize_dataset(payload)
    teams = sorted({code for game in games for code in (game.home_code, game.away_code)})
    season = games[0].season

    print(
        f"season={season} "
        f"games={len(games)} "
        f"teams={','.join(teams)}"
    )
    
    if not apply:
        print("검증만 수행했습니다. DB에 반영하려면 --apply를 추가하세요.")
        return
    async with AsyncSessionLocal() as db:
        try:
            count = await import_games(db, games, source_name=path.name)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    print(f"저장 완료: {count}경기 (기존 gamePk는 갱신)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.path, args.apply))
