import { useEffect, useState } from "react";
import { api, ApiError, type CoverageStatus, type KboDataCoverage as Coverage } from "../api/client";
import { presentTeam, recordTeamCode } from "./recordDisplay";

type Props = { season: number; teamCode: string; logout: () => void };
const labels: Record<CoverageStatus, string> = { COMPLETE: "준비됨", PARTIAL: "일부만 있음", EMPTY: "데이터 없음" };
const count = (value: number) => value.toLocaleString("ko-KR");
const rate = (value: number | null) => value === null ? "확인 중" : `${value.toFixed(1)}%`;
const day = (value: string | null) => value ? value.slice(0, 10).replaceAll("-", ".") : "—";

function Status({ value }: { value: CoverageStatus }) {
  return <span className={`coverage-status coverage-status--${value.toLowerCase()}`}>{labels[value]}</span>;
}

function Progress({ value }: { value: number | null }) {
  return <div className="coverage-progress" aria-label={`데이터 커버리지 ${rate(value)}`}><i style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%` }} /></div>;
}

export function KboDataCoverage({ season, teamCode, logout }: Props) {
  const [retry, setRetry] = useState(0);
  const requestKey = `${season}:${teamCode}:${retry}`;
  const [state, setState] = useState<{ key: string; coverage: Coverage | null; error: string | null }>({ key: "", coverage: null, error: null });
  useEffect(() => {
    let active = true;
    api.kboCoverage(season, recordTeamCode(teamCode)).then((result) => active && setState({ key: requestKey, coverage: result, error: null })).catch((reason: unknown) => {
      if (!active) return;
      if (reason instanceof ApiError && reason.status === 401) logout();
      setState({ key: requestKey, coverage: null, error: reason instanceof Error ? reason.message : "데이터 상태를 불러오지 못했어요." });
    });
    return () => { active = false; };
  }, [season, teamCode, logout, retry, requestKey]);

  const busy = state.key !== requestKey;
  const coverage = busy ? null : state.coverage;
  const error = busy ? null : state.error;
  if (error) return <section className="coverage-panel coverage-panel--error"><div><strong>데이터 상태를 확인하지 못했어요</strong><p>{error}</p></div><button type="button" className="secondary" onClick={() => setRetry((value) => value + 1)}>다시 확인</button></section>;
  if (!coverage) return <section className="coverage-panel coverage-panel--loading" role="status"><div className="record-loading-dots"><i /><i /><i /></div><span>데이터 준비 상태를 확인하고 있어요</span></section>;

  const { records, schedule, boxscores, matchups } = coverage.sections;
  return <section className="coverage-panel" aria-labelledby="coverage-title">
    <header><div><p>{presentTeam(teamCode)} · {season} 시즌</p><h3 id="coverage-title">데이터 준비 상태</h3></div><Status value={coverage.overall_status} /></header>
    <div className="coverage-grid">
      <article><div className="coverage-card-title"><strong>선수·구단 기록</strong><Status value={records.status} /></div><p><b>{count(records.batter_count)}</b>명 타자 · <b>{count(records.pitcher_count)}</b>명 투수</p><small>구단 기록 {records.team_record_categories_loaded.length}/{records.team_record_categories_expected.length}개 구분 · 업데이트 {day(records.collected_at ?? records.imported_at)}</small></article>
      <article><div className="coverage-card-title"><strong>경기 일정</strong><Status value={schedule.status} /></div><p>종료 <b>{count(schedule.completed_game_count)}</b>경기 · 전체 {count(schedule.game_count)}경기</p><small>{day(schedule.date_from)} ~ {day(schedule.date_through)}</small></article>
      <article><div className="coverage-card-title"><strong>경기 기록지</strong><Status value={boxscores.status} /></div><p><b>{count(boxscores.loaded_completed_games)}</b> / {count(boxscores.expected_completed_games)}경기 · {rate(boxscores.coverage_rate)}</p><Progress value={boxscores.coverage_rate} /><small>타순·출전 기록 {count(boxscores.lineup_rows)}행</small></article>
      <article className={matchups.status === "PARTIAL" ? "coverage-card--attention" : ""}><div className="coverage-card-title"><strong>직접 맞대결 PBP</strong><Status value={matchups.status} /></div><p><b>{count(matchups.covered_completed_games)}</b> / {count(matchups.expected_completed_games)}경기 · {rate(matchups.coverage_rate)}</p><Progress value={matchups.coverage_rate} /><small>타석 {count(matchups.plate_appearances)}건 · {day(matchups.date_from)} ~ {day(matchups.date_through)}</small></article>
    </div>
    <details><summary>데이터 범위를 확인해 주세요</summary><p>{matchups.note}</p><ul>{coverage.limitations.map((item) => <li key={item}>{item}</li>)}</ul></details>
  </section>;
}
