# LLM에 노출하는 Tool 목록이다.

AGENT_TOOLS = [
    {
        "type": "function",
        "name": "get_game_state",
        "description": (
            "특정 경기의 저장된 시점 정보를 조회한다. "
            "이닝, 아웃카운트, 투구 수를 확인할 때 사용한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "game_id": {
                    "type": "integer",
                    "description": "조회할 경기 ID",
                },
                "state_id": {
                    "type": "integer",
                    "description": "조회할 경기 상태 ID",
                },
            },
            "required": ["game_id", "state_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_pitcher_status",
        "description": (
            "투수의 기본 정보를 조회한다. "
            "최근 투구 기록이나 가용 여부는 제공하지 않는다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "player_id": {
                    "type": "integer",
                    "description": "투수 선수 ID",
                },
            },
            "required": ["player_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_bullpen_options",
        "description": (
            "지정한 팀의 다른 투수 명단을 조회한다. "
            "실제 불펜 등판 가능 여부는 확인할 수 없다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "team": {
                    "type": "string",
                    "description": "팀 이름. 예: KIA",
                },
                "exclude_player_id": {
                    "type": ["integer", "null"],
                    "description": "후보에서 제외할 투수 ID 또는 null",
                },
            },
            "required": ["team", "exclude_player_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]