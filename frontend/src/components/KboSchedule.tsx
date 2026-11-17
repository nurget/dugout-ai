import { useEffect, useMemo, useState } from "react";
import { api, ApiError, type KboGameRecord } from "../api/client";
import { presentTeam, recordTeamCode, recordTeams } from "./recordDisplay";
import { KboGameSheet } from "./KboGameSheet";
import "./Schedule.css";

type Props = { logout: () => void; initialTeam?: string };
type CalendarView = "month" | "week";
type CalendarSelection = { anchor: string; day: string };
type Outcome = "win" | "loss" | "draw";
const outcomeNames: Record<Outcome, string> = { win: "승", loss: "패", draw: "무" };
const normalizeTeam = (code: string) => recordTeamCode(code.toUpperCase());
function gameOutcome(game: KboGameRecord, team: string): Outcome | null {
  if (!team || game.status !== "Final" || !Number.isFinite(game.home_score) || !Number.isFinite(game.away_score) || game.home_score === null || game.away_score === null) return null;
  const code = normalizeTeam(team);
  const isHome = normalizeTeam(game.home_team_code) === code;
  if (!isHome && normalizeTeam(game.away_team_code) !== code) return null;
  const own = isHome ? game.home_score : game.away_score;
  const opponent = isHome ? game.away_score : game.home_score;
  return own === opponent ? "draw" : own > opponent ? "win" : "loss";
}
const matchupKey = (game: KboGameRecord) => [normalizeTeam(game.home_team_code), normalizeTeam(game.away_team_code)].sort().join("-");
function doubleHeaderMatchups(games: KboGameRecord[]) {
  const byMatchup = new Map<string, Set<string>>();
  games.filter((game) => !["Cancelled", "Postponed"].includes(game.status)).forEach((game) => {
    const key = matchupKey(game);
    if (!byMatchup.has(key)) byMatchup.set(key, new Set());
    byMatchup.get(key)!.add(game.game_pk);
  });
  return new Set([...byMatchup].filter(([, ids]) => ids.size > 1).map(([key]) => key));
}
function dayResultsLabel(games: KboGameRecord[], team: string) {
  if (!games.length) return "경기 없음";
  if (!team) return "경기 일정 있음";
  const results = games.map((game) => gameOutcome(game, team));
  const summary = (["win", "loss", "draw"] as Outcome[]).map((outcome) => {
    const count = results.filter((result) => result === outcome).length;
    return count ? `${count}${outcomeNames[outcome]}` : "";
  }).filter(Boolean).join(" ");
  return summary || "경기 일정 있음";
}
const statuses: Record<string, string> = { Scheduled: "경기 예정", Final: "경기 종료", Postponed: "연기", Cancelled: "취소", "In Progress": "진행 중" };
const weekdayNames = ["월", "화", "수", "목", "금", "토", "일"];
const season = 2026;
const utcDay = (date: string) => new Date(`${date}T00:00:00.000Z`);
const isoDay = (date: Date) => date.toISOString().slice(0, 10);
const addDays = (date: string, days: number) => { const next = utcDay(date); next.setUTCDate(next.getUTCDate() + days); return isoDay(next); };
const startOfMonth = (date: string) => `${date.slice(0, 7)}-01`;
const startOfWeek = (date: string) => addDays(date, -((utcDay(date).getUTCDay() + 6) % 7));
const addMonths = (date: string, months: number) => { const next = utcDay(startOfMonth(date)); next.setUTCMonth(next.getUTCMonth() + months); return isoDay(next); };
const endOfMonth = (date: string) => addDays(addMonths(date, 1), -1);
const koreanDay = (date: string) => utcDay(date).toLocaleDateString("ko-KR", { timeZone: "UTC", month: "long", day: "numeric", weekday: "long" });
const koreanMonth = (date: string) => utcDay(date).toLocaleDateString("ko-KR", { timeZone: "UTC", year: "numeric", month: "long" });
const shortDay = (date: string) => `${Number(date.slice(5, 7))}.${Number(date.slice(8, 10))}`;
const todayInSeoul = () => new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
function recentGameDate(dates: string[]) {
  const today = todayInSeoul();
  return dates.filter((date) => date <= today).at(-1) ?? dates[0] ?? `${season}-01-01`;
}
function closestGameDate(dates: string[], target: string) {
  if (!dates.length) return target;
  return dates.reduce((closest, date) => Math.abs(utcDay(date).getTime() - utcDay(target).getTime()) < Math.abs(utcDay(closest).getTime() - utcDay(target).getTime()) ? date : closest);
}

