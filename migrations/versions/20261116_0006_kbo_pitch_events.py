"""preserve pitch-level KBO play-by-play events

Revision ID: 20261116_0006_pitch_events
Revises: 20261115_0005_rec_review
Create Date: 2026-11-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261116_0006_pitch_events"
down_revision: Union[str, Sequence[str], None] = "20261115_0005_rec_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kbo_pitch_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("game_pk", sa.String(length=32), nullable=False),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("inning", sa.Integer(), nullable=True),
        sa.Column("inning_topbot", sa.String(length=8), nullable=True),
        sa.Column("at_bat_number", sa.Integer(), nullable=False),
        sa.Column("pitch_number", sa.Integer(), nullable=False),
        sa.Column("home_team_code", sa.String(length=12), nullable=True),
        sa.Column("away_team_code", sa.String(length=12), nullable=True),
        sa.Column("batter_id", sa.String(length=32), nullable=False),
        sa.Column("batter_name", sa.String(length=120), nullable=True),
        sa.Column("pitcher_id", sa.String(length=32), nullable=False),
        sa.Column("pitcher_name", sa.String(length=120), nullable=True),
        sa.Column("pitch_result", sa.String(length=32), nullable=True),
        sa.Column("pitch_type", sa.String(length=16), nullable=True),
        sa.Column("pitch_name", sa.String(length=80), nullable=True),
        sa.Column("release_speed_kmh", sa.Float(), nullable=True),
        sa.Column("events", sa.String(length=40), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("source_batch_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["source_batch_id"], ["data_import_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "game_pk", "at_bat_number", "pitch_number",
            name="uq_kbo_pitch_event_game_ab_pitch",
        ),
    )
    for column in (
        "season", "game_pk", "game_date", "batter_id", "pitcher_id", "source_batch_id",
    ):
        op.create_index(f"ix_kbo_pitch_events_{column}", "kbo_pitch_events", [column], unique=False)


def downgrade() -> None:
    for column in ("source_batch_id", "pitcher_id", "batter_id", "game_date", "game_pk", "season"):
        op.drop_index(f"ix_kbo_pitch_events_{column}", table_name="kbo_pitch_events")
    op.drop_table("kbo_pitch_events")
