"""Merge existing Alembic heads and store coach recommendation reviews.

Revision ID: 20261115_0005_rec_review
Revises: 20261110_0003, 20261111_0004_eval_cols
Create Date: 2026-11-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261115_0005_rec_review"
down_revision: Union[str, Sequence[str], None] = (
    "20261110_0003",
    "20261111_0004_eval_cols",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recommendation_reviews",
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("reviewer_user_id", sa.String(length=36), nullable=False),
        sa.Column("team_code", sa.String(length=20), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("acceptable_candidate_ids", sa.JSON(), nullable=False),
        sa.Column("recommendation_snapshot", sa.JSON(), nullable=False),
        sa.Column("data_snapshot_ids", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("review_id"),
        sa.UniqueConstraint(
            "run_id",
            "reviewer_user_id",
            name="uq_recommendation_review_run_reviewer",
        ),
    )
    op.create_index(
        "ix_recommendation_reviews_run_id",
        "recommendation_reviews",
        ["run_id"],
    )
    op.create_index(
        "ix_recommendation_reviews_reviewer_user_id",
        "recommendation_reviews",
        ["reviewer_user_id"],
    )
    op.create_index(
        "ix_recommendation_reviews_team_code",
        "recommendation_reviews",
        ["team_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_reviews_team_code",
        table_name="recommendation_reviews",
    )
    op.drop_index(
        "ix_recommendation_reviews_reviewer_user_id",
        table_name="recommendation_reviews",
    )
    op.drop_index(
        "ix_recommendation_reviews_run_id",
        table_name="recommendation_reviews",
    )
    op.drop_table("recommendation_reviews")
