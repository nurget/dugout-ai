
import argparse
import asyncio

from sqlalchemy import text

from app.db.session import engine


async def migrate():
    async with engine.begin() as connection:
        existing = await connection.scalar(text("""
            SELECT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid =
                    'kbo_pitcher_appearances'::regclass
                  AND conname = 'uq_kbo_pitcher_appearance_order'
            )
        """))

        if existing:
            print("이미 적용된 마이그레이션입니다.")
            return

        await connection.execute(text("""
            ALTER TABLE kbo_pitcher_appearances
            ADD COLUMN IF NOT EXISTS appearance_order INTEGER
        """))

        await connection.execute(text("""
            ALTER TABLE kbo_pitcher_appearances
            ADD COLUMN IF NOT EXISTS pitcher_id VARCHAR(32)
        """))

        await connection.execute(text("""
            WITH ordered AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY game_pk, team_code
                        ORDER BY id
                    ) AS position
                FROM kbo_pitcher_appearances
            )
            UPDATE kbo_pitcher_appearances AS target
            SET appearance_order = ordered.position
            FROM ordered
            WHERE target.id = ordered.id
              AND target.appearance_order IS NULL
        """))

        await connection.execute(text("""
            ALTER TABLE kbo_pitcher_appearances
            ALTER COLUMN appearance_order SET NOT NULL
        """))

        await connection.execute(text("""
            ALTER TABLE kbo_pitcher_appearances
            DROP CONSTRAINT IF EXISTS uq_kbo_pitcher_appearance
        """))

        await connection.execute(text("""
            ALTER TABLE kbo_pitcher_appearances
            ADD CONSTRAINT uq_kbo_pitcher_appearance_order
            UNIQUE (game_pk, team_code, appearance_order)
        """))

    print("투수 등판 기록 식별 구조 마이그레이션 완료")