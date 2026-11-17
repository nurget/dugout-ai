/* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type SavedMessage, type TeamCode, type User, type UserId } from "./api/client";
import { useAuth } from "./hooks/useAuth";
import { useAgentStream } from "./hooks/useAgentStream";
import { BullpenComparisonCard } from "./components/BullpenComparisonCard";
import { MatchupAnalysis } from "./components/MatchupAnalysis";
import { KboTeamOverview } from "./components/KboTeamOverview";
import { KboRecords } from "./components/KboRecords";
import { getTeamTheme } from "./teamTheme";
import "./App.css";
import "./phase.css";

type Tab = "agent" | "overview" | "pitchers" | "batters" | "matchups" | "records";
const labels: Record<string, string> = { idle: "준비됨", connecting: "연결 중", analyzing: "질문 처리 중", generating: "답변 생성 중", completed: "분석 완료", cancelled: "중단됨", failed: "실패" };
const teamLabels: Record<string, string> = { HT: "KIA", KIA: "KIA", KT: "KT", LG: "LG", NC: "NC", LT: "롯데", LOT: "롯데", HH: "한화", HAN: "한화", WO: "키움", KIW: "키움", SSG: "SSG", SS: "삼성", SAM: "삼성", OB: "두산", DOO: "두산" };
const teamLabel = (code: string) => teamLabels[code.toUpperCase()] ?? code;

const signupTeams: ReadonlyArray<readonly [TeamCode, string]> = [["KIA", "KIA 타이거즈"], ["SS", "삼성 라이온즈"], ["LG", "LG 트윈스"], ["KT", "KT 위즈"], ["SSG", "SSG 랜더스"], ["NC", "NC 다이노스"], ["OB", "두산 베어스"], ["LT", "롯데 자이언츠"], ["HH", "한화 이글스"], ["WO", "키움 히어로즈"]];
function Login({ login, register }: { login: (id: string, password: string) => Promise<void>; register: (id: string, password: string, team: TeamCode) => Promise<void> }) {
  const [registering, setRegistering] = useState(false); const [username, setUsername] = useState(""); const [password, setPassword] = useState(""); const [confirmPassword, setConfirmPassword] = useState(""); const [team, setTeam] = useState<TeamCode>("KIA"); const [error, setError] = useState<string | null>(null); const [loading, setLoading] = useState(false);
  const changeMode = (next: boolean) => { setRegistering(next); setError(null); setPassword(""); setConfirmPassword(""); };
  async function submit(e: React.FormEvent) { e.preventDefault(); setError(null); if (registering && password !== confirmPassword) { setError("비밀번호가 일치하지 않습니다."); return; } setLoading(true); try { if (registering) await register(username, password, team); else await login(username, password); } catch (err) { setError(err instanceof Error ? err.message : registering ? "계정을 생성하지 못했습니다." : "로그인에 실패했습니다."); } finally { setLoading(false); } }
  return <main className="login-page" style={registering ? getTeamTheme(team) : undefined}><section className="login-card"><div className="brand-mark">D</div><p className="eyebrow">야구를 더 깊이 보는 기록</p><h1>{registering ? "계정 생성" : "Dugout AI"}</h1><p className="muted">{registering ? "데모에 사용할 소속 구단을 선택하세요." : "구단의 판단을 더 빠르고 정확하게"}</p><div className="auth-tabs"><button type="button" className={!registering ? "active" : ""} onClick={() => changeMode(false)}>로그인</button><button type="button" className={registering ? "active" : ""} onClick={() => changeMode(true)}>계정 생성</button></div><form onSubmit={submit}><label>아이디<input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" minLength={3} required /></label><label>비밀번호<input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete={registering ? "new-password" : "current-password"} minLength={registering ? 12 : 1} required />{registering && <small>12자 이상으로 설정해 주세요.</small>}</label>{registering && <><label>비밀번호 확인<input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} autoComplete="new-password" required /></label><label>소속 구단<select value={team} onChange={e => setTeam(e.target.value as TeamCode)}>{signupTeams.map(([code, name]) => <option key={code} value={code}>{name}</option>)}</select></label><small>공개 가입 계정은 코치 권한으로만 생성됩니다.</small></>}{error && <p className="error">{error}</p>}<button className="primary" disabled={loading}>{loading ? (registering ? "계정 생성 중…" : "로그인 중…") : (registering ? "계정 생성하고 시작하기" : "로그인")}</button></form></section></main>;
}

function Dashboard({ user, logout }: { user: User; logout: () => void }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [recordTeam, setRecordTeam] = useState<string>(user.team_code);
  const handleLogout = useCallback(() => { sessionStorage.removeItem(`dugout_conversation_id:${user.id}`); logout(); }, [logout, user.id]);
  const menu: Array<[Tab, string, string]> = [
    ["overview", "구단과 경기", "팀 성적과 경기 일정"],
    ["batters", "타자 기록", "한 장으로 보는 타격 기록"],
    ["pitchers", "투수 기록", "한 장으로 보는 투구 기록"],
    ["matchups", "상대 타순", "경기별 선발 타순과 상대 기록"],
    ["records", "전체 선수", "KBO 전 구단 선수 찾기"],
  ];
  return <main className="app-shell" data-team={user.team_code} style={getTeamTheme(user.team_code)}>
    <header className="topbar"><div className="brand-lockup"><span className="wordmark-mark">D</span><span className="wordmark">Dugout</span><span className="product">야구를 더 깊이 보는 기록</span></div><div className="account"><span className="account-team">{teamLabel(user.team_code)}</span><span className="account-name">{user.username}</span><button onClick={handleLogout}>로그아웃</button></div></header>
    <aside className="sidebar"><div className="team-chip"><span>내 구단</span><strong>{teamLabel(user.team_code)}</strong><small>2026 시즌</small></div><nav aria-label="서비스 메뉴"><div className="nav-group"><span className="nav-label">기록 둘러보기</span>{menu.map(([id, name, description]) => <button key={id} className={tab === id ? "nav nav-record active" : "nav nav-record"} onClick={() => { setRecordTeam(user.team_code); setTab(id); }}><span className="nav-indicator" aria-hidden="true" /><span><strong>{name}</strong><small>{description}</small></span></button>)}</div><div className="nav-group nav-group--support"><span className="nav-label">경기 분석</span><button className={tab === "agent" ? "nav nav-primary active" : "nav nav-primary"} onClick={() => setTab("agent")}><span className="nav-icon">AI</span><span><strong>AI 전술 분석</strong><small>경기 상황을 물어보세요</small></span></button></div></nav><div className="sidebar-foot"><span className="status-dot" />KBO 기록을 한곳에서</div></aside>
    <section className="content" id="main-content">
      {tab === "agent" && <Agent accountId={user.id} canReview={user.role === "COACH" || user.role === "MANAGER"} logout={handleLogout} />}
      {tab === "overview" && <KboTeamOverview initialTeam={recordTeam} logout={handleLogout} onPlayers={(category, teamCode) => { setRecordTeam(teamCode); setTab(category === "batter" ? "batters" : "pitchers"); }} />}
      {tab === "pitchers" && <KboRecords key="pitchers" title="투수 기록" fixedCategory initialCategory="pitcher" initialTeam={recordTeam} logout={handleLogout} />}
      {tab === "batters" && <KboRecords key="batters" title="타자 기록" fixedCategory initialCategory="batter" initialTeam={recordTeam} logout={handleLogout} />}
      {tab === "matchups" && <MatchupAnalysis teamCode={user.team_code} logout={handleLogout} />}
      {tab === "records" && <KboRecords key="all-records" title="전체 선수 기록" showSchedule logout={handleLogout} />}
    </section>
  </main>;
}

function Agent({ accountId, canReview, logout }: { accountId: UserId; canReview: boolean; logout: () => void }) {
  const [message, setMessage] = useState("");
  const [dateChoice, setDateChoice] = useState("");
  const [calendar, setCalendar] = useState<{ dates: string[]; ready: boolean; error: string | null }>({ dates: [], ready: false, error: null });
  const [calendarRetry, setCalendarRetry] = useState(0);
  const asOfDate = calendar.dates.includes(dateChoice) ? dateChoice : calendar.dates[0] ?? "";
  const [history, setHistory] = useState<SavedMessage[]>([]);
  const stream = useAgentStream(accountId, logout);
  const busy = ["connecting", "analyzing", "generating"].includes(stream.status);
  const suggestions = ["7회말 1사 1루, 투수 교체가 필요할까요?", "오늘 불펜 후보의 최근 등판 부담을 비교해줘", "전상현과 정해영의 시즌 기록을 비교해줘"];

  useEffect(() => {
    let active = true;
    api.matchupCalendar(2026).then((result) => {
      if (active) setCalendar({ dates: result.data.map((row) => row.game_date), ready: true, error: null });
    }).catch((reason: unknown) => {
      if (!active) return;
      if (reason instanceof ApiError && reason.status === 401) logout();
      setCalendar({ dates: [], ready: true, error: reason instanceof Error ? reason.message : "경기 날짜를 불러오지 못했어요." });
    });
    return () => { active = false; };
  }, [logout, calendarRetry]);

  useEffect(() => { if (!stream.conversationId) { setHistory([]); return; } let active = true; api.messages(stream.conversationId).then(r => active && setHistory(r.messages)).catch(e => { if (e instanceof ApiError && e.status === 401) logout(); if (e instanceof ApiError && e.status === 404) stream.startNewConversation(); }).catch(() => undefined); return () => { active = false; }; }, [stream.conversationId, stream.historyVersion, logout]);
  const submit = (e: React.FormEvent) => { e.preventDefault(); if (!message.trim() || busy || !calendar.dates.includes(asOfDate)) return; void stream.sendMessage(message, asOfDate); setMessage(""); };

  return <><div className="page-head agent-head"><div><div className="agent-title-row"><p className="eyebrow">경기 상황에서 시작하는 분석</p><span className="core-badge">핵심 기능</span></div><h2>AI 전술 분석</h2><p className="muted">경기 상황을 질문하면 Agent가 필요한 기록과 도구를 선택해 판단 근거를 제시합니다.</p></div><button className="secondary" disabled={busy} onClick={stream.startNewConversation}>새 대화</button></div><section className="agent-panel"><div className="agent-status"><i className={busy ? "pulse" : ""} />{labels[stream.status]} {stream.conversationId && <small>대화 ID {stream.conversationId.slice(0, 8)}</small>}</div><div className="messages">{history.map(m => <div key={m.id}><article className={`message ${m.role}`}><b>{m.role === "user" ? "코치" : "Dugout AI"}</b><p>{m.content}</p></article>{m.analysis_results.map((result, index) => <BullpenComparisonCard key={`${m.id}-${index}`} result={result} canReview={canReview} />)}</div>)}{stream.answer && <article className="message assistant live"><b>DUGOUT AI</b><p>{stream.answer}</p></article>}{stream.analysisResults.map((result, index) => <BullpenComparisonCard key={`live-${index}`} result={result} canReview={canReview} />)}{!history.length && !stream.answer && !busy && <div className="agent-empty"><span className="agent-empty__mark">AI</span><h3>경기 상황을 설명해 주세요</h3><p>자연어 질문을 바탕으로 선수 기록 조회, 불펜 비교, 최근 투구 부담 확인을 순서대로 수행합니다.</p><div className="suggestion-list">{suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => setMessage(suggestion)}>{suggestion}</button>)}</div></div>}</div>{stream.tools.length > 0 && <div className="tools"><strong>Agent 실행 과정</strong>{stream.tools.map((tool, i) => <span key={`${tool.tool}-${i}`} className={tool.ok === false ? "fail" : tool.ok ? "done" : "running"}>{tool.ok === undefined ? "실행 중" : tool.ok ? "완료" : "실패"} · {tool.tool.replaceAll("_", " ")}{tool.duration_ms !== undefined && ` · ${tool.duration_ms}ms`}</span>)}</div>}{stream.error && <p className="error">{stream.error}</p>}<form className="composer" onSubmit={submit}><div className="analysis-game-date"><label className="as-of-picker">분석 기준일<select aria-label="분석 기준일" value={asOfDate} disabled={!calendar.ready || busy || !calendar.dates.length} onChange={event => setDateChoice(event.target.value)}>{!calendar.dates.length && <option value="">{!calendar.ready ? "경기 날짜를 불러오는 중" : "선택할 경기가 없어요"}</option>}{calendar.dates.map(day => <option key={day} value={day}>{day}</option>)}</select><small>우리 팀의 경기 날짜만 선택할 수 있어요. 분석에는 선택 경기 전날까지의 기록을 사용해요.</small></label>{calendar.error && <p className="analysis-calendar-error" role="alert">{calendar.error}<button type="button" onClick={() => { setCalendar({ dates: [], ready: false, error: null }); setCalendarRetry(value => value + 1); }}>다시 불러오기</button></p>}</div><textarea aria-label="전술 질문" value={message} onChange={e => setMessage(e.target.value)} placeholder="예: 7회말 1사 1루, 투수 교체가 필요할까요?" maxLength={1000} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} /><div><small>AI 분석은 의사결정을 지원하며, 당일 엔트리와 컨디션은 별도 확인이 필요합니다.</small>{busy ? <button className="secondary" type="button" onClick={stream.cancel}>중단</button> : <button className="primary" disabled={!calendar.ready || !asOfDate || !!calendar.error}>분석 요청</button>}</div></form></section></>;
}

export default function App() { const auth = useAuth(); if (auth.checking) return <main className="page-state">인증 상태를 확인하는 중입니다…</main>; return auth.user ? <Dashboard key={auth.user.id} user={auth.user} logout={auth.logout} /> : <Login login={auth.login} register={auth.register} />; }
