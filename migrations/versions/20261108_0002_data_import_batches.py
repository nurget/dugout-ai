"""add data import provenance and agent request snapshot metadata

Revision ID: 20261108_0002
Revises: 20261101_0001
Create Date: 2026-11-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261108_0002"
down_revision: Union[str, Sequence[str], None] = "20261101_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_import_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset", sa.String(length=80), nullable=False),
        sa.Column("source_name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("freshness", sa.String(length=20), nullable=False),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("season_type", sa.String(length=20), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("quality_summary", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_data_import_batches_dataset"),
        "data_import_batches",
        ["dataset"],
        unique=False,
    )
    op.add_column("kbo_games", sa.Column("source_batch_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_kbo_games_source_batch_id"), "kbo_games", ["source_batch_id"], unique=False)
    op.create_foreign_key(
        "fk_kbo_games_source_batch_id_data_import_batches",
        "kbo_games",
        "data_import_batches",
        ["source_batch_id"],
        ["id"],
    )
    op.add_column("kbo_pitcher_appearances", sa.Column("source_batch_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_kbo_pitcher_appearances_source_batch_id"), "kbo_pitcher_appearances", ["source_batch_id"], unique=False)
    op.create_foreign_key(
        "fk_kbo_pitcher_appearances_source_batch_id_data_import_batches",
        "kbo_pitcher_appearances",
        "data_import_batches",
        ["source_batch_id"],
        ["id"],
    )
    op.add_column("agent_runs", sa.Column("as_of_date", sa.Date(), nullable=True))
    op.add_column("agent_runs", sa.Column("data_snapshot_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "data_snapshot_ids")
    op.drop_column("agent_runs", "as_of_date")
    op.drop_constraint(
        "fk_kbo_pitcher_appearances_source_batch_id_data_import_batches",
        "kbo_pitcher_appearances",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_kbo_pitcher_appearances_source_batch_id"), table_name="kbo_pitcher_appearances")
    op.drop_column("kbo_pitcher_appearances", "source_batch_id")
    op.drop_constraint(
        "fk_kbo_games_source_batch_id_data_import_batches",
        "kbo_games",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_kbo_games_source_batch_id"), table_name="kbo_games")
    op.drop_column("kbo_games", "source_batch_id")
    op.drop_index(op.f("ix_data_import_batches_dataset"), table_name="data_import_batches")
    op.drop_table("data_import_batches")
