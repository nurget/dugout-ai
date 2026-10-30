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
    {
        "type": "function",
        "name": "simulate_pitching_decision",
        "description": (
            "경기의 이닝, 아웃카운트, 투구 수, 1루 주자 여부를 기준으로 "
            "투수 유지와 교체 검토에 필요한 위험 요인을 평가한다. "
            "학습 모델이 아닌 가정 기반 규칙 평가이며 실제 승률을 계산하지 않는다. "
            "가능하면 먼저 get_game_state로 실제 경기 정보를 조회한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "inning": {
                    "type": "integer",
                    "description": "현재 이닝",
                },
                "outs": {
                    "type": "integer",
                    "description": "현재 아웃카운트",
                },
                "pitch_count": {
                    "type": "integer",
                    "description": "현재 투수의 투구 수",
                },
                "runner_on_first": {
                    "type": "boolean",
                    "description": "1루 주자 존재 여부",
                },
            },
            "required": [
                "inning",
                "outs",
                "pitch_count",
                "runner_on_first",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "calculate_re24",
        "description": (
            "플레이 전후 주자·아웃 상황과 실제 득점을 사용해 "
            "득점 기대값 변화(RE24)를 계산한다. "
            "예시 행렬을 사용하며 KBO 시즌별 실측값은 아니다. "
            "플레이 결과가 확인되지 않았다면 임의로 생성하지 않는다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "before": {
                    "type": "object",
                    "properties": {
                        "outs": {"type": "integer"},
                        "bases": {
                            "type": "string",
                            "enum": [
                                "000",
                                "100",
                                "010",
                                "110",
                                "001",
                                "101",
                                "011",
                                "111",
                            ],
                        },
                    },
                    "required": ["outs", "bases"],
                    "additionalProperties": False,
                },
                "after": {
                    "type": "object",
                    "properties": {
                        "outs": {"type": "integer"},
                        "bases": {
                            "type": "string",
                            "enum": [
                                "000",
                                "100",
                                "010",
                                "110",
                                "001",
                                "101",
                                "011",
                                "111",
                            ],
                        },
                    },
                    "required": ["outs", "bases"],
                    "additionalProperties": False,
                },
                "runs_scored": {
                    "type": "integer",
                    "description": "해당 플레이에서 발생한 득점",
                },
            },
            "required": ["before", "after", "runs_scored"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]
