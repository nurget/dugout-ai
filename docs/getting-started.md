# DUGOUT AI 처음부터 실행하기

이 문서는 프로젝트를 처음 받은 사람이 별도 설명 없이 서비스를 실행하고 주요 기능과 테스트를 확인할 수 있도록 작성했습니다. 아래 명령은 모두 프로젝트 최상위 폴더에서 시작합니다.

전체 준비에는 보통 10분 정도가 걸립니다. 실제 Agent 답변을 받으려면 OpenAI API 키가 필요하며 API 사용료가 발생할 수 있습니다.

## 1. 실행 전에 필요한 프로그램

다음 프로그램이 설치되어 있어야 합니다.

| 프로그램 | 필요한 버전 | 확인 명령 |
| --- | --- | --- |
| Python | 3.13 이상 | `python3 --version` |
| uv | 최신 버전 권장 | `uv --version` |
| Node.js | 20.19 이상 또는 22.12 이상 | `node --version` |
| Docker Desktop 또는 Docker Engine | Compose 사용 가능 버전 | `docker --version` |
| Docker Compose | Docker Compose v2 | `docker compose version` |

Python 3.13이 없다면 uv로 설치할 수 있습니다.

```bash
uv python install 3.13
```

Windows에서는 WSL2와 Docker Desktop 조합을 권장합니다. 이후 명령은 macOS, Linux, WSL의 셸을 기준으로 작성했습니다.

## 2. 압축 해제 후 프로젝트 폴더로 이동

제출 ZIP을 해제한 뒤 터미널에서 프로젝트 폴더로 이동합니다.

```bash
cd dugout-ai
```

다음 파일이 보이면 올바른 위치입니다.

```text
README.md
pyproject.toml
uv.lock
compose.yaml
app/
frontend/
migrations/
data/demo/
```

## 3. 환경 변수 준비

예시 파일을 복사합니다.

```bash
cp .env.example .env
```

`.env`에서 아래 두 값을 반드시 바꿉니다.

```dotenv
OPENAI_API_KEY=실제_OpenAI_API_키
JWT_SECRET_KEY=충분히_긴_무작위_문자열
```

JWT 비밀값은 다음 명령으로 만들 수 있습니다.

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

처음 실행할 때는 나머지 값을 그대로 사용해도 됩니다.

```dotenv
DATABASE_URL=postgresql+asyncpg://dugout:dugout_local_password@127.0.0.1:5433/dugout
OPENAI_MODEL=gpt-4.1-mini
ALLOW_PUBLIC_REGISTRATION=true
```

- `DATABASE_URL`은 `compose.yaml`의 PostgreSQL 설정과 맞춰져 있습니다.
- `ALLOW_PUBLIC_REGISTRATION=true`는 로컬 데모에서 회원가입 화면을 사용하기 위한 설정입니다.
- OpenAI 프로젝트에서 기본 모델을 사용할 수 없다면 `OPENAI_MODEL`을 사용 가능한 모델로 바꿉니다.
- `.env`에는 비밀값이 있으므로 저장소나 제출 파일에 다시 넣지 않습니다.

## 4. 백엔드 의존성 설치

잠금 파일에 기록된 버전으로 Python 패키지를 설치합니다.

```bash
uv sync --locked
```

프로젝트 안에 `.venv`가 만들어집니다. 별도로 가상환경을 활성화할 필요 없이 이후 명령 앞에 `uv run`을 붙이면 됩니다.

## 5. PostgreSQL 실행

Docker로 PostgreSQL 17을 실행합니다.

```bash
docker compose up -d
docker compose ps
```

`dugout-postgres`의 상태가 `healthy`이면 준비가 끝난 것입니다. 최초 실행에서는 이미지 다운로드 때문에 조금 더 걸릴 수 있습니다.

문제가 생기면 로그를 확인합니다.

```bash
docker compose logs postgres
```

## 6. DB 스키마와 데모 데이터 준비

먼저 Alembic으로 현재 버전의 테이블을 만듭니다.

```bash
uv run alembic upgrade head
```

그다음 Agent 흐름을 확인할 샘플 경기와 KIA 데모 데이터를 넣습니다.

