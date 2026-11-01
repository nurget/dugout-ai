# DUGOUT AI

경기 중 투수 교체를 검토할 때 경기 상황, KBO 시즌 기록, 최근 투구 부담을 Tool Calling으로 조회하는 대화형 분석 서비스입니다. LLM이 수치를 만들지 않고 서버가 검증한 Tool 결과를 바탕으로 답변하는 구조에 초점을 맞췄습니다.

이 서비스는 교체 성공 확률이나 승률을 예측하지 않습니다. 확인된 데이터, 규칙 기반 판단, 현재 확인할 수 없는 정보를 구분해 제시합니다.

처음 프로젝트를 받은 분은 [DUGOUT AI 처음부터 실행하기](docs/getting-started.md)를 따라 하면 환경 준비부터 데모 확인, 전체 테스트까지 순서대로 실행할 수 있습니다.

![DUGOUT AI 메인 화면](docs/images/overview.png)

## 핵심 기능

- OpenAI Responses API와 strict function schema를 이용한 다단계 Tool Calling
- 실제 경기 상태, 시즌 투수 지표, 최근 3일 투구 부담 조회
- 투구 수·이닝·주자 상황에 대한 규칙 기반 교체 검토
- SSE를 통한 Tool 실행 상태와 답변 텍스트 스트리밍
- JWT 인증, 사용자별 대화 접근 제어, 대화 저장·복원
- Agent·Tool 지연시간, 토큰, 성공 여부, 중단 상태 기록
- LLM 답변과 분리된 구조화 불펜 비교 카드

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| Backend | Python 3.13, FastAPI, Pydantic |
| Database | PostgreSQL 17, SQLAlchemy 2.x Async, asyncpg |
| AI | OpenAI Responses API, Function Calling |
| Streaming | Server-Sent Events over POST |
| Frontend | React, TypeScript, Vite |
| Test | pytest, pytest-asyncio, httpx, ESLint |

시스템 구조, Agent 실행 흐름, DB ERD, 기술 선택의 장단점은 [설계 문서](docs/design.md)에 정리했습니다. 실행 절차와 소스코드 진입점은 [실행 안내서](docs/getting-started.md)에서 확인할 수 있습니다.

## 프로젝트 구조

```text
dugout-ai/
├── app/
│   ├── agent/          # Agent 프롬프트, 실행 루프, 메트릭
│   ├── core/           # 설정, JWT, 인증 의존성
│   ├── db/             # Async SQLAlchemy 세션
│   ├── models/         # 사용자, 대화, Agent 이력, KBO 데이터
│   ├── repositories/   # 대화·실행 이력 저장소
│   ├── routers/        # 인증, 인증 구단, Agent, health API
│   ├── services/       # KBO 집계·비교·추천 규칙
│   ├── simulation/     # 투수 교체 규칙 평가
│   └── tools/          # LLM Tool schema, Registry, 실행 적응 계층
├── data/demo/              # KIA 2026 로컬 데모 데이터
├── docs/                   # 아키텍처 이미지와 설계 문서
├── frontend/               # React 대시보드와 SSE 클라이언트
├── migrations/             # Alembic 버전 관리형 DB 스키마
├── scripts/                # 데모 복원, 계정 생성, KBO 적재 스크립트
└── tests/                  # 도메인·Tool·Agent·접근 제어 테스트
```

## 로컬 실행

### 1. 의존성과 환경 변수

Python 3.13, uv, Node.js, Docker가 필요합니다.

```bash
uv sync
cp .env.example .env
```

`.env`에 `OPENAI_API_KEY`를 입력하고 `JWT_SECRET_KEY`를 32자 이상의 무작위 문자열로 바꾸세요. `.env.example`의 DB 접속 정보는 `compose.yaml`과 일치합니다. `ALLOW_PUBLIC_REGISTRATION=true`는 로컬 데모용이며 운영 환경에서는 생략하거나 `false`로 설정해야 합니다.

### 2. PostgreSQL과 데모 데이터

```bash
docker compose up -d
uv run alembic upgrade head
uv run python -m scripts.seed
uv run python -m scripts.demo_dataset import
```

`seed`는 Tool Calling 예제용 경기·선수를 넣습니다. `demo_dataset import`는 KIA 2026 정규시즌 경기, 공식 시즌 투수 지표, 경기별 투구 기록을 중복 없이 복원합니다. 다른 구단 계정은 UI를 확인할 수 있지만 번들 데모 데이터로는 불펜 비교 결과가 비어 있을 수 있습니다.

### 3. Backend·Frontend

```bash
uv run uvicorn app.main:app --reload
```

별도 터미널에서:

```bash
cd frontend
npm ci
npm run dev
```

- API: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- Frontend: Vite가 출력한 주소, 기본 `http://localhost:5173`

