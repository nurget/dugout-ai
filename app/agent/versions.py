"""Stable identifiers for the instructions and tool contract used by an Agent run."""

import hashlib
import json

from app.agent.prompt import SYSTEM_PROMPT
from app.agent.tool_definitions import AGENT_TOOLS


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def agent_versions(model: str) -> dict[str, str]:
    tool_schema = json.dumps(
        AGENT_TOOLS,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "model": model,
        "prompt_version": _digest(SYSTEM_PROMPT.strip()),
        "tool_schema_version": _digest(tool_schema),
    }