```bash
uv run python -m scripts.seed
uv run python -m scripts.demo_dataset import
```

정상적으로 끝나면 대략 아래와 같은 결과를 볼 수 있습니다.

```text
샘플 데이터 생성 완료
kbo_games: 144건 처리
kbo_official_season_pitchers: 24건 처리
kbo_pitcher_appearances: 713건 처리
데모 데이터 복원 완료
```

데모 데이터 적재는 같은 명령을 다시 실행해도 중복 행을 만들지 않습니다. 번들 데이터는 KIA 2026 정규시즌 자료이므로 기능 확인용 계정도 KIA로 만드는 것이 좋습니다.

## 7. 백엔드 실행

첫 번째 터미널에서 다음 명령을 실행합니다.

```bash
uv run uvicorn app.main:app --reload
```

아래 주소로 상태를 확인합니다.

- 서버 상태: `http://127.0.0.1:8000/health`
- API 문서: `http://127.0.0.1:8000/docs`

터미널에서도 확인할 수 있습니다.

```bash
curl http://127.0.0.1:8000/health
```

정상 응답은 다음과 같습니다.

```json
{"status":"ok","service":"dugout-ai"}
```

## 8. 프론트엔드 실행

백엔드는 그대로 둔 채 두 번째 터미널을 열어 실행합니다.

```bash
cd frontend
npm ci
npm run dev
```

브라우저에서 `http://localhost:5173`을 엽니다. 개발 서버는 `/api` 요청을 `http://127.0.0.1:8000`으로 전달합니다.

## 9. 데모 계정 만들기

로그인 화면에서 회원가입 탭을 선택하고 다음 조건으로 계정을 만듭니다.

- 구단: `KIA`
- 역할: 서버가 `COACH`로 고정
- 비밀번호: 12자 이상

`ALLOW_PUBLIC_REGISTRATION=false`로 실행하고 싶다면 화면 회원가입 대신 프로젝트 최상위 폴더에서 아래 명령을 사용합니다.

```bash
uv run python -m scripts.create_demo_user \
  --username demo \
  --team KIA \
  --role COACH
```

명령을 실행하면 비밀번호를 두 번 입력하라는 안내가 나옵니다.

## 10. 주요 기능 직접 확인

### 10-1. 경기 상황 조회와 다단계 Tool 호출

AI 전술 분석 화면에 다음 질문을 입력합니다.

```text
경기 ID 1의 상태 ID 1을 조회해줘.
1루 주자는 없다고 가정하고 투구 수 기반 교체 검토도 수행해줘.
확인되지 않은 승률이나 기록은 만들지 마.
```

화면의 실행 과정에서 다음 Tool이 순서대로 보이면 정상입니다.

```text
get_game_state
simulate_pitching_decision
```

답변이 끝난 뒤 같은 대화에서 다음 질문을 보내면 저장된 대화 문맥도 확인할 수 있습니다.

```text
방금 확인한 투구 수와 교체 검토 결과만 짧게 다시 알려줘.
```

### 10-2. KIA 불펜 후보 비교

KIA 데모 데이터가 들어간 상태에서 다음 질문을 사용할 수 있습니다.

```text
2026년 8월 15일 기준으로 KIA의 전상현, 정해영, 조상우를 찾아서
시즌 K-BB%와 최근 3일 투구 부담을 비교해줘.
실제 등판 가능 여부는 단정하지 마.
```

이 흐름에서는 선수 검색, 최근 투구 부담 조회, 후보 비교 Tool을 사용할 수 있습니다. 모델의 Tool 선택은 매번 완전히 같지 않을 수 있지만, 선수 조회 범위는 로그인한 KIA 구단으로 고정됩니다.

### 10-3. 참고 데이터 화면

- 운영 현황에서 KIA의 2026 경기 목록을 확인합니다.
- 투수 기록에서 선수 이름과 K%, BB%, K-BB%를 확인합니다.
- 정규시즌 외 대회를 선택했을 때 데이터가 없으면 빈 화면이 정상일 수 있습니다. 번들 데이터는 KIA 정규시즌만 포함합니다.

## 11. 기본 테스트 실행

프로젝트 최상위 폴더에서 백엔드 테스트를 실행합니다.

```bash
uv run pytest -q
```

현재 제출본의 기준 결과는 다음과 같습니다.

```text
95 passed, 1 skipped
```

건너뛴 한 개는 실제 OpenAI API를 호출하는 선택 테스트입니다. 나머지 테스트에는 인증, 구단별 조회 제한, Agent 실행 순서, SSE, 대화 저장, DB 규칙과 계산 로직이 포함됩니다.

프론트엔드는 다음과 같이 확인합니다.

```bash
cd frontend
npm run lint
npm run build
```

두 명령 모두 오류 없이 끝나야 합니다.

## 12. 실제 OpenAI·PostgreSQL 전체 연동 테스트

이 테스트는 실제 OpenAI API를 사용하므로 비용이 발생합니다. PostgreSQL, 데모 데이터, 백엔드 서버가 모두 실행 중이어야 합니다.

프로젝트 최상위 폴더에서 실행합니다.

```bash
RUN_E2E=1 uv run pytest tests/test_e2e_agent.py -v -s
```

테스트는 다음을 한 번에 확인합니다.

1. 로그인 또는 E2E 계정 생성
2. JWT가 포함된 SSE 요청
3. `get_game_state → simulate_pitching_decision` 다단계 Tool 호출
4. 같은 대화에서 후속 질문
5. 사용자·Agent 메시지 저장
6. Agent와 Tool 실행 이력 조회

`ALLOW_PUBLIC_REGISTRATION=false`라면 먼저 `scripts.create_demo_user`로 계정을 만든 뒤 아래 환경 변수에 같은 값을 넣습니다.

```bash
E2E_USERNAME=dugout_e2e \
E2E_PASSWORD=12자_이상의_비밀번호 \
RUN_E2E=1 \
uv run pytest tests/test_e2e_agent.py -v -s
```

## 13. 소스코드가 실행되는 순서

Agent 요청 하나가 처리되는 흐름은 다음과 같습니다.

1. `app/main.py`가 FastAPI 앱을 만들고 health, 인증, 구단, Agent 라우터를 등록합니다.
2. `app/routers/auth.py`가 로그인 요청을 확인하고 JWT를 발급합니다.
3. `app/routers/agent.py`가 JWT와 대화 소유권을 확인한 뒤 SSE 응답을 시작합니다.
4. `app/agent/streaming.py`가 최근 대화와 새 질문을 OpenAI Responses API에 전달합니다.
5. 모델이 고른 Tool 이름과 인자를 `app/tools/registry.py`가 검사합니다. 선수 관련 Tool에는 모델이 만든 구단 값 대신 JWT에서 확인한 구단 값을 넣습니다.
6. `app/tools/`와 `app/services/`가 PostgreSQL 조회 또는 규칙 계산을 실행합니다.
7. Tool 결과를 모델에 다시 전달합니다. 필요한 정보가 더 있으면 같은 과정을 최대 5회 반복합니다.
8. 정보 수집이 끝나면 별도 OpenAI 호출로 최종 답변만 생성해 SSE로 전송합니다.
9. 정상 완료된 질문과 답변은 `app/repositories/conversation.py`가 저장합니다. Agent와 Tool 실행 시간·성공 여부는 별도 실행 이력에 남깁니다.
10. `frontend/src/hooks/useAgentStream.ts`가 SSE를 읽고 `frontend/src/App.tsx`가 답변, Tool 상태, 구조화된 불펜 비교 결과를 화면에 표시합니다.

처음 코드를 읽는다면 아래 순서가 이해하기 쉽습니다.

```text
app/main.py
→ app/routers/agent.py
→ app/agent/streaming.py
→ app/agent/tool_definitions.py
→ app/tools/registry.py
→ app/tools/ 및 app/services/
→ app/models/ 및 app/repositories/
→ frontend/src/hooks/useAgentStream.ts
→ frontend/src/App.tsx
```

## 14. 실행 종료와 DB 초기화

백엔드와 프론트엔드는 각 터미널에서 `Ctrl+C`로 종료합니다.

