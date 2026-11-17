"""unify KBO player profiles and team raw records

Revision ID: 20261116_0009
Revises: 20261116_0008
"""
from alembic import op
import sqlalchemy as sa

revision = "20261116_0009"
down_revision = "20261116_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("kbo_player_records", sa.Column("profile", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("kbo_player_records", sa.Column("source_urls", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("kbo_player_records", sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "kbo_team_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("season_type", sa.String(16), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("team_code", sa.String(12), nullable=False),
        sa.Column("raw_fields", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(300), nullable=False),
        sa.Column("source_urls", sa.JSON(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True)),
        sa.Column("source_batch_id", sa.String(36), sa.ForeignKey("data_import_batches.id")),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("season", "season_type", "category", "team_code", name="uq_kbo_team_record_scope"),
    )
    for column in ("season", "category", "team_code"):
        op.create_index(f"ix_kbo_team_records_{column}", "kbo_team_records", [column])


def downgrade():
    op.drop_table("kbo_team_records")
    for column in ("collected_at", "source_urls", "profile"):
        op.drop_column("kbo_player_records", column)
