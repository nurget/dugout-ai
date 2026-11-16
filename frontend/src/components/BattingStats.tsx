import { useEffect, useMemo, useState } from "react";
import { api, ApiError, type Batter, type TeamBattingStats } from "../api/client";

const today = () => new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const average = (value: number | null) => value === null ? "—" : value.toFixed(3).replace(/^0/, "");

export function BattingStats({ logout }: { logout: () => void }) {
  const [season, setSeason] = useState(2026);
  const [asOfDate, setAsOfDate] = useState(today);
  const [query, setQuery] = useState("");
  const [stats, setStats] = useState<TeamBattingStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const requestKey = `${season}:${asOfDate}:${retry}`;
  const loading = loadedKey !== requestKey;
  const visibleError = loadedKey === requestKey ? error : null;

  useEffect(() => {
    let active = true;
    api.batters(season, asOfDate).then((result) => {
      if (active) { setStats(result); setError(null); }
    }).catch((err) => {
      if (!active) return;
      if (err instanceof ApiError && err.status === 401) logout();
      setError(err instanceof Error ? err.message : "타자 기록을 불러오지 못했어요.");
      setStats(null);
    }).finally(() => active && setLoadedKey(requestKey));
    return () => { active = false; };
  }, [season, asOfDate, logout, requestKey, retry]);

  const rows = useMemo(() => (stats?.data ?? [])
    .filter((batter) => batter.player_name.includes(query.trim()))
    .sort((a, b) => (b.ops ?? -1) - (a.ops ?? -1)), [stats, query]);
  const allBatters = stats?.data ?? [];
  const leaders: Array<{ label: string; player: Batter | undefined; value: (player: Batter) => string }> = [
    { label: "타율", player: allBatters.toSorted((a, b) => (b.batting_average ?? -1) - (a.batting_average ?? -1))[0], value: (p) => average(p.batting_average) },
    { label: "출루율", player: allBatters.toSorted((a, b) => (b.on_base_percentage ?? -1) - (a.on_base_percentage ?? -1))[0], value: (p) => average(p.on_base_percentage) },
    { label: "장타율", player: allBatters.toSorted((a, b) => (b.slugging_percentage ?? -1) - (a.slugging_percentage ?? -1))[0], value: (p) => average(p.slugging_percentage) },
    { label: "OPS", player: allBatters.toSorted((a, b) => (b.ops ?? -1) - (a.ops ?? -1))[0], value: (p) => average(p.ops) },
  ];

  return <>
    <div className="page-head">
      <p className="eyebrow">TEAM DATA · BATTING</p>
      <div className="page-heading-row"><div><h2>타자 기록</h2><p className="muted">우리 팀 타자들의 시즌 누적 성적을 확인해요.</p></div><span className="source-badge">PBP 파생 기록</span></div>
    </div>
    <section className="filter-card" aria-label="기록 조회 조건">
      <label>시즌<select value={season} onChange={(event) => {
        const nextSeason = Number(event.target.value);
        setSeason(nextSeason);
        setAsOfDate(nextSeason === Number(today().slice(0, 4)) ? today() : `${nextSeason}-12-31`);
      }}>{[2026, 2025, 2024, 2023].map((year) => <option key={year} value={year}>{year} 시즌</option>)}</select></label>
      <label>기준일<input type="date" min={`${season}-01-01`} max={season === Number(today().slice(0, 4)) ? today() : `${season}-12-31`} value={asOfDate} onChange={(event) => setAsOfDate(event.target.value)} /></label>
      <label className="filter-search">타자 검색<input type="search" placeholder="선수 이름을 검색해요" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
      <p>기준일 경기는 제외하고 전날까지 집계해요.</p>
    </section>
    {visibleError && <div className="section-error"><strong>타자 기록을 불러오지 못했어요.</strong><span>{visibleError}</span><button className="secondary" onClick={() => setRetry((value) => value + 1)}>다시 불러오기</button></div>}
    {loading && <div className="section-state">기록을 불러오고 있어요…</div>}
    {!loading && !visibleError && stats && <>
      <div className="batting-summary">
        <div className="summary-intro"><span>시즌 기록 리더</span><strong>{stats.team_code} <small>{season}</small></strong></div>
        {leaders.map(({ label, player, value }) => <div className="leader-item" key={label}><span>{label}</span><strong>{player ? value(player) : "—"}</strong><small>{player?.player_name ?? "기록 없음"}</small></div>)}
      </div>
      <section className="panel">
        <div className="panel-title"><div><h3>{season} 시즌 타자 누적 기록</h3><p>{rows.length}명 · 기준일 {asOfDate} 전까지</p></div><span>{stats.coverage.accepted_plate_appearances.toLocaleString()} 타석</span></div>
        {rows.length ? <div className="table-wrap"><table className="batting-table"><thead><tr><th>선수명</th><th>경기</th><th>타석</th><th>타수</th><th>안타</th><th>2루타</th><th>3루타</th><th>홈런</th><th>볼넷</th><th>삼진</th><th>타율</th><th>출루율</th><th>장타율</th><th>OPS</th></tr></thead><tbody>{rows.map((batter) => <tr key={batter.player_id}><td className="batter-name">{batter.player_name}</td><td>{batter.games}</td><td>{batter.plate_appearances}</td><td>{batter.at_bats}</td><td>{batter.hits}</td><td>{batter.doubles}</td><td>{batter.triples}</td><td>{batter.home_runs}</td><td>{batter.walks}</td><td>{batter.strikeouts}</td><td>{average(batter.batting_average)}</td><td>{average(batter.on_base_percentage)}</td><td>{average(batter.slugging_percentage)}</td><td className="emphasis">{average(batter.ops)}</td></tr>)}</tbody></table></div> : <div className="empty">{query ? "검색 결과가 없어요." : "선택한 조건의 타자 기록이 없어요."}</div>}
      </section>
      <details className="data-footnote"><summary>데이터 기준과 제한 사항</summary><p>{stats.stat_definition}</p><p>데이터 범위: {stats.coverage.date_min ?? "—"} ~ {stats.coverage.date_max ?? "아직 기록 없음"} · 출처: {stats.source_name ?? "미상"}</p><ul>{stats.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></details>
    </>}
  </>;
}