PostgreSQL 컨테이너만 멈추고 데이터를 보존하려면 다음을 실행합니다.

```bash
docker compose stop
```

컨테이너를 제거하되 DB 데이터는 보존하려면 다음을 실행합니다.

```bash
docker compose down
```

완전히 처음 상태로 되돌리려면 아래 명령을 사용합니다.

```bash
docker compose down -v
```

`down -v`는 이 프로젝트의 Docker DB 데이터를 모두 삭제합니다. 필요한 데이터가 없는지 확인한 뒤 실행해야 합니다. 초기화한 다음에는 5~6단계의 PostgreSQL 실행, Alembic 적용, 데모 데이터 적재를 다시 수행합니다.

## 15. 자주 생기는 문제

### Docker 컨테이너가 시작되지 않음

`5433` 포트를 다른 프로그램이 쓰고 있는지 확인합니다. 포트를 바꾼다면 `compose.yaml`의 포트와 `.env`의 `DATABASE_URL`을 함께 수정해야 합니다.

```bash
docker compose ps
docker compose logs postgres
```

### `AI 서비스가 설정되지 않았습니다` 또는 HTTP 503

`.env`의 `OPENAI_API_KEY`가 예시 값으로 남아 있거나 비어 있습니다. 실제 키를 넣고 백엔드를 다시 시작합니다.

### 로그인 또는 회원가입이 되지 않음

- 비밀번호가 12자 이상인지 확인합니다.
- 화면 회원가입을 사용할 때는 `.env`의 `ALLOW_PUBLIC_REGISTRATION=true`를 확인합니다.
- 이미 같은 아이디가 있다면 다른 아이디를 쓰거나 기존 계정으로 로그인합니다.

### 경기나 투수 목록이 비어 있음

`scripts.demo_dataset import`를 실행했는지 확인하고 KIA 계정으로 로그인합니다. 번들 데모에는 다른 구단의 전체 데이터가 없습니다.

### Alembic 실행 중 이미 테이블이 있다는 오류가 남

예전 방식으로 만든 Docker 볼륨을 재사용하고 있을 가능성이 큽니다. 제출본을 새로 확인하는 환경이라면 `docker compose down -v`로 로컬 DB를 지운 뒤 5~6단계를 다시 실행하는 것이 가장 단순합니다. 기존 데이터가 필요하다면 삭제하지 말고 현재 스키마를 먼저 확인해야 합니다.

### 프론트엔드에서 API 요청이 실패함

- 백엔드가 `127.0.0.1:8000`에서 실행 중인지 확인합니다.
- 프론트엔드는 `npm run dev`로 실행하고 브라우저에서는 `localhost:5173`으로 접속합니다.
- 두 터미널의 오류 로그를 함께 확인합니다.

### 백엔드 실행 시 `address already in use`가 나옴

다른 프로그램이 이미 `8000` 포트를 사용하고 있습니다. 실행 중인 다른 개발 서버를 종료한 뒤 백엔드를 다시 시작합니다. macOS와 Linux에서는 다음 명령으로 사용 중인 프로세스를 확인할 수 있습니다.

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

프론트엔드 개발 서버가 기본적으로 `127.0.0.1:8000`에 API 요청을 전달하므로, 처음 확인할 때는 백엔드 포트를 임의로 바꾸기보다 기존 8000 포트 프로세스를 확인하고 정리하는 편이 단순합니다.

## 16. 빠른 확인용 명령 모음

처음부터 한 번에 준비할 때 필요한 명령만 모으면 아래와 같습니다.

```bash
cp .env.example .env
# .env에 OPENAI_API_KEY와 JWT_SECRET_KEY 입력

uv sync --locked
docker compose up -d
uv run alembic upgrade head
uv run python -m scripts.seed
uv run python -m scripts.demo_dataset import
uv run uvicorn app.main:app --reload
```

새 터미널에서는 다음을 실행합니다.

```bash
cd frontend
npm ci
npm run dev
```

브라우저에서 `http://localhost:5173`을 열고 KIA 계정을 만든 뒤 Agent 질문을 실행하면 됩니다.
