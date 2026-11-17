"""store KBO season player record fields without AI transformation

Revision ID: 20261116_0008
Revises: 20261116_0007
Create Date: 2026-11-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261116_0008"
down_revision: Union[str, Sequence[str], None] = "20261116_0007_pitch_team_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kbo_player_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("season_type", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("player_id", sa.String(length=32), nullable=False),
        sa.Column("player_name", sa.String(length=120), nullable=False),
        sa.Column("team_code", sa.String(length=12), nullable=False),
        sa.Column("source_url", sa.String(length=300), nullable=False),
        sa.Column("raw_fields", sa.JSON(), nullable=False),
        sa.Column("source_batch_id", sa.String(length=36), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_batch_id"], ["data_import_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "season", "season_type", "category", "player_id", "team_code",
            name="uq_kbo_player_record_scope",
        ),
    )
    for column in ("season", "category", "player_id", "player_name", "team_code", "source_batch_id"):
        op.create_index(
            f"ix_kbo_player_records_{column}",
            "kbo_player_records",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in ("source_batch_id", "team_code", "player_name", "player_id", "category", "season"):
        op.drop_index(f"ix_kbo_player_records_{column}", table_name="kbo_player_records")
    op.drop_table("kbo_player_records")
