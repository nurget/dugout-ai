"""store completed KBO plate appearances for historical matchup analysis

Revision ID: 20261110_0003
Revises: 20261108_0002
Create Date: 2026-11-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261110_0003"
down_revision: Union[str, Sequence[str], None] = "20261108_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kbo_plate_appearances",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_pk", sa.String(length=32), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("at_bat_number", sa.Integer(), nullable=False),
        sa.Column("inning", sa.Integer(), nullable=True),
        sa.Column("inning_topbot", sa.String(length=8), nullable=True),
        sa.Column("batting_team_code", sa.String(length=12), nullable=False),
        sa.Column("fielding_team_code", sa.String(length=12), nullable=False),
        sa.Column("batter_id", sa.String(length=32), nullable=False),
        sa.Column("batter_name", sa.String(length=120), nullable=False),
        sa.Column("batter_stand", sa.String(length=1), nullable=True),
        sa.Column("pitcher_id", sa.String(length=32), nullable=False),
        sa.Column("pitcher_name", sa.String(length=120), nullable=False),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("source_batch_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["source_batch_id"], ["data_import_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_pk", "at_bat_number", name="uq_kbo_plate_appearance_game_ab"),
    )
    for column in (
        "game_pk", "season", "game_date", "batting_team_code", "fielding_team_code",
        "batter_id", "pitcher_id", "source_batch_id",
    ):
        op.create_index(f"ix_kbo_plate_appearances_{column}", "kbo_plate_appearances", [column], unique=False)


def downgrade() -> None:
    for column in (
        "source_batch_id", "pitcher_id", "batter_id", "fielding_team_code", "batting_team_code",
        "game_date", "season", "game_pk",
    ):
        op.drop_index(f"ix_kbo_plate_appearances_{column}", table_name="kbo_plate_appearances")
    op.drop_table("kbo_plate_appearances")
