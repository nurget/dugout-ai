
"""
KIA 2026 정규시즌 제출용 데이터 추출 및 복원.

export: 기존 DB에서 읽기만 수행한다.
import: 신규 DB에 중복 없이 데이터를 삽입한다.

기존 데이터 삭제나 테이블 초기화는 하지 않는다.
"""

import argparse
import asyncio
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import MetaData, Table, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql.sqltypes import Date, DateTime

from app.db.session import engine


TABLE_NAMES = (
    "kbo_games",
    "kbo_official_season_pitchers",
    "kbo_pitcher_appearances",
)

OUTPUT_PATH = Path("data/demo/kia_2026.json")


def load_tables(connection):
    metadata = MetaData()

    return {
        name: Table(name, metadata, autoload_with=connection)
        for name in TABLE_NAMES
    }


def export_data(connection):
    tables = load_tables(connection)

    games = tables["kbo_games"]
    appearances = tables["kbo_pitcher_appearances"]
    pitchers = tables["kbo_official_season_pitchers"]

    # KIA 등판 기록에 연결된 실제 경기만 가져온다.
    # 경기 테이블의 팀 코드 표기 차이에 의존하지 않는다.
    game_ids = select(appearances.c.game_pk).where(
        appearances.c.team_code == "HT"
    )

    game_rows = connection.execute(
        select(games).where(
            games.c.season == 2026,
            games.c.season_type == "REGULAR",
            games.c.game_pk.in_(game_ids),
        )
    ).mappings().all()

    selected_ids = [
        row["game_pk"] for row in game_rows
    ]

    appearance_rows = connection.execute(
        select(appearances).where(
            appearances.c.team_code == "HT",
            appearances.c.game_pk.in_(selected_ids),
        )
    ).mappings().all()

    pitcher_rows = connection.execute(
        select(pitchers).where(
            pitchers.c.season == 2026,
            pitchers.c.season_type == "REGULAR",
            pitchers.c.team_code == "HT",
        )
    ).mappings().all()

    return {
        "dataset": "DUGOUT_AI_KIA_DEMO",
        "season": 2026,
        "season_type": "REGULAR",
        "team_code": "HT",
        "tables": {
            "kbo_games": [dict(row) for row in game_rows],
            "kbo_pitcher_appearances": [
                dict(row) for row in appearance_rows
            ],
            "kbo_official_season_pitchers": [
                dict(row) for row in pitcher_rows
            ],
        },
    }


def convert_row(table, raw_row):
    converted = {}

    for column in table.columns:
        name = column.name

        # DB가 새로운 기본키를 자동 발급하도록 한다.
        if name == "id":
            continue

        if name not in raw_row:
            continue

        value = raw_row[name]

        if value is not None and isinstance(
            column.type, DateTime
        ):
            value = datetime.fromisoformat(value)

        elif value is not None and isinstance(
            column.type, Date
        ):
            value = date.fromisoformat(value)

        converted[name] = value

    return converted


def import_data(connection, payload):
    if (
        payload.get("dataset") != "DUGOUT_AI_KIA_DEMO"
        or payload.get("season") != 2026
        or payload.get("team_code") != "HT"
    ):
        raise ValueError("지원하지 않는 데모 데이터입니다.")

    tables = load_tables(connection)

    # 부모 경기부터 적재한 뒤 등판 기록을 적재한다.
    for name in TABLE_NAMES:
        table = tables[name]
        raw_rows = payload["tables"][name]

        for raw_row in raw_rows:
            row = convert_row(table, raw_row)

            statement = (
                pg_insert(table)
                .values(**row)
                .on_conflict_do_nothing()
            )

            connection.execute(statement)

        print(f"{name}: {len(raw_rows)}건 처리")


async def run_export(path: Path):
    async with engine.connect() as connection:
        payload = await connection.run_sync(export_data)

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=lambda value: (
                value.isoformat()
                if isinstance(value, (date, datetime))
                else str(value)
            ),
        ),
        encoding="utf-8",
    )

    print(f"데모 데이터 생성: {path}")

    for name, rows in payload["tables"].items():
        print(f"{name}: {len(rows)}건")


async def run_import(path: Path):
    if not path.is_file():
        raise FileNotFoundError(path)

    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    # 모든 테이블의 적재가 성공해야 커밋한다.
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: import_data(
                sync_connection,
                payload,
            )
        )

    print("데모 데이터 복원 완료")


async def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "action",
        choices=["export", "import"],
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=OUTPUT_PATH,
    )

    args = parser.parse_args()

    try:
        if args.action == "export":
            await run_export(args.file)
        else:
            await run_import(args.file)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())