import argparse
import asyncio

from app.db.session import AsyncSessionLocal
from app.repositories.agent_run import (
    count_stale_runs,
    reconcile_stale_runs,
    stale_run_cutoff,
)


async def main(minutes: int, apply: bool) -> None:
    cutoff = stale_run_cutoff(minutes)

    async with AsyncSessionLocal() as db:
        count = await count_stale_runs(db, cutoff)

        print(f"복구 기준: {minutes}분")
        print(f"복구 대상 실행: {count}건")

        if not apply:
            print("미리보기 모드입니다. DB는 변경하지 않았습니다.")
            return

        recovered = await reconcile_stale_runs(db, cutoff)

        print(f"복구 완료: {len(recovered)}건")

        for run_id in recovered:
            print(f"- {run_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="오래된 Agent RUNNING 기록 복구",
    )

    parser.add_argument(
        "--minutes",
        type=int,
        default=30,
        help="RUNNING 상태 유지 시간 기준 (기본 30분)",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="실제로 DB 상태를 변경합니다.",
    )

    args = parser.parse_args()

    asyncio.run(main(args.minutes, args.apply))