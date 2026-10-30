# DUGOUT AI

**야구 경기 의사결정 분석 Agent**

경기 중 투수 교체를 고민할 때 필요한 정보를 모아 보고, 선택의 근거를 확인할 수 있는 대화형 분석 서비스입니다. 사용자가 자연어로 상황을 질문하면 LLM Agent가 필요한 도구를 선택해 경기와 선수 데이터를 조회합니다. 분석 결과는 채팅 화면에서 실시간으로 확인할 수 있습니다.

실제 경기 결과를 맞히는 예측 서비스가 아닙니다. 데이터로 확인한 사실과 분석에 사용한 가정, 현재 판단할 수 없는 부분을 구분하는 데 초점을 맞췄습니다.

![DUGOUT AI 메인 화면](docs/images/overview.png)


## 주요 기능

| 기능 | 설명 |
| --- | --- |
| 경기 정보 조회 | 경기 ID와 상태 ID를 기준으로 이닝, 아웃카운트, 투구 수 등 조회 |
| 선수 및 불펜 후보 조회 | 등록된 투수 정보와 같은 팀의 후보 목록 확인 |
| 다단계 Agent | 질문에 따라 여러 Tool을 순차 호출하고 실행 결과를 바탕으로 답변 생성 |
| 실시간 응답 | SSE를 통해 Tool 실행 상태와 LLM의 답변을 순차적으로 표시 |
| 대화 문맥 유지 | 대화 ID로 이전 질문과 답변을 불러와 후속 질문에 활용 |
| 대화 저장 및 복원 | PostgreSQL에 완료된 대화를 저장하고 화면에서 다시 조회 |
| 투수 교체 시나리오 | 투구 수, 이닝, 주자 상황을 기준으로 교체 검토 요인 평가 |

### 세이버메트릭스

주자·아웃 상태를 이용한 득점 기대값(RE)과 플레이 전후 기대값 변화(RE24) 분석을 별도 계산 모듈로 확장하고 있습니다. RE24 계산은 플레이 전후 상태와 실제 득점이 필요하며, 투수 교체 시 승률이나 기대 실점의 차이를 직접 예측하는 값은 아닙니다.

시뮬레이션의 투구 수 임계값은 분석 흐름을 보여주기 위한 규칙입니다. 선수별 실제 가용성, 최근 등판 기록, 상대 타자 성적 등이 확인되지 않으면 분석 결과에도 해당 한계를 표시합니다.

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| Backend | Python 3.13, FastAPI, Pydantic |
| Database | PostgreSQL, SQLAlchemy 2.x (Async), asyncpg |
| AI | OpenAI Responses API, Function Calling |
| Streaming | Server-Sent Events (SSE) |
| Frontend | React, TypeScript, Vite |
| Development | uv, Docker Compose |
| Test | pytest, pytest-asyncio, httpx |

## 시스템 구성

![시스템 아키텍처](docs/images/architecture.png)

Agent가 Tool 이름과 입력값을 결정하더라도 실제 실행은 백엔드에서 처리합니다. 등록된 Tool만 호출할 수 있으며, 입력값은 Pydantic으로 검증합니다. 경기 데이터 조회와 시나리오 계산을 분리해 분석 결과를 테스트할 수 있도록 구성했습니다.

### Agent 실행 흐름

<!-- Tool Calling 실행 순서 다이어그램을 추가할 위치
![Agent 실행 흐름](docs/images/agent-flow.png)
-->

1. 사용자가 경기 상황을 질문합니다.
2. 이전 대화가 있다면 PostgreSQL에서 문맥을 불러옵니다.
3. LLM이 필요한 Tool과 입력값을 결정합니다.
4. 서버가 Tool 입력을 검증한 뒤 조회 또는 계산을 수행합니다.
5. 실행 결과를 LLM에 전달하고 필요한 경우 다음 Tool을 호출합니다.
6. 생성 중인 답변은 SSE로 전송합니다.
7. 응답이 정상 완료되면 질문과 답변을 DB에 저장합니다.

## 프로젝트 구조

```text
dugout-ai/
├── app/
│   ├── agent/              # LLM 호출, Tool Calling, 스트리밍, 대화 문맥
│   ├── core/               # 환경 설정
│   ├── db/                 # DB 엔진 및 AsyncSession
│   ├── models/             # SQLAlchemy 모델
│   ├── repositories/       # 대화 저장 및 조회
│   ├── routers/            # FastAPI 엔드포인트
│   ├── schemas/            # 요청·응답 스키마
│   ├── simulation/         # 투수 교체 규칙 기반 평가
│   ├── tools/              # Tool 입력 검증 및 실행 Registry
│   ├── utils/              # SSE 이벤트 포맷
│   └── main.py             # FastAPI 앱 진입점
├── frontend/
│   └── src/
│       ├── hooks/          # SSE 수신 및 대화 상태 관리
│       └── App.tsx         # 채팅 UI
├── scripts/               # DB 초기화 및 샘플 데이터
├── tests/                 # API, Tool, Agent, 계산 로직 테스트
├── compose.yaml           # PostgreSQL 개발 환경
├── pyproject.toml          # Python 의존성
└── README.md
```

RE24 계산 모듈을 추가한 브랜치에서는 `app/sabermetrics/` 디렉터리가 포함됩니다.

## 로컬 실행

### 사전 준비

- Python 3.13 및 [uv](https://docs.astral.sh/uv/)
- Node.js, npm
- Docker 및 Docker Compose
- OpenAI API Key (별도 API 사용 요금 발생)

### 1. 저장소 및 Python 의존성

```bash
git clone <repository-url>
cd dugout-ai
uv sync
```

### 2. 환경 변수

프로젝트 루트에 `.env` 파일을 만듭니다.

```dotenv
DATABASE_URL=postgresql+asyncpg://dugout:dugout_local_password@127.0.0.1:5433/dugout
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4.1-mini
```

`.env`와 실제 API Key는 저장소에 올리지 않습니다. 모델명은 사용하는 OpenAI API 프로젝트에서 접근 가능한 모델로 변경할 수 있습니다.

### 3. PostgreSQL 실행 및 초기 데이터 생성

```bash
docker compose up -d
uv run python -m scripts.init_db
uv run python -m scripts.seed
```

`init_db`는 개발 환경에 필요한 테이블을 생성합니다. `seed`는 데모용 경기와 선수를 등록하는 스크립트입니다. 이미 데이터를 넣은 DB에서 재실행하면 중복 데이터가 발생할 수 있으므로 초기 구성 시 한 번만 실행하는 것을 권장합니다.

### 4. Backend 실행

```bash
uv run uvicorn app.main:app --reload
```

- API: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- Health Check: `http://127.0.0.1:8000/health`

### 5. Frontend 실행

별도 터미널에서 실행합니다.

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 Vite가 출력한 접속 주소(기본 `http://localhost:5173`)를 엽니다. 개발 환경에서는 Vite 프록시가 `/api` 요청을 FastAPI로 전달합니다.

## API

| Method | Endpoint | 설명 |
| --- | --- | --- |
| `GET` | `/health` | 서버 상태 확인 |
| `GET` | `/api/players` | 선수 목록 조회 |
| `GET` | `/api/games` | 경기 목록 조회 |
| `POST` | `/api/agent/chat` | Agent 분석 결과를 JSON으로 반환 |
| `POST` | `/api/agent/chat/stream` | 대화 ID와 질문을 받아 SSE 응답 반환 |
| `GET` | `/api/agent/conversations/{conversation_id}/messages` | 저장된 대화 메시지 조회 |

전체 API 요청·응답 스키마는 Swagger UI에서 확인할 수 있습니다.

### SSE 요청 예시

```bash
curl -N -X POST http://127.0.0.1:8000/api/agent/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "경기 ID 1의 상태 ID 1을 확인하고 KIA의 투수 후보를 알려줘."
  }'
```

응답은 `conversation`, `started`, `tool_start`, `tool_result`, `answer_delta`, `completed` 등의 이벤트로 전달됩니다. 후속 질문에는 첫 응답에서 받은 `conversation_id`를 함께 전송합니다.

## 테스트

```bash
# 전체 백엔드 테스트
uv run pytest -v

# 프론트엔드 빌드 확인
cd frontend
npm run build
```

Agent와 Tool은 외부 API 호출을 Mock으로 대체해 실행 흐름과 입력 검증을 확인할 수 있습니다. 실제 OpenAI API 연결, 스트리밍 출력, DB 대화 복원은 로컬 환경에서도 확인해야 합니다.

## 데이터와 분석 범위

현재 개발 환경은 샘플 경기 및 선수 데이터를 활용합니다. 실시간 KBO 경기 데이터와 연동된 서비스는 아닙니다.

투수 교체 시나리오는 이닝, 아웃카운트, 투구 수 등을 이용한 규칙 기반 평가입니다. 이는 교체 여부를 검토하는 참고 정보로 사용하며 실제 승률이나 투수의 등판 가능 여부를 보장하지 않습니다.

세이버메트릭스 분석도 지표의 정의와 데이터 출처를 구분합니다. RE24 예시 행렬을 사용할 경우 실제 KBO 시즌별 수치로 해석하지 않도록 합니다.

## 개선 예정

- 시즌별 경기 데이터로 득점 기대값 행렬 구성 및 출처 관리
- 투수 성과 지표(K-BB%, FIP 등)를 활용한 비교 분석
- Agent 실행 이력, Tool별 지연시간, 토큰 사용량 및 비용 기록
- 모델 호출 실패 유형별 대응과 전체 요청 시간 제한
- 대화 접근 권한 및 동시 요청 처리

---

DUGOUT AI는 **LLM이 분석 과정을 조정하고, 데이터 조회와 계산은 검증 가능한 백엔드 도구가 수행하도록** 설계했습니다.