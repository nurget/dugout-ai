FINALIZE_ANALYSIS_TOOL_NAME = "finalize_analysis"

FINALIZE_ANALYSIS_DEFINITION = {
    "type": "function",
    "name": FINALIZE_ANALYSIS_TOOL_NAME,
    "description": (
        "필요한 조회와 계산이 완료되었거나 추가 Tool이 "
        "필요하지 않을 때 최종 답변 생성 단계로 전환한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
    "strict": True,
}

GET_BULLPEN_WORKLOAD_DEFINITION = {
    "type": "function",
    "name": "get_bullpen_workload",
    "description": (
        "로그인한 구단의 2026 정규시즌 투수별 "
        "최근 3일 투구 수, 연속 등판, 휴식일을 조회한다. "
        "선발·구원 역할 및 실제 등판 가능 여부는 보장하지 않는다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "as_of_date": {
                "type": "string",
                "description": (
                    "분석 기준 날짜 YYYY-MM-DD. "
                    "해당 날짜 이전 3일의 정규시즌 기록을 조회한다."
                ),
            },
        },
        "required": ["as_of_date"],
        "additionalProperties": False,
    },
    "strict": True,
}


COMPARE_BULLPEN_CANDIDATES_DEFINITION = {
    "type": "function",
    "name": "compare_bullpen_candidates",
    "description": (
        "로그인한 KBO 구단의 투수 1~5명을 2026 정규시즌 "
        "K-BB%, 표본 규모, 최근 3일 투구 부담으로 조건부 비교한다. "
        "사용자가 선수 ID를 제공하지 않았다면 "
        "search_season_pitchers로 먼저 ID를 확인한다. "
        "당일 엔트리, 선발·구원 역할, 등판 가능 여부는 검증하지 않는다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "as_of_date": {
                "type": "string",
                "description": "분석 기준일 YYYY-MM-DD",
            },
            "candidate_ids": {
                "type": "array",
                "description": "비교할 선수의 확인된 공식 ID",
                "items": {
                    "type": "string",
                },
            },
        },
        "required": [
            "as_of_date",
            "candidate_ids",
        ],
        "additionalProperties": False,
    },
    "strict": True,
}

AGENT_TOOLS = [
    FINALIZE_ANALYSIS_DEFINITION,
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
        {
        "type": "function",
        "name": "search_season_pitchers",
        "description": (
            "실제 KBO 시즌 투수 기록에서 이름으로 선수를 검색한다. "
            "투수를 비교하기 전에 이 도구로 pitcher_id를 확인한다. "
            "team은 검색 범위를 제한하는 선택 조건이다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "season": {
                    "type": "integer",
                    "description": "조회 시즌. 예: 2026",
                },
                "name": {
                    "type": "string",
                    "description": "검색할 투수 이름 또는 이름 일부",
                },
                "team": {
                    "type": ["string", "null"],
                    "description": (
                        "검색할 팀 코드 또는 null. "
                        "팀 코드는 데이터셋과 일치해야 한다."
                    ),
                },
            },
            "required": ["season", "name", "team"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "compare_pitchers",
        "description": (
            "같은 시즌의 투수 두 명을 실제 집계 기록으로 비교한다. "
            "K%, BB%, K-BB% 등을 확인한다. "
            "반드시 먼저 search_season_pitchers로 각 투수의 ID를 확인한다. "
            "해당 기록만으로 승리 확률이나 교체 효과를 단정하지 않는다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "season": {
                    "type": "integer",
                    "description": "비교 시즌. 예: 2026",
                },
                "first_pitcher_id": {
                    "type": "string",
                    "description": "첫 번째 투수 ID",
                },
                "second_pitcher_id": {
                    "type": "string",
                    "description": "두 번째 투수 ID",
                },
                "team": {
                    "type": ["string", "null"],
                    "description": (
                        "팀 범위 제한 또는 null. "
                        "서로 다른 팀 투수를 비교할 때는 null."
                    ),
                },
            },
            "required": [
                "season",
                "first_pitcher_id",
                "second_pitcher_id",
                "team",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    GET_BULLPEN_WORKLOAD_DEFINITION,
    COMPARE_BULLPEN_CANDIDATES_DEFINITION,
]