export function KboSchedule({ logout, initialTeam = "" }: Props) {
  const [team, setTeam] = useState(initialTeam);
  const [phase, setPhase] = useState<"REGULAR" | "POSTSEASON">("REGULAR");
  const [view, setView] = useState<CalendarView>("month");
  const [selection, setSelection] = useState<CalendarSelection | null>(null);
  const [games, setGames] = useState<KboGameRecord[]>([]);
  const [loadState, setLoadState] = useState<{ key: string; error: string | null }>({ key: "", error: null });
  const [retry, setRetry] = useState(0);
  const [selectedGame, setSelectedGame] = useState<KboGameRecord | null>(null);
  const loadKey = [season, team, phase, retry].join(":");
  const busy = loadState.key !== loadKey;
  const error = busy ? null : loadState.error;

  useEffect(() => {
    let active = true;
    api.kboGames(season, phase, team ? recordTeamCode(team) : undefined).then((response) => {
      if (!active) return;
      const dates = [...new Set(response.data.map((game) => game.game_date))].sort();
      setGames(response.data);
      setSelection((previous) => {
        const day = previous ? closestGameDate(dates, previous.day) : recentGameDate(dates);
        return { anchor: day, day };
      });
      setLoadState({ key: loadKey, error: null });
    }).catch((reason: unknown) => {
      if (!active) return;
      if (reason instanceof ApiError && reason.status === 401) logout();
      setLoadState({ key: loadKey, error: reason instanceof Error ? reason.message : "경기 일정을 불러오지 못했어요." });
    });
    return () => { active = false; };
  }, [team, phase, retry, logout, loadKey]);

  const gamesByDate = useMemo(() => {
    const result = new Map<string, KboGameRecord[]>();
    games.toSorted((a, b) => a.game_pk.localeCompare(b.game_pk)).forEach((game) => result.set(game.game_date, [...(result.get(game.game_date) ?? []), game]));
    return result;
  }, [games]);
  const dates = useMemo(() => [...gamesByDate.keys()].sort(), [gamesByDate]);
  const anchor = selection?.anchor ?? recentGameDate(dates);
  const selectedDay = selection?.day ?? anchor;
  const periodStart = view === "month" ? startOfMonth(anchor) : startOfWeek(anchor);
  const periodEnd = view === "month" ? endOfMonth(anchor) : addDays(periodStart, 6);
  const periodDates = dates.filter((date) => date >= periodStart && date <= periodEnd);
  const dayGames = gamesByDate.get(selectedDay) ?? [];
  const selectedDoubleHeaders = doubleHeaderMatchups(dayGames);
  const firstPeriod = dates[0] ? (view === "month" ? startOfMonth(dates[0]) : startOfWeek(dates[0])) : periodStart;
  const lastPeriod = dates.at(-1) ? (view === "month" ? startOfMonth(dates.at(-1)!) : startOfWeek(dates.at(-1)!)) : periodStart;
  const calendarStart = view === "month" ? startOfWeek(periodStart) : periodStart;
  const calendarCellCount = view === "month" ? Math.ceil((((utcDay(periodStart).getUTCDay() + 6) % 7) + utcDay(periodEnd).getUTCDate()) / 7) * 7 : 7;
  const calendarDays = Array.from({ length: calendarCellCount }, (_, index) => addDays(calendarStart, index));
  const caption = view === "month" ? koreanMonth(anchor) : `${Number(periodStart.slice(0, 4))}년 ${shortDay(periodStart)} – ${periodStart.slice(0, 4) !== periodEnd.slice(0, 4) ? `${periodEnd.slice(0, 4)}년 ` : ""}${shortDay(periodEnd)}`;

  const choosePeriod = (nextAnchor: string) => {
    const from = view === "month" ? startOfMonth(nextAnchor) : startOfWeek(nextAnchor);
    const through = view === "month" ? endOfMonth(nextAnchor) : addDays(from, 6);
    const available = dates.filter((date) => date >= from && date <= through);
    const day = available.length ? closestGameDate(available, nextAnchor) : from;
    setSelection({ anchor: nextAnchor, day });
  };
  const movePeriod = (direction: number) => choosePeriod(view === "month" ? addMonths(anchor, direction) : addDays(periodStart, direction * 7));
  const showRecent = () => { const day = recentGameDate(dates); setSelection({ anchor: day, day }); };
  const changeView = (next: CalendarView) => { setView(next); setSelection({ anchor: selectedDay, day: selectedDay }); };

  return <section className="schedule-workspace schedule-calendar-workspace" aria-label="KBO 경기 일정">
    <div className="schedule-filters schedule-calendar-filters"><span className="schedule-season-label">{season} 시즌</span><label>대회<select aria-label="일정 대회 구분" value={phase} onChange={(event) => setPhase(event.target.value as "REGULAR" | "POSTSEASON")}><option value="REGULAR">정규시즌</option><option value="POSTSEASON">포스트시즌</option></select></label><label>구단<select aria-label="일정 구단" value={team} onChange={(event) => setTeam(event.target.value)}>{recordTeams.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label></div>
    {busy ? <div className="record-state" role="status"><div className="record-loading-dots"><i /><i /><i /></div><strong>경기 일정을 불러오고 있어요</strong></div> : error ? <div className="record-state record-state--error" role="alert"><strong>일정을 불러오지 못했어요</strong><p>{error}</p><button type="button" className="secondary" onClick={() => setRetry((value) => value + 1)}>다시 불러오기</button></div> : !dates.length ? <div className="record-state"><strong>이 조건에 해당하는 경기가 없어요</strong><p>다른 구단이나 대회 구분을 선택해 확인해 보세요.</p></div> : <>
      <section className="schedule-calendar-panel" aria-label={view === "month" ? "월간 경기 달력" : "주간 경기 달력"}>
        <div className="schedule-calendar-top"><div className="schedule-view-control" aria-label="일정 보기 방식"><button type="button" className={view === "month" ? "active" : ""} aria-pressed={view === "month"} onClick={() => changeView("month")}>월별</button><button type="button" className={view === "week" ? "active" : ""} aria-pressed={view === "week"} onClick={() => changeView("week")}>주간</button></div><button type="button" className="schedule-recent-button" onClick={showRecent}>최근 경기로</button></div>
        <div className="schedule-period-heading"><button type="button" className="schedule-period-arrow" aria-label={view === "month" ? "이전 달 경기 일정" : "이전 주 경기 일정"} disabled={periodStart <= firstPeriod} onClick={() => movePeriod(-1)}><span aria-hidden="true">‹</span></button><div aria-live="polite"><h3>{caption}</h3><p>{view === "month" ? "월별 일정" : "월요일부터 일요일까지"}</p></div><button type="button" className="schedule-period-arrow" aria-label={view === "month" ? "다음 달 경기 일정" : "다음 주 경기 일정"} disabled={periodStart >= lastPeriod} onClick={() => movePeriod(1)}><span aria-hidden="true">›</span></button></div>

        <div className={`schedule-calendar-grid ${view === "week" ? "is-week" : ""}`}><div className="schedule-weekdays" aria-hidden="true">{weekdayNames.map((day) => <span key={day}>{day}</span>)}</div><div className="schedule-calendar-dates">{calendarDays.map((date, index) => {
          const rows = gamesByDate.get(date) ?? [];
          const outcomes = rows.map((game) => gameOutcome(game, team)).filter((value): value is Outcome => value !== null);
          const isDoubleHeader = doubleHeaderMatchups(rows).size > 0;
          const outsideMonth = view === "month" && date.slice(0, 7) !== anchor.slice(0, 7);
          return <button type="button" key={date} className={`schedule-calendar-date ${date === selectedDay ? "is-selected" : ""} ${outsideMonth ? "is-outside" : ""} ${index % 7 === 6 ? "is-sunday" : ""}`} aria-pressed={date === selectedDay} aria-label={`${koreanDay(date)}, ${dayResultsLabel(rows, team)}${isDoubleHeader ? ", 더블헤더" : ""}`} disabled={outsideMonth} onClick={() => setSelection({ anchor, day: date })}><time dateTime={date}>{Number(date.slice(8, 10))}</time><span className="schedule-day-results">{team && outcomes.length ? <>{outcomes.map((outcome, resultIndex) => <span className={`schedule-outcome outcome-${outcome}`} key={`${outcome}-${resultIndex}`}>{outcomeNames[outcome]}</span>)}{outcomes.length < rows.length && <i className="schedule-neutral-marker" aria-hidden="true" />}</> : rows.length > 0 ? <i className="schedule-neutral-marker" aria-hidden="true" /> : null}</span>{isDoubleHeader && <small className="schedule-doubleheader-day">더블헤더</small>}</button>;

        })}</div></div>
        <div className="schedule-calendar-caption"><span><i /> 선택한 날짜</span>{team ? <div className="schedule-outcome-legend"><span className="schedule-outcome outcome-win">승</span><span className="schedule-outcome outcome-loss">패</span><span className="schedule-outcome outcome-draw">무</span><span>{presentTeam(team)} 기준</span></div> : <p>점이 있는 날짜에 경기가 있어요.</p>}</div>
      </section>
      <section className="schedule-selected-day" aria-label="선택한 날짜의 경기"><header><div><p>{view === "month" ? "월별" : "주간"} 일정에서 선택한 날짜</p><h3><time dateTime={selectedDay}>{koreanDay(selectedDay)}</time></h3></div>{selectedDoubleHeaders.size > 0 && <span className="schedule-doubleheader-header">{team ? "더블헤더" : "더블헤더 포함"}</span>}</header>{dayGames.length ? <div className="schedule-game-grid">{dayGames.map((game) => { const outcome = gameOutcome(game, team); const isDoubleHeader = selectedDoubleHeaders.has(matchupKey(game)) && !["Cancelled", "Postponed"].includes(game.status); return <article className={`schedule-game-card ${outcome ? `has-outcome-${outcome}` : ""}`} key={game.game_pk}><div className="schedule-game-status"><span className={game.status === "Final" ? "is-final" : ""}>{statuses[game.status] ?? game.status}</span><div className="schedule-card-result">{outcome && <span className={`schedule-outcome outcome-${outcome}`}>{presentTeam(team)} {outcomeNames[outcome]}</span>}{isDoubleHeader && <span className="schedule-doubleheader-card">더블헤더</span>}</div></div><div className="schedule-game-team"><span>{presentTeam(game.away_team_code)}<small>원정</small></span><strong>{game.away_score ?? "—"}</strong></div><div className="schedule-game-team"><span>{presentTeam(game.home_team_code)}<small>홈</small></span><strong>{game.home_score ?? "—"}</strong></div><button type="button" className="schedule-details-button" onClick={() => setSelectedGame(game)}>경기 기록 보기 <span aria-hidden="true">›</span></button></article>; })}</div> : <div className="schedule-rest-day"><strong>이날은 등록된 경기가 없어요.</strong><p>달력에서 결과나 점이 표시된 날짜를 선택해 보세요.</p>{!periodDates.length && <button type="button" className="secondary" onClick={showRecent}>최근 경기 보기</button>}</div>}</section>
    </>}
    {selectedGame && <KboGameSheet game={selectedGame} logout={logout} onClose={() => setSelectedGame(null)} />}
  </section>;
}
