# KBO 데이터 범위와 적재 방법

## 현재 확보한 원본

| 데이터 | 시즌 | 범위 | 상태 |
|---|---:|---|---|
| PBP 투구 원본 | 2023–2026 | 경기·타석·투구 순서, 타자/투수 ID, 구종·구속·좌표, 투구 전후 상황, 타석 결과 등 배포 파일의 원본 컬럼 | 로컬 snapshot 및 DB 적재 완료. 2026 snapshot은 3월 28일–7월 26일 범위 |
| 완료 타석 PBP | 2026 | 단일 타자·투수·결과가 확인된 타석 | 기존 DB 적재 경로 |
| 공식 시즌 투수 | 기존 기록 일부 | 투수의 제공된 시즌 지표 | 기존 적재분. 시즌/대회 범위 및 최신성은 적재 이력에서 확인 |
| 경기별 투수 등판·부하 | 기존 기록 일부 | 경기별 등판 및 투구 수 등 | 제공 파일 범위에 한함 |

PBP snapshot은 `slothman3878/kbo_playbyplay` 배포자가 [데이터 카드](https://huggingface.co/datasets/slothman3878/kbo_playbyplay)에서 CC BY 4.0으로 표시한 자료입니다. 배포자는 Naver Sports 중계 API를 원천으로 설명하지만, 원천 제공자의 상업 이용·재배포 권리는 별도 검증하지 않았습니다. 저장소는 원본 데이터 파일을 공개 Git에 포함하지 않고, 각 파일의 revision, SHA-256, 출처 URL과 라이선스 표시를 sidecar manifest에 보존합니다. 공개 또는 상업 서비스에 사용하기 전에 권리 범위를 확인해야 합니다.

## 투구 원본 다운로드

파일이 로컬에 없을 때 시즌별로 실행합니다. 다운로드는 `data/private/`에 저장하며 DB는 변경하지 않습니다.

```bash
uv run python -m scripts.fetch_kbo_pbp_snapshot --season 2023
uv run python -m scripts.fetch_kbo_pbp_snapshot --season 2024
uv run python -m scripts.fetch_kbo_pbp_snapshot --season 2025
uv run python -m scripts.fetch_kbo_pbp_snapshot --season 2026
```

## DB 적재

DB에는 2023–2026 PBP 투구 805,960행과 완료 타석 206,354건이 적재되어 있습니다. 2026은 보유 snapshot의 종료일까지만 반영됩니다. `audit_kbo_pitch_events`로 DB 적재 행 수를 다시 확인할 수 있습니다. 마이그레이션 후 파일 검증 명령을 먼저 실행합니다. 기본 동작은 검증 전용입니다.

```bash
uv run alembic upgrade head
uv run python -m scripts.import_kbo_pitch_events data/private/kbo_pbp_2023.parquet --season 2023
```

품질 요약과 시즌 범위를 확인한 후 `--apply`를 추가하면 해당 시즌의 기존 `kbo_pitch_events` snapshot을 새 snapshot으로 원자적으로 교체합니다. 중복 투구는 하나만 유지하고, 같은 식별자에 서로 다른 값이 발견되면 적재를 중단합니다. 재실행 가능한 시즌 단위 작업이며 타석 요약 테이블에는 영향을 주지 않습니다.

```bash
uv run python -m scripts.import_kbo_pitch_events data/private/kbo_pbp_2023.parquet --season 2023 --apply
uv run python -m scripts.audit_kbo_pitch_events
```

다른 시즌도 같은 방식으로 실행합니다. 별도 PBP pitch table은 원천 행을 보존하며, 타석 결과가 없는 투구도 삭제하지 않습니다.

## 빠진 기록과 다음 확보 단계

현재 PBP로 확인할 수 없는 공식 타자 누적 성적 전체, 타점·득점의 신뢰 가능한 귀속, 도루·도루실패, 수비 이닝·자살·보살·실책·병살, 포지션별 수비, 선수 등록/말소, 부상·실시간 컨디션, 구장·날씨·공인 스코어링 상세 기록은 아직 완성된 원천이 없습니다. PBP 이벤트로부터 만든 제한된 통계는 반드시 `PBP 파생`으로 구분하고 공식 시즌 누적 기록을 대체하지 않습니다.

추가 범위는 아래 순서로 확보합니다.

1. KBO 공식 API 또는 KBO의 서면 데이터 이용 승인을 요청합니다.
2. 승인이 지연되면, 타자/투수/수비/주루 항목별 재사용 권한과 attribution 요건이 명시된 공개 데이터만 추가합니다.
3. 원천별 필드 사전, 시즌·경기 범위, 갱신 시각, 결측률과 중복 검증을 기록하고 기존 필드와 비교합니다.
4. 적재된 공식 기록과 PBP 파생치를 분리해 조회하며, 추천 답변에 데이터 출처·기준일·표본 수를 표시합니다.

KBO는 [공식 약관 개정 공지](https://www.koreabaseball.com/kbo/board/notice/View.aspx?boardSe=12148)에서 공식 API 또는 사전 서면 동의 없는 대량 자동 수집과 2차 가공을 제한한다고 안내합니다. 따라서 허가가 필요한 공식 페이지를 자동으로 수집해 이 테이블에 넣지 않습니다.
