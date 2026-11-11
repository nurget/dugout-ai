"""Store Agent version identifiers and per-call token usage.

Revision ID: 20261110_0003_agent_eval
Revises: 20261108_0002
Create Date: 2026-11-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20261110_0003_agent_eval"
down_revision: Union[str, None] = "20261108_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("llm_call_metrics", sa.JSON(), nullable=True))
    op.add_column("agent_runs", sa.Column("model_name", sa.String(length=120), nullable=True))
    op.add_column("agent_runs", sa.Column("prompt_version", sa.String(length=32), nullable=True))
    op.add_column("agent_runs", sa.Column("tool_schema_version", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "tool_schema_version")
    op.drop_column("agent_runs", "prompt_version")
    op.drop_column("agent_runs", "model_name")
    op.drop_column("agent_runs", "llm_call_metrics")
