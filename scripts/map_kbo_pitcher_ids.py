
import argparse
import asyncio
import json
from collections import defaultdict
from pathlib import Path

import app.models
from sqlalchemy import select, update, text

from app.db.session import AsyncSessionLocal
from app.models.kbo import KboGame
from app.models.kbo_pitcher_appearance import KboPitcherAppearance
from app.services.data_catalog import record_import_batch
from app.models.kbo_official_season_pitcher import (
    KboOfficialSeasonPitcher,
)


async def main():
    parser = argparse.ArgumentParser(
        description="KBO 정규시즌 경기별 투수 기록에 공식 ID 매핑"
    )
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--output",
        default="data/private/pitcher_id_mapping_2026.json",
    )
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        # 공식 시즌 기록에서 팀 + 이름에 대응하는
        # 선수 ID 후보를 구성한다.
        
        official_result = await db.execute(
            text("""
                SELECT
                    team_code,
                    pitcher_name,
                    pitcher_id
                FROM kbo_official_season_pitchers
                WHERE season = :season
                  AND season_type = 'REGULAR'
                  AND pitcher_id IS NOT NULL
            """),
            {"season": args.season},
        )

        official_by_name = defaultdict(set)

        for row in official_result.mappings():
            key = (
                row["team_code"],
                row["pitcher_name"].strip(),
            )
            official_by_name[key].add(str(row["pitcher_id"]))

        appearance_result = await db.execute(
            select(
                KboPitcherAppearance.id,
                KboPitcherAppearance.game_pk,
                KboPitcherAppearance.team_code,
                KboPitcherAppearance.pitcher_name,
                KboPitcherAppearance.pitcher_id,
            )
            .join(
                KboGame,
                KboGame.game_pk == KboPitcherAppearance.game_pk,
            )
            .where(
                KboGame.season == args.season,
                KboGame.season_type == "REGULAR",
            )
        )

        appearances = [
            dict(row)
            for row in appearance_result.mappings()
        ]

        # 같은 경기·같은 팀에서 동일 이름의 선수가
        # 두 번 등장했다면, 그 이름은 자동 매핑하지 않는다.
        game_name_counts = defaultdict(int)

        for row in appearances:
            key = (
                row["game_pk"],
                row["team_code"],
                row["pitcher_name"].strip(),
            )
            game_name_counts[key] += 1

        ambiguous_names = {
            (game_pk, team_code, name)
            for (game_pk, team_code, name), count
            in game_name_counts.items()
            if count > 1
        }

        # 특정 경기에서 동명이인이 확인되었다면
        # 같은 시즌·같은 팀·같은 이름 전체를 보류한다.
        ambiguous_team_names = {
            (team_code, name)
            for _, team_code, name in ambiguous_names
        }

        updates = []
        withheld = []
        already_matched = 0

        for row in appearances:
            key = (
                row["team_code"],
                row["pitcher_name"].strip(),
            )

            candidates = official_by_name.get(key, set())

            if key in ambiguous_team_names:
                reason = "동일 경기 내 동명이인 확인"
            elif len(candidates) == 0:
                reason = "공식 시즌 선수 ID 검색 결과 없음"
            elif len(candidates) > 1:
                reason = "공식 시즌 선수 ID 후보가 여러 개"
            else:
                reason = None

            if reason:
                withheld.append({
                    "appearance_id": row["id"],
                    "game_pk": row["game_pk"],
                    "team_code": row["team_code"],
                    "pitcher_name": row["pitcher_name"],
                    "reason": reason,
                })
                continue

            pitcher_id = next(iter(candidates))
            existing_id = row["pitcher_id"]

            if existing_id is not None:
                if str(existing_id) == pitcher_id:
                    already_matched += 1
                else:
                    withheld.append({
                        "appearance_id": row["id"],
                        "game_pk": row["game_pk"],
                        "team_code": row["team_code"],
                        "pitcher_name": row["pitcher_name"],
                        "reason": "기존 선수 ID와 공식 시즌 ID 충돌",
                        "existing_id": str(existing_id),
                        "candidate_id": pitcher_id,
                    })
                continue

            updates.append({
                "appearance_id": row["id"],
                "game_pk": row["game_pk"],
                "team_code": row["team_code"],
                "pitcher_name": row["pitcher_name"],
                "pitcher_id": pitcher_id,
            })

        report = {
            "season": args.season,
            "mapping_method": "TEAM_NAME_UNIQUE_IN_SEASON",
            "identity_verified": False,
            "total_appearances": len(appearances),
            "already_matched": already_matched,
            "mapping_candidates": len(updates),
            "withheld_count": len(withheld),
            "ambiguous_team_names": [
                {"team_code": team, "pitcher_name": name}
                for team, name in sorted(ambiguous_team_names)
            ],
            "updates": updates,
            "withheld": withheld,
        }

        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print("전체 등판 기록:", len(appearances))
        print("이미 일치하는 기록:", already_matched)
        print("매핑 후보:", len(updates))
        print("매핑 보류:", len(withheld))
        print("보고서:", output)

        if not args.apply:
            print("검증 전용 — DB 변경 없음")
            return

        # 이름 기반 유일성은 확정 신원이 아니므로,
        # 이 실행 결과는 잠정 매핑임을 명시한다.
        batch = await record_import_batch(
            db,
            dataset="kbo_pitcher_appearances",
            source_name="PITCHER_ID_MAPPING",
            season=args.season,
            season_type="REGULAR",
            record_count=len(appearances),
            quality_summary={
                "mapping_method": "TEAM_NAME_UNIQUE_IN_SEASON",
                "identity_verified": False,
                "already_matched": already_matched,
                "mapping_candidates": len(updates),
                "withheld_count": len(withheld),
                "validation": "PASSED",
            },
            status="PARTIAL",
        )
        for row in updates:
            await db.execute(
                update(KboPitcherAppearance)
                .where(
                    KboPitcherAppearance.id == row["appearance_id"],
                    KboPitcherAppearance.pitcher_id.is_(None),
                )
                .values(
                    pitcher_id=row["pitcher_id"],
                    pitcher_id_source="TEAM_NAME_UNIQUE",
                    source_batch_id=batch.id,
                )
            )
        await db.commit()
        print("잠정 선수 ID 매핑 완료:", len(updates))


if __name__ == "__main__":
    asyncio.run(main())
