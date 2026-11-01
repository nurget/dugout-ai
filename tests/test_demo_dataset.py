import json
from pathlib import Path

from scripts.demo_dataset import TEAM_NAMES


def test_demo_team_mapping_covers_bundled_games():
    payload = json.loads(
        Path("data/demo/kia_2026.json").read_text(encoding="utf-8")
    )
    payload_codes = {
        row[field]
        for row in payload["tables"]["kbo_games"]
        for field in ("home_team_code", "away_team_code")
    }

    assert payload_codes == TEAM_NAMES.keys()


def test_demo_team_names_are_not_empty():
    assert all(name.strip() for name in TEAM_NAMES.values())
