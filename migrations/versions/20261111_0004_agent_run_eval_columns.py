"""Repair AgentRun evaluation columns if revision was stamped on an old schema.

Revision ID: 20261111_0004_eval_cols
Revises: 20261110_0003_agent_eval
Create Date: 2026-11-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op


revision: str = "20261111_0004_eval_cols"
down_revision: Union[str, None] = "20261110_0003_agent_eval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Offline PostgreSQL scripts use idempotent DDL. On live connections use
    # schema inspection so the repair works with stamped, partially applied DBs.
    if context.is_offline_mode():
        op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS llm_call_metrics JSON")
        op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS model_name VARCHAR(120)")
        op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS prompt_version VARCHAR(32)")
        op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS tool_schema_version VARCHAR(32)")
        return
    connection = op.get_bind()
    existing = {
        column["name"]
        for column in sa.inspect(connection).get_columns("agent_runs")
    }
    columns = (
        ("llm_call_metrics", sa.JSON()),
        ("model_name", sa.String(length=120)),
        ("prompt_version", sa.String(length=32)),
        ("tool_schema_version", sa.String(length=32)),
    )
    for name, column_type in columns:
        if name not in existing:
            op.add_column("agent_runs", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    # These columns are part of the 0003 AgentRun contract. This reconciliation
    # revision may run against databases where 0003 was stamped without DDL.
    pass