로컬 데모에서는 회원가입 화면으로 KIA `COACH` 계정을 만들 수 있습니다. 공개 가입을 끈 환경에서는 아래처럼 관리자가 구단과 역할을 지정해 계정을 생성합니다.

```bash
uv run python -m scripts.create_demo_user --username demo --team KIA --role COACH
```

## API 계약

모든 `/api/teams/me/*`, `/api/agent/*` 요청은 `Authorization: Bearer <token>` 헤더가 필요합니다.

| Method | Endpoint | 설명 |
| --- | --- | --- |
| `GET` | `/health` | 서비스 health check |
| `POST` | `/api/auth/register` | 공개 가입이 켜진 데모 환경에서 `COACH` 계정 생성 |
| `POST` | `/api/auth/login` | JWT 발급 |
| `GET` | `/api/auth/me` | 현재 사용자 조회 |
| `GET` | `/api/teams/me` | 인증 구단·역할 조회 |
| `GET` | `/api/teams/me/games` | 인증 구단 경기 조회 |
| `GET` | `/api/teams/me/pitchers` | 인증 구단 투수 지표 조회 |
| `POST` | `/api/agent/chat/stream` | JWT, 메시지, 선택적 대화 ID를 받아 SSE 응답 |
| `GET` | `/api/agent/conversations/{id}/messages` | 소유한 대화 복원 |
| `GET` | `/api/agent/runs/{id}` | Agent·Tool 실행 이력 조회 |

### 인증된 SSE 요청

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo","password":"your-password"}' | jq -r .access_token)

curl -N -X POST http://127.0.0.1:8000/api/agent/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"message":"7회말 1사 1루, 95구인 투수의 교체를 검토해줘."}'
```

SSE는 `conversation`, `started`, `tool_start`, `tool_result`, `analysis_result`, `answer_delta`, `completed`, `error` 이벤트를 사용합니다.

## 테스트

```bash
uv run pytest -q

cd frontend
npm run lint
npm run build
```

기본 pytest는 외부 OpenAI 호출을 mock으로 대체하지만, FastAPI 요청을 통해 회원가입, JWT, SSE 이벤트, 대화 저장, Agent 실행 이력까지 연결하는 hermetic 통합 테스트를 포함합니다. 실제 PostgreSQL·OpenAI 연결까지 검증하려면 backend와 DB를 실행한 뒤 다음을 사용합니다.

```bash
RUN_E2E=1 uv run pytest tests/test_e2e_agent.py -v
```

E2E 테스트는 기본적으로 `dugout_e2e` 계정을 생성하고 JWT를 사용합니다. 필요하면 `E2E_USERNAME`, `E2E_PASSWORD`, `E2E_BASE_URL`을 지정할 수 있습니다. 실제 OpenAI API 비용이 발생합니다.

`ALLOW_PUBLIC_REGISTRATION=false`인 서버에서는 E2E 계정을 `scripts.create_demo_user`로 먼저 만들고 같은 자격 증명을 환경 변수로 전달해야 합니다. 이 테스트는 비용과 외부 서비스 의존성 때문에 기본 테스트 묶음에서는 명시적으로 제외됩니다.

## 스키마 변경

DB 스키마는 Alembic revision으로 관리합니다.

```bash
uv run alembic revision --autogenerate -m "변경 설명"
uv run alembic upgrade head
uv run alembic downgrade -1
```

이전에 `create_all()`로 만든 DB를 이어서 사용할 때는 먼저 현재 테이블이 초기 revision과 일치하는지 검증한 뒤 `uv run alembic stamp head`를 한 번만 실행합니다. 검증 없이 stamp하면 실제 스키마 차이가 숨겨질 수 있습니다.

## 데이터와 안전 범위

- 번들 데모는 KIA 2026 정규시즌 스냅샷이며 실시간 KBO 연동이 아닙니다.
- `TEAM_NAME_UNIQUE`는 구단과 이름을 기준으로 연결한 잠정 ID입니다. 동명이인이나 매핑 근거가 불충분하면 비교에서 제외합니다.
- `REVIEW_REQUIRED`는 최근 투구 부담을 추가 확인해야 한다는 신호이며 등판 불가 판정이 아닙니다.
- `NO_HIGH_LOAD_FLAG`는 조회한 기록에서 높은 부담 신호가 없다는 뜻이며 출전 가능을 보장하지 않습니다.
- 공개 가입은 기본값이 꺼져 있고, 켜더라도 클라이언트가 역할을 선택할 수 없으며 `COACH`만 생성됩니다. 다만 데모 가입에서는 구단을 직접 고르므로 운영 계정은 관리자 프로비저닝 또는 조직 초대 흐름이 필요합니다.
- 운영 배포 전에는 rate limit, SSE heartbeat, Agent 회귀 평가셋을 추가해야 합니다.
