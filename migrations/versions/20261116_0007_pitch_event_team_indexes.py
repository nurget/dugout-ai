"""index pitch events for team-scoped aggregates

Revision ID: 20261116_0007_pitch_team_indexes
Revises: 20261116_0006_pitch_events
Create Date: 2026-11-16
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20261116_0007_pitch_team_indexes"
down_revision: Union[str, Sequence[str], None] = "20261116_0006_pitch_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_kbo_pitch_events_home_team_scope",
        "kbo_pitch_events",
        ["season", "home_team_code", "inning_topbot", "game_date"],
    )
    op.create_index(
        "ix_kbo_pitch_events_away_team_scope",
        "kbo_pitch_events",
        ["season", "away_team_code", "inning_topbot", "game_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_kbo_pitch_events_away_team_scope", table_name="kbo_pitch_events")
    op.drop_index("ix_kbo_pitch_events_home_team_scope", table_name="kbo_pitch_events")
