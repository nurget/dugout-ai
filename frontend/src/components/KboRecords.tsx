import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type KboPlayerRecord } from "../api/client";
import { KboSchedule } from "./KboSchedule";
import { TeamAvatar } from "./TeamAvatar";
import { displayDate, numericStat, presentTeam, recordTeamCode, recordTeams, statName } from "./recordDisplay";
import "./Records.css";

type Category = "batter" | "pitcher";
type Props = { logout: () => void; initialCategory?: Category; initialTeam?: string; title?: string; showSchedule?: boolean; fixedCategory?: boolean };
type Player = KboPlayerRecord & { position?: string | null; profile?: Record<string, string>; collected_at?: string | null; metrics?: Record<string, number | null> };
const pageSize = 18;
const profileLabels: Record<string, string> = { uniform_number: "등번호", position: "포지션", birth_date: "생년월일", physique: "신체조건", school: "출신 학교", career: "선수 경력", debut: "입단 정보" };
const featured: Record<Category, string[]> = { batter: ["AVG", "HR", "RBI", "OPS"], pitcher: ["ERA", "WHIP", "SO", "IP"] };
const summaries: Record<Category, Array<[string, string[]]>> = {
  batter: [["출전과 타격", ["G", "PA", "AB", "AVG", "H", "R", "RBI"]], ["장타", ["2B", "3B", "HR", "TB", "SLG", "OPS"]], ["출루와 선구", ["OBP", "BB", "IBB", "HBP", "HP", "SO", "GDP"]], ["주루와 팀 타격", ["SB", "CS", "SAC", "SF"]]],
  pitcher: [["등판과 승패", ["G", "W", "L", "WPCT", "SV", "HLD", "QS"]], ["이닝과 실점", ["IP", "ERA", "R", "ER", "CG", "SHO"]], ["상대 타자와 출루", ["TBF", "BF", "NP", "WHIP", "H", "HR", "BB", "IBB", "HBP", "HP"]], ["탈삼진과 제구", ["SO", "WP", "BK"]]],
};
const sortOptions: Record<Category, string[]> = { batter: ["PA", "AVG", "H", "HR", "RBI", "OPS", "OBP", "SLG", "SB", "선수명"], pitcher: ["IP", "ERA", "WHIP", "SO", "W", "SV", "HLD", "선수명"] };
const rateSorts: Record<Category, string[]> = { batter: ["AVG", "OPS", "OBP", "SLG"], pitcher: ["ERA", "WHIP"] };
const metricDescriptions: Record<string, string> = { AVG: "안타 ÷ 타수", OBP: "타석에서 출루한 비율", SLG: "루타 ÷ 타수", OPS: "출루율 + 장타율", ERA: "9이닝 기준 자책점", WHIP: "(안타 + 볼넷) ÷ 투구 이닝", SO: "타자는 삼진, 투수는 탈삼진", IP: "⅓과 ⅔은 각각 아웃카운트 1개와 2개예요" };
const metricKeys: Record<string, string> = { AVG: "avg", OBP: "obp", SLG: "slg", OPS: "ops", ERA: "era", WHIP: "whip", ISO: "iso" };
const valueOf = (record: Player, field: string) => {
  if (record.raw_fields[field]) return record.raw_fields[field];
  const value = record.metrics?.[metricKeys[field]];
  return value !== null && value !== undefined ? value.toFixed(["ERA", "WHIP"].includes(field) ? 2 : 3) : "—";
};

function Stat({ field, record, category, large = false }: { field: string; record: Player; category: Category; large?: boolean }) {
  return <div className={large ? "sheet-number sheet-number--large" : "sheet-number"}><span>{statName(field, category)}{statName(field, category) !== field && <small>{field}</small>}</span><strong>{valueOf(record, field)}</strong>{large && metricDescriptions[field] && <p>{metricDescriptions[field]}</p>}</div>;
}

