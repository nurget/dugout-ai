"""Preserve KBO game batting sheets and starting order.

Revision ID: 20261116_0010
Revises: 20261116_0009
"""
from alembic import op
import sqlalchemy as sa

revision = "20261116_0010"
down_revision = "20261116_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kbo_game_boxscores",
        sa.Column("game_pk", sa.String(32), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_pk"], ["kbo_games.game_pk"]),
        sa.PrimaryKeyConstraint("game_pk"),
    )
    op.create_table(
        "kbo_game_lineups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_pk", sa.String(32), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("team_code", sa.String(12), nullable=False),
        sa.Column("player_id", sa.String(32), nullable=False),
        sa.Column("player_name", sa.String(120), nullable=False),
        sa.Column("batting_order", sa.Integer(), nullable=False),
        sa.Column("is_starter", sa.Boolean(), nullable=False),
        sa.Column("position", sa.String(40)),
        sa.Column("raw_fields", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("source_batch_id", sa.String(36)),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_pk"], ["kbo_games.game_pk"]),
        sa.ForeignKeyConstraint(["source_batch_id"], ["data_import_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_pk", "team_code", "player_id", name="uq_kbo_game_lineup_player"),
    )
    for name in ("game_pk", "season", "game_date", "team_code", "player_id", "source_batch_id"):
        op.create_index(f"ix_kbo_game_lineups_{name}", "kbo_game_lineups", [name])


def downgrade() -> None:
    for name in ("source_batch_id", "player_id", "team_code", "game_date", "season", "game_pk"):
        op.drop_index(f"ix_kbo_game_lineups_{name}", table_name="kbo_game_lineups")
    op.drop_table("kbo_game_lineups")
    op.drop_table("kbo_game_boxscores")
