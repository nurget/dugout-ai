from app.agent.tool_definitions import AGENT_TOOLS
from app.tools.registry import TOOL_REGISTRY
from app.tools.schemas import (
    SearchSeasonPitchersInput,
    ComparePitchersInput,
)


def test_pitcher_tools_are_exposed_to_llm():
    tool_names = [tool["name"] for tool in AGENT_TOOLS]

    assert "search_season_pitchers" in tool_names
    assert "compare_pitchers" in tool_names

    assert len(tool_names) == len(set(tool_names))


def test_pitcher_tool_definitions_match_registry():
    schemas = {
        "search_season_pitchers": SearchSeasonPitchersInput,
        "compare_pitchers": ComparePitchersInput,
    }

    for name, expected_schema in schemas.items():
        definition = next(
            tool for tool in AGENT_TOOLS
            if tool["name"] == name
        )

        registered_schema, _ = TOOL_REGISTRY[name]

        assert registered_schema is expected_schema
        assert definition["strict"] is True

        properties = definition["parameters"]["properties"]

        assert set(properties) == set(
            expected_schema.model_fields
        )
        assert set(definition["parameters"]["required"]) == set(
            properties
        )
        assert definition["parameters"]["additionalProperties"] is False


def test_pitcher_tool_inputs_are_valid():
    search_input = SearchSeasonPitchersInput.model_validate({
        "season": 2026,
        "name": "김",
        "team": None,
    })

    compare_input = ComparePitchersInput.model_validate({
        "season": 2026,
        "first_pitcher_id": "123",
        "second_pitcher_id": "456",
        "team": None,
    })

    assert search_input.season == 2026
    assert compare_input.first_pitcher_id == "123"