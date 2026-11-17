import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { KboSchedule } from "./KboSchedule";
import { displayDate, formatWinLossDraw, numericStat, presentTeam, recordTeamCode, recordTeams, statName } from "./recordDisplay";
import "./Records.css";

type TeamRecord = { team_code: string; raw_fields: Record<string, string>; collected_at?: string | null; imported_at?: string; metrics?: Record<string, number | null> };
type Props = { logout: () => void; initialTeam: string; onPlayers: (category: "batter" | "pitcher", teamCode: string) => void };
const raw = (row: TeamRecord | undefined, ...keys: string[]) => keys.map((key) => row?.raw_fields[key]).find((value) => value !== undefined && value !== "") ?? "—";
const tableKeys = [["순위", "순위"], ["승", "승"], ["패", "패"], ["무", "무"], ["승률", "승률"], ["게임차", "게임 차"]];

export function KboTeamOverview({ logout, initialTeam, onPlayers }: Props) {
  const [team, setTeam] = useState(initialTeam);
  const [standings, setStandings] = useState<TeamRecord[]>([]);
  const [batting, setBatting] = useState<TeamRecord | undefined>();
  const [pitching, setPitching] = useState<TeamRecord | undefined>();
  const [defense, setDefense] = useState<TeamRecord | undefined>();
  const [running, setRunning] = useState<TeamRecord | undefined>();
  const [loadState, setLoadState] = useState<{ key: string; error: string | null }>({ key: "", error: null });
  const [retry, setRetry] = useState(0);
  const [section, setSection] = useState<"team" | "schedule">("team");
  const season = 2026;
  const loadKey = [team, retry].join(":");
  const busy = loadState.key !== loadKey;
  const error = busy ? null : loadState.error;
  useEffect(() => {
    let active = true;
    Promise.all([api.kboTeamRecords(season, "standings"), api.kboTeamRecords(season, "batting", recordTeamCode(team)), api.kboTeamRecords(season, "pitching", recordTeamCode(team)), api.kboTeamRecords(season, "defense", recordTeamCode(team)), api.kboTeamRecords(season, "running", recordTeamCode(team))]).then(([rank, bat, pit, def, run]) => {
      if (!active) return;
      setStandings(rank.data); setBatting(bat.data[0]); setPitching(pit.data[0]); setDefense(def.data[0]); setRunning(run.data[0]); setLoadState({ key: loadKey, error: null });
    }).catch((reason: unknown) => {
      if (!active) return;
      if (reason instanceof ApiError && reason.status === 401) logout();
      setLoadState({ key: loadKey, error: reason instanceof Error ? reason.message : "구단 기록을 불러오지 못했어요." });
    });
    return () => { active = false; };
  }, [team, logout, retry, loadKey]);
  const standing = standings.find((row) => recordTeamCode(row.team_code) === recordTeamCode(team));
  const ordered = standings.toSorted((a, b) => (numericStat(raw(a, "순위")) ?? 99) - (numericStat(raw(b, "순위")) ?? 99));
  const teamMetric = (row: TeamRecord | undefined, fields: string[]) => fields.filter((field) => row && field in row.raw_fields);
  return <>
    <header className="record-page-heading"><div><p className="eyebrow">우리 팀의 시즌을 한눈에</p><h2>구단과 경기</h2><p>팀 성적과 시즌 기록을 확인하고, 경기 일정으로 이어서 살펴보세요.</p></div><span className="record-source">{season} 시즌</span></header>
    <div className="record-page-tabs"><button type="button" className={section === "team" ? "active" : ""} onClick={() => setSection("team")}>구단 기록</button><button type="button" className={section === "schedule" ? "active" : ""} onClick={() => setSection("schedule")}>경기 일정</button></div>
    {section === "schedule" ? <KboSchedule logout={logout} initialTeam={team} /> : <>
      <div className="team-overview-select"><label>살펴볼 구단<select value={team} onChange={(event) => setTeam(event.target.value)} aria-label="살펴볼 구단">{recordTeams.filter(([code]) => code).map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label><span>정규시즌</span></div>
      {busy ? <div className="record-state" role="status"><div className="record-loading-dots"><i /><i /><i /></div><strong>구단 기록을 불러오고 있어요</strong></div> : error ? <div className="record-state record-state--error" role="alert"><strong>구단 기록을 불러오지 못했어요</strong><p>{error}</p><button type="button" className="secondary" onClick={() => setRetry((value) => value + 1)}>다시 불러오기</button></div> : <>
        <section className="team-season-card"><div className="team-season-title"><span className="team-season-mark" aria-hidden="true">{presentTeam(team)}</span><div><p>{season} 정규시즌</p><h3>{recordTeams.find(([code]) => code === team)?.[1] ?? presentTeam(team)}</h3></div>{standing && <span className="team-standing-rank"><small>{season} 순위</small>{raw(standing, "순위")}위</span>}</div>{standing ? <><div className="team-season-numbers"><div><span>승률</span><strong>{raw(standing, "승률", "WPCT")}</strong></div><div><span>승 · 패 · 무</span><strong>{raw(standing, "승", "W")} <small>·</small> {raw(standing, "패", "L")} <small>·</small> {raw(standing, "무", "D")}</strong></div><div><span>게임 차</span><strong>{raw(standing, "게임차", "게임 차", "GB")}</strong></div><div><span>최근 10경기</span><strong className="recent-results">{formatWinLossDraw(raw(standing, "최근10경기", "최근 10경기"))}</strong></div></div><p className="team-season-updated">업데이트 {displayDate(standing.collected_at ?? standing.imported_at) ?? "시각 확인 중"}</p></> : <p className="team-record-pending">이 구단의 순위 기록을 준비 중이에요.</p>}</section>
        <div className="team-skill-grid">{([["타격", "batting", batting, ["AVG", "OBP", "SLG", "OPS", "H", "HR", "R", "RBI", "SB", "BB", "SO"]], ["투구", "pitching", pitching, ["ERA", "WHIP", "IP", "SO", "BB", "SV", "HLD", "H", "HR", "R", "ER"]], ["수비", "defense", defense, ["FPCT", "E", "PO", "A", "DP", "PB", "SB", "CS", "CS%", "PKO"]], ["주루", "running", running, ["SB", "SBA", "CS", "SB%", "OOB", "PKO"]]] as const).map(([name, category, row, fields]) => <section className="team-skill-card" key={category}><header><div><p>팀 {name} 기록</p><h3>{({ 타격: "득점을 만드는 힘", 투구: "실점을 막는 힘", 수비: "아웃을 만드는 수비", 주루: "한 베이스를 더 가는 주루" })[name]}</h3></div>{(category === "batting" || category === "pitching") && <button type="button" onClick={() => onPlayers(category === "batting" ? "batter" : "pitcher", team)}>선수 보기 <span aria-hidden="true">›</span></button>}</header>{row ? <dl>{teamMetric(row, [...fields]).map((field) => <div key={field}><dt>{statName(field, category)}</dt><dd>{raw(row, field)}</dd></div>)}</dl> : <p className="team-record-pending">팀 {name} 기록을 준비 중이에요.</p>}</section>)}</div>
        <section className="league-standings"><header><div><h3>{season} 순위</h3><p>구단을 선택하면 해당 팀의 시즌 기록을 볼 수 있어요.</p></div><span>정규시즌 승패·승률</span></header>{ordered.length ? <div className="standings-scroll"><table><thead><tr><th>순위 · 구단</th>{tableKeys.slice(1).map(([key, label]) => <th key={key}>{label}</th>)}</tr></thead><tbody>{ordered.map((row) => <tr key={row.team_code} className={recordTeamCode(row.team_code) === recordTeamCode(team) ? "is-my-team" : ""}><td><button type="button" onClick={() => setTeam(({ HT: "KIA", SK: "SSG" } as Record<string, string>)[row.team_code] ?? row.team_code)}><span>{raw(row, "순위")}</span>{presentTeam(row.team_code)}</button></td>{tableKeys.slice(1).map(([key]) => <td key={key}>{raw(row, key)}</td>)}</tr>)}</tbody></table></div> : <div className="record-state"><strong>리그 순위 기록을 준비 중이에요</strong></div>}</section>
      </>}
    </>}
  </>;
}