function PlayerSheet({ record, category, season }: { record: Player; category: Category; season: number }) {
  const groups = summaries[category];
  const advanced = (category === "batter" ? [["iso", "ISO", "장타율 − 타율. 순수 장타력을 보는 지표예요."], ["k_pct", "삼진 비율", "삼진 ÷ 타석 × 100"], ["bb_pct", "볼넷 비율", "볼넷 ÷ 타석 × 100"]] : [["k_pct", "탈삼진 비율", "탈삼진 ÷ 상대 타자 × 100"], ["bb_pct", "볼넷 비율", "볼넷 ÷ 상대 타자 × 100"], ["k_minus_bb_pct", "K−BB%", "탈삼진 비율 − 볼넷 비율"]]).filter(([key]) => record.metrics?.[key] != null);
  const groupedKeys = new Set(groups.flatMap(([, fields]) => fields));
  const extraFields = Object.keys(record.raw_fields).filter((key) => !groupedKeys.has(key) && !["선수명", "팀명", "순위"].includes(key));
  const bars = (category === "batter" ? ["H", "2B", "3B", "HR"] : ["SO", "BB", "H", "HR"]).filter((key) => numericStat(record.raw_fields[key]) !== null);
  const max = Math.max(...bars.map((key) => numericStat(record.raw_fields[key]) ?? 0), 1);
  const calculated = featured[category].filter((key) => !record.raw_fields[key] && record.metrics?.[metricKeys[key]] != null);
  const profile = Object.entries(record.profile ?? {}).filter(([key, value]) => value && !["선수명", "팀명", "포지션"].includes(key));
  return <article className="player-sheet" aria-label={`${record.player_name} 선수 기록지`}>
    <header className="player-sheet-header"><TeamAvatar teamCode={record.team_code} large /><div><p>{presentTeam(record.team_code)} <span>·</span> {record.position ?? (category === "pitcher" ? "투수" : "타격 기록")}</p><h3>{record.player_name}</h3><small>{season} 정규시즌 기록지</small></div><span className="sheet-badge">{category === "batter" ? "타격" : "투구"}</span></header>
    <div className="sheet-featured">{featured[category].map((key) => <Stat key={key} field={key} record={record} category={category} large />)}</div>
    <div className="sheet-groups">{groups.map(([title, fields]) => {
      const present = fields.filter((key) => valueOf(record, key) !== "—");
      return present.length ? <section className="sheet-group" key={title}><h4>{title}</h4><dl>{present.map((key) => <div key={key}><dt>{statName(key, category)}<small>{key}</small></dt><dd>{valueOf(record, key)}</dd></div>)}</dl></section> : null;
    })}</div>
    {advanced.length > 0 && <section className="sheet-advanced"><h4>기록으로 살펴본 지표</h4><p>원본 기록을 정해진 산식으로 계산했어요.</p><dl>{advanced.map(([key, label, description]) => <div key={key}><dt>{label}</dt><dd>{record.metrics?.[key]?.toFixed(key === "iso" ? 3 : 1)}{key !== "iso" && "%"}</dd><small>{description}</small></div>)}</dl></section>}
    {bars.length > 0 && <section className="sheet-chart"><h4>{category === "batter" ? "타격 기록 한눈에 보기" : "상대 타자 결과 한눈에 보기"}</h4><p>각 항목의 실제 누적 횟수예요.</p>{bars.map((key) => <div className="sheet-bar" key={key}><span>{statName(key, category)}</span><div><i style={{ width: `${((numericStat(record.raw_fields[key]) ?? 0) / max) * 100}%` }} /></div><strong>{valueOf(record, key)}</strong></div>)}</section>}
    {(profile.length > 0 || extraFields.length > 0) && <details className="sheet-additional"><summary>선수 정보와 추가 기록 보기</summary><dl>{profile.map(([key, value]) => <div key={`profile-${key}`}><dt>{profileLabels[key] ?? key}</dt><dd>{value}</dd></div>)}{extraFields.map((key) => <div key={key}><dt>{statName(key, category)}</dt><dd>{valueOf(record, key)}</dd></div>)}</dl></details>}
    {calculated.length > 0 && <p className="sheet-calculation-note">{calculated.join(" · ")}는 원본 기록으로 계산한 지표예요.</p>}
    <footer className="sheet-footer">{displayDate(record.collected_at ?? record.imported_at) && <time>업데이트 {displayDate(record.collected_at ?? record.imported_at)}</time>}</footer>
  </article>;
}

export function KboRecords({ logout, initialCategory = "batter", initialTeam = "", title, showSchedule = false, fixedCategory = false }: Props) {
  const [view, setView] = useState<"players" | "schedule">("players");
  const [category, setCategory] = useState<Category>(initialCategory);
  const [season, setSeason] = useState(2026);
  const [team, setTeam] = useState(initialTeam);
  const [query, setQuery] = useState("");
  const [records, setRecords] = useState<Player[]>([]);
  const [loadState, setLoadState] = useState<{ key: string; error: string | null }>({ key: "", error: null });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sort, setSort] = useState(initialCategory === "batter" ? "PA" : "IP");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [minimum, setMinimum] = useState(0);
  const [qualifiedOnly, setQualifiedOnly] = useState(false);
  const [includePitchers, setIncludePitchers] = useState(false);
  const [display, setDisplay] = useState<"cards" | "table">("cards");
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const sheetRef = useRef<HTMLDivElement>(null);
  const loadKey = [season, category, team, includePitchers, retry].join(":");
  const busy = loadState.key !== loadKey;
  const error = busy ? null : loadState.error;

  useEffect(() => {
    let active = true;
    api.kboPlayerRecords(season, "REGULAR", category, team ? recordTeamCode(team) : undefined, undefined, includePitchers).then((response) => {
      if (!active) return;
      setRecords(response.data); setSelectedId(null); setPage(1); setLoadState({ key: loadKey, error: null });
    }).catch((reason: unknown) => {
      if (!active) return;
      if (reason instanceof ApiError && reason.status === 401) logout();
      setLoadState({ key: loadKey, error: reason instanceof Error ? reason.message : "기록을 불러오지 못했어요." });
    });
    return () => { active = false; };
  }, [category, season, team, includePitchers, retry, logout, loadKey]);

  const visible = useMemo(() => records.filter((record) => record.player_name.includes(query.trim()) && (!qualifiedOnly || record.qualification?.is_qualified === true) && (numericStat(record.raw_fields[category === "batter" ? "PA" : "IP"]) ?? 0) >= minimum).toSorted((a, b) => {
    const aValue = sort === "선수명" ? a.player_name : valueOf(a, sort);
    const bValue = sort === "선수명" ? b.player_name : valueOf(b, sort);
    const aNumber = numericStat(aValue), bNumber = numericStat(bValue);
    if (aNumber === null && bNumber !== null) return 1;
    if (aNumber !== null && bNumber === null) return -1;
    const order = aNumber !== null && bNumber !== null ? aNumber - bNumber : aValue.localeCompare(bValue, "ko-KR");
    return (sortDirection === "desc" ? -order : order) || a.player_name.localeCompare(b.player_name, "ko-KR");
  }), [records, query, category, minimum, qualifiedOnly, sort, sortDirection]);
  const selected = visible.find((record) => `${record.player_id}-${record.team_code}` === selectedId) ?? visible[0];
  const pageCount = Math.ceil(visible.length / pageSize);
  const currentPage = Math.min(page, pageCount || 1);
  const pageRows = visible.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const availableSorts = sortOptions[category].filter((key) => key === "선수명" || records.some((record) => valueOf(record, key) !== "—"));
  const chooseCategory = (next: Category) => { setCategory(next); setSort(next === "batter" ? "PA" : "IP"); setSortDirection("desc"); setMinimum(0); setQualifiedOnly(false); setPage(1); };
  const chooseSort = (next: string) => { setSort(next); setSortDirection(next === "선수명" || next === "ERA" || next === "WHIP" ? "asc" : "desc"); setQualifiedOnly(rateSorts[category].includes(next)); setPage(1); };
  const thresholds = [...new Set(records.map((record) => category === "batter" ? record.qualification?.min_plate_appearances : record.qualification?.min_innings).filter((value): value is number => value != null))].sort((a, b) => a - b);
  const thresholdLabel = thresholds.length === 1 ? `${thresholds[0]}${category === "batter" ? "타석" : "이닝"} 이상` : "구단별 경기 수에 따른 기준";
  const choosePlayer = (record: Player) => { setSelectedId(`${record.player_id}-${record.team_code}`); if (window.matchMedia("(max-width: 1040px)").matches) sheetRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); };
  const tableColumns = [...new Set([category === "batter" ? "PA" : "IP", ...featured[category]])];

  return <>
    <header className="record-page-heading"><div><p className="eyebrow">선수의 기록을 한눈에</p><h2>{title ?? "KBO 선수 기록"}</h2><p>선수를 선택하면 핵심 지표부터 세부 기록까지 한 장으로 볼 수 있어요.</p></div></header>
    {showSchedule && <div className="record-page-tabs" aria-label="기록 종류"><button type="button" className={view === "players" ? "active" : ""} onClick={() => setView("players")}>선수 기록</button><button type="button" className={view === "schedule" ? "active" : ""} onClick={() => setView("schedule")}>경기 일정</button></div>}
    {view === "schedule" ? <KboSchedule logout={logout} initialTeam={initialTeam} /> : <>
      <section className="player-find" aria-label="선수 기록 검색 조건"><div className="player-find-top">{fixedCategory ? <h3 className="player-category-title">{category === "batter" ? "타격 기록 찾기" : "투구 기록 찾기"}</h3> : <div className="record-control-group" aria-label="기록 구분"><button type="button" aria-pressed={category === "batter"} className={category === "batter" ? "active" : ""} onClick={() => chooseCategory("batter")}>타자 기록</button><button type="button" aria-pressed={category === "pitcher"} className={category === "pitcher" ? "active" : ""} onClick={() => chooseCategory("pitcher")}>투수 기록</button></div>}<label className="record-compact-label">시즌<select aria-label="기록 시즌" value={season} onChange={(event) => setSeason(Number(event.target.value))}>{[2026].map((year) => <option key={year} value={year}>{year} 정규시즌</option>)}</select></label></div><div className="player-find-bottom"><label className="player-search"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg><input type="search" placeholder="궁금한 선수 이름을 검색하세요" aria-label="선수 이름 검색" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} /></label><select aria-label="기록 구단" value={team} onChange={(event) => setTeam(event.target.value)}>{recordTeams.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select><select aria-label={category === "batter" ? "최소 타석" : "최소 이닝"} value={minimum} onChange={(event) => { setMinimum(Number(event.target.value)); setPage(1); }}><option value={0}>{category === "batter" ? "타석 제한 없음" : "이닝 제한 없음"}</option>{(category === "batter" ? [1, 50, 100, 300] : [1, 10, 30, 100]).map((value) => <option key={value} value={value}>{value}{category === "batter" ? "타석" : "이닝"} 이상</option>)}</select></div>{category === "batter" && <label className="pitcher-batting-toggle"><input type="checkbox" checked={includePitchers} onChange={(event) => setIncludePitchers(event.target.checked)} />투수의 타격 기록도 포함하기</label>}</section>
      {!busy && !error && records.length > 0 && <div className="player-qualification"><label><input type="checkbox" checked={qualifiedOnly} onChange={(event) => { setQualifiedOnly(event.target.checked); setPage(1); }} />{category === "batter" ? "규정타석 충족 선수만" : "규정이닝 충족 선수만"}</label><span>{thresholds.length ? thresholdLabel : "규정 기준을 확인할 수 없는 기록이에요"}</span><small>{category === "batter" ? "팀 경기 수 × 3.1, 소수점 버림" : "팀 경기 수와 같은 이닝"}{rateSorts[category].includes(sort) && qualifiedOnly ? " · 비율 정렬에 자동 적용했어요" : ""}</small></div>}
      {busy ? <div className="record-state" role="status"><div className="record-loading-dots"><i /><i /><i /></div><strong>선수 기록을 불러오고 있어요</strong></div> : error ? <div className="record-state record-state--error" role="alert"><strong>기록을 불러오지 못했어요</strong><p>{error}</p><button type="button" className="secondary" onClick={() => setRetry((value) => value + 1)}>다시 불러오기</button></div> : !visible.length ? <div className="record-state"><strong>{records.length ? "조건에 맞는 선수가 없어요" : "이 시즌의 선수 기록을 준비 중이에요"}</strong><p>{records.length ? "선수 이름이나 구단, 규정 기준·최소 출전 조건을 바꿔 보세요." : "구단을 바꾸거나 잠시 후 다시 확인해 주세요."}</p>{records.length > 0 && <button type="button" className="secondary" onClick={() => { setQuery(""); setMinimum(0); setQualifiedOnly(false); }}>검색 조건 지우기</button>}</div> : <><label className="mobile-player-picker">기록지를 볼 선수<select aria-label="기록지를 볼 선수" value={selected ? `${selected.player_id}-${selected.team_code}` : ""} onChange={(event) => setSelectedId(event.target.value)}>{visible.map((record) => <option key={`${record.player_id}-${record.team_code}`} value={`${record.player_id}-${record.team_code}`}>{record.player_name} · {presentTeam(record.team_code)}</option>)}</select><small>선수를 바꾸면 아래 기록지도 바로 바뀌어요.</small></label><div className="record-explorer"><section className="player-directory" aria-label="선수 목록"><div className="player-directory-heading"><h3>선수 <span>{visible.length}명</span></h3><div className="record-view-toggle"><button type="button" aria-pressed={display === "cards"} className={display === "cards" ? "active" : ""} onClick={() => setDisplay("cards")}>카드</button><button type="button" aria-pressed={display === "table"} className={display === "table" ? "active" : ""} onClick={() => setDisplay("table")}>표</button></div></div><div className="player-sort"><label>정렬<select aria-label="선수 정렬 기준" value={sort} onChange={(event) => chooseSort(event.target.value)}>{availableSorts.map((key) => <option key={key} value={key}>{statName(key, category)}</option>)}</select></label><button type="button" onClick={() => setSortDirection((value) => value === "asc" ? "desc" : "asc")}>{sortDirection === "asc" ? "낮은 순 ↑" : "높은 순 ↓"}</button></div>{display === "cards" ? <div className="player-card-list">{pageRows.map((record) => <button type="button" className={`player-record-card ${selected === record ? "is-selected" : ""}`} aria-pressed={selected === record} key={`${record.player_id}-${record.team_code}`} onClick={() => choosePlayer(record)}><div className="player-card-title"><TeamAvatar teamCode={record.team_code} /><span><strong>{record.player_name}</strong><small>{presentTeam(record.team_code)} · {record.position ?? (category === "pitcher" ? "투수" : "타격 기록")}</small></span><span className="player-card-arrow" aria-hidden="true">›</span></div><div className="player-card-stats">{(category === "batter" ? ["AVG", "HR", "PA"] : ["ERA", "SO", "IP"]).map((key) => <span key={key}><small>{statName(key, category)}</small><strong>{valueOf(record, key)}</strong></span>)}</div></button>)}</div> : <div className="player-directory-table"><table><thead><tr><th>선수</th>{tableColumns.map((key) => <th key={key}>{statName(key, category)}</th>)}</tr></thead><tbody>{pageRows.map((record) => <tr key={`${record.player_id}-${record.team_code}`} className={selected === record ? "is-selected" : ""}><td><button type="button" onClick={() => choosePlayer(record)}><TeamAvatar teamCode={record.team_code} /><span className="table-player-name">{record.player_name}<small>{presentTeam(record.team_code)}</small></span></button></td>{tableColumns.map((key) => <td key={key}>{valueOf(record, key)}</td>)}</tr>)}</tbody></table></div>}{pageCount > 1 && <nav className="record-pagination" aria-label="선수 목록 페이지"><button type="button" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>이전</button><span>{currentPage} / {pageCount}</span><button type="button" disabled={currentPage === pageCount} onClick={() => setPage(currentPage + 1)}>다음</button></nav>}</section><div className="player-sheet-anchor" ref={sheetRef}>{selected && <PlayerSheet record={selected} category={category} season={season} />}</div></div></>}
      <details className="record-glossary"><summary>기록을 읽는 방법</summary><p>타율·출루율·장타율·OPS와 평균자책점·WHIP 정렬에는 규정타석 또는 규정이닝 기준을 자동 적용해요. 타율은 높은 순, 평균자책점은 낮은 순으로 보여드려요. 전체 선수를 보려면 규정 기준을 해제할 수 있어요.</p><dl>{["AVG", "OBP", "SLG", "OPS", "ERA", "WHIP", "IP"].map((key) => <div key={key}><dt>{key} · {statName(key, category)}</dt><dd>{metricDescriptions[key]}</dd></div>)}</dl><p>투수가 실제 타석에 들어선 기록은 ‘투수의 타격 기록도 포함하기’를 켜면 확인할 수 있어요. 값이 ‘—’인 항목은 조회된 기록에 값이 없다는 뜻이에요.</p></details>
    </>}
  </>;
}
