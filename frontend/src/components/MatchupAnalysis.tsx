import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type MatchupAnalysis, type MatchupGame, type TeamCode } from "../api/client";
import "./MatchupAnalysis.css";

type GameDetail = Awaited<ReturnType<typeof api.gamePitcherMatchup>>;
type BatterFilter = "all" | "starters" | "faced";
const teamNames: Record<string, string> = { KIA: "KIA", HT: "KIA", SS: "삼성", SAM: "삼성", LG: "LG", KT: "KT", SSG: "SSG", SK: "SSG", NC: "NC", OB: "두산", DOO: "두산", LT: "롯데", LOT: "롯데", HH: "한화", HAN: "한화", WO: "키움", KIW: "키움" };
const teamName = (code: string) => teamNames[code] ?? code;
const value = (fields: Record<string, string> | undefined, ...keys: string[]) => keys.map((key) => fields?.[key]).find((item) => item !== undefined && item !== "") ?? "—";
const labels: Record<string, string> = { AB: "타수", H: "안타", RBI: "타점", R: "득점", AVG: "타율", HR: "홈런", OBP: "출루율", SLG: "장타율", OPS: "OPS", BB: "볼넷", SO: "삼진", PA: "타석", ERA: "평균자책", WHIP: "WHIP", G: "경기", IP: "이닝" };
const pitcherStats = ["이닝", "투구수", "타자", "피안타", "삼진", "4사구", "실점", "자책"];
const eventNames: Record<string, string> = { single: "단타", double: "2루타", triple: "3루타", home_run: "홈런", walk: "볼넷", intent_walk: "고의4구", intentional_walk: "고의4구", hit_by_pitch: "사구", strikeout: "삼진", strikeout_double_play: "삼진 병살", field_out: "범타", force_out: "포스 아웃", fielders_choice: "야수선택", fielders_choice_out: "야수선택 아웃", grounded_into_double_play: "땅볼 병살", double_play: "병살", triple_play: "삼중살", other_out: "기타 아웃", field_error: "실책 출루", sac_fly: "희생플라이", sac_fly_double_play: "희생플라이 병살", sac_bunt: "희생번트", sac_bunt_double_play: "희생번트 병살", catcher_interference: "타격방해", catcher_interf: "타격방해" };

export function MatchupAnalysis({ teamCode, logout }: { teamCode: TeamCode; logout: () => void }) {
  const [asOfDate, setAsOfDate] = useState("");
  const [calendar, setCalendar] = useState<Array<{ game_date: string; count: number }>>([]);
  const [games, setGames] = useState<MatchupGame[]>([]);
  const [selectedGamePk, setSelectedGamePk] = useState("");
  const [selectedPitcherId, setSelectedPitcherId] = useState("");
  const [detail, setDetail] = useState<GameDetail | null>(null);
  const [filter, setFilter] = useState<BatterFilter>("all");
  const [selectedBatterId, setSelectedBatterId] = useState("");
  const [showSubstitutes, setShowSubstitutes] = useState(false);
  const [pairResponse, setPairResponse] = useState<{ key: string; result: MatchupAnalysis | null; error: string | null }>({ key: "", result: null, error: null });
  const [pairRetry, setPairRetry] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [gamesLoading, setGamesLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const pairRequest = useRef(0);
  const pairPanelRef = useRef<HTMLElement | null>(null);
  const selectedGame = games.find((game) => game.game_pk === selectedGamePk);
  const selectedPitcher = detail?.pitchers.find((pitcher) => pitcher.pitcher_id === selectedPitcherId) ?? detail?.selected_pitcher;
  const shownBatters = useMemo(() => (detail?.batters ?? []).filter((batter) => filter === "starters" ? batter.is_starter === true : filter === "faced" ? !!batter.direct_matchup : true), [detail, filter]);
  const startingBatters = (detail?.batters ?? []).filter((batter) => batter.is_starter === true);
  const selectableBatters = showSubstitutes || !startingBatters.length ? detail?.batters ?? [] : startingBatters;
  const selectedBatter = detail?.batters.find((batter) => batter.batter_id === selectedBatterId);
  const identifiedPair = !!selectedPitcher && !!selectedBatter && !selectedPitcher.pitcher_id.startsWith("box-") && !selectedBatter.batter_id.startsWith("box-");
  const pairKey = selectedPitcher && selectedBatter && detail ? `${detail.game.game_pk}|${selectedPitcher.pitcher_id}|${selectedBatter.batter_id}|${asOfDate}|${pairRetry}` : "";
  const currentPair = pairResponse.key === pairKey ? pairResponse : null;
  const pairLoading = identifiedPair && !!pairKey && !currentPair;
  const history = currentPair?.result;
  const matchup = history?.matchups[0];
  const showError = useCallback((reason: unknown, fallback: string) => {
    if (reason instanceof ApiError && reason.status === 401) logout();
    setError(reason instanceof Error ? reason.message : fallback);
  }, [logout]);

  useEffect(() => {
    let active = true;
    api.matchupCalendar(2026).then((result) => {
      if (!active) return;
      setCalendar(result.data); setAsOfDate((current) => current || result.latest_game_date || "");
      if (!result.data.length) setGamesLoading(false);
    }).catch((reason: unknown) => { if (active) { showError(reason, "경기 목록을 불러오지 못했어요."); setGamesLoading(false); } });
    return () => { active = false; };
  }, [showError, retry]);

  useEffect(() => {
    if (!asOfDate) return;
    let active = true;
    api.matchupGames(asOfDate).then((result) => {
      if (!active) return;
      setGames(result.data); setSelectedPitcherId(""); setSelectedGamePk(result.data[0]?.game_pk ?? "");
      setError(null);
    }).catch((reason: unknown) => { if (active) { setGames([]); showError(reason, "경기를 불러오지 못했어요."); } }).finally(() => { if (active) setGamesLoading(false); });
    return () => { active = false; };
  }, [asOfDate, showError, retry]);

  useEffect(() => {
    if (!selectedGamePk) return;
    let active = true;
    api.gamePitcherMatchup(selectedGamePk, selectedPitcherId || undefined).then((result) => {
      if (active) { setDetail(result); setFilter(result.direct_matchup_available ? "faced" : "all"); setError(null); }
    }).catch((reason: unknown) => { if (active) { setDetail(null); showError(reason, "등판 기록을 불러오지 못했어요."); } }).finally(() => { if (active) setDetailLoading(false); });
    return () => { active = false; };
  }, [selectedGamePk, selectedPitcherId, showError, retry]);

  useEffect(() => {
    if (!identifiedPair || !pairKey || !detail || !selectedPitcher || !selectedBatter || detailLoading || gamesLoading) return;
    let active = true;
    const request = ++pairRequest.current;
    api.pitcherMatchups({
      season: detail.game.season, as_of_date: detail.game.game_date,
      opponent_team_code: detail.opponent_team_code,
      pitcher_ids: [selectedPitcher.pitcher_id], batter_ids: [selectedBatter.batter_id],
    }).then((result) => {
      if (active && request === pairRequest.current) setPairResponse({ key: pairKey, result, error: null });
    }).catch((reason: unknown) => {
      if (reason instanceof ApiError && reason.status === 401) logout();
      if (active && request === pairRequest.current) setPairResponse({ key: pairKey, result: null, error: reason instanceof Error ? reason.message : "이전 맞대결을 불러오지 못했어요." });
    });
    return () => { active = false; };
  }, [identifiedPair, pairKey, detail, selectedPitcher, selectedBatter, detailLoading, gamesLoading, logout]);

  function chooseDate(next: string) {
    if (!next || next === asOfDate) return;
    pairRequest.current += 1;
    setAsOfDate(next); setGamesLoading(true); setDetailLoading(true); setDetail(null); setFilter("all"); setSelectedBatterId(""); setShowSubstitutes(false); setError(null);
  }
  function chooseGame(next: string) {
    pairRequest.current += 1;
    setSelectedGamePk(next); setSelectedPitcherId(""); setDetail(null); setDetailLoading(true); setFilter("all"); setSelectedBatterId(""); setShowSubstitutes(false);
  }
  function choosePitcher(next: string) {
    if (next === selectedPitcher?.pitcher_id) return;
    pairRequest.current += 1;
    setSelectedPitcherId(next); setDetailLoading(true); setFilter("all");
  }
  function chooseBatter(next: string) {
    if (next !== selectedBatterId) {
      pairRequest.current += 1;
      setSelectedBatterId(next);
    }
    if (window.matchMedia("(max-width: 850px)").matches) {
      requestAnimationFrame(() => pairPanelRef.current?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "start",
      }));
    }
  }

  return <div className="matchup-page">
    <header className="page-head"><p className="eyebrow">경기별 맞대결</p><h2>투수와 상대 타순</h2><p className="muted">경기와 투수, 상대 타자를 차례로 고르면 두 선수의 이전 맞대결을 바로 볼 수 있어요.</p></header>
    <section className="matchup-datebar" aria-label="경기 선택"><label><span className="matchup-step-number">1</span> 경기 날짜<select aria-label="우리 팀 경기 날짜" value={calendar.some((day) => day.game_date === asOfDate) ? asOfDate : ""} disabled={!calendar.length} onChange={(event) => chooseDate(event.target.value)}><option value="" disabled>{gamesLoading ? "경기 날짜를 불러오고 있어요" : "선택할 경기 날짜가 없어요"}</option>{calendar.map((day) => <option key={day.game_date} value={day.game_date}>{day.game_date}{day.count > 1 ? ` · ${day.count}경기` : ""}</option>)}</select></label>{games.length > 1 && <label>더블헤더 경기<select aria-label="경기 선택" value={selectedGamePk} onChange={(event) => chooseGame(event.target.value)}>{games.map((game, index) => <option key={game.game_pk} value={game.game_pk}>{teamName(game.away_team_code)} 대 {teamName(game.home_team_code)} · {index + 1}차전</option>)}</select></label>}</section>
    {error && <div className="matchup-message is-error" role="alert"><span>{error}</span><button type="button" onClick={() => { setGamesLoading(true); setDetailLoading(true); setRetry((current) => current + 1); }}>다시 불러오기</button></div>}
    {gamesLoading ? <div className="matchup-empty" role="status">경기 목록을 불러오고 있어요.</div> : !selectedGame ? <div className="matchup-empty"><strong>이 날짜에는 {teamName(teamCode)} 경기가 없어요.</strong><span>위의 목록에서 경기가 있는 날짜를 선택해 주세요.</span></div> : <>
      <section className="matchup-scorecard" aria-label="선택 경기"><div><small>원정</small><strong>{teamName(selectedGame.away_team_code)}</strong></div><p><b>{selectedGame.away_score ?? "—"}<span>:</span>{selectedGame.home_score ?? "—"}</b><small>{asOfDate} · {selectedGame.status === "Final" ? "경기 종료" : selectedGame.status === "Scheduled" ? "경기 예정" : selectedGame.status}</small></p><div><small>홈</small><strong>{teamName(selectedGame.home_team_code)}</strong></div></section>
      <section className="matchup-pitcher-picker"><div className="matchup-section-title"><div><h3><span className="matchup-step-number">2</span> {teamName(teamCode)} 등판 투수</h3><p>이 경기에 실제로 등판한 투수만 보여드려요.</p></div></div>{detail?.pitchers.length ? <div className="matchup-appearance-tabs" role="tablist" aria-label="등판 투수 선택">{detail.pitchers.map((pitcher) => <button key={pitcher.pitcher_id} type="button" role="tab" aria-selected={selectedPitcher?.pitcher_id === pitcher.pitcher_id} className={selectedPitcher?.pitcher_id === pitcher.pitcher_id ? "active" : ""} onClick={() => choosePitcher(pitcher.pitcher_id)}><small>{pitcher.appearance_order === 1 ? "선발" : `${pitcher.appearance_order}번째 등판`}</small><strong>{pitcher.pitcher_name}</strong><span>{value(pitcher.game_fields, "이닝")}이닝 · {value(pitcher.game_fields, "투구수")}구</span></button>)}</div> : detailLoading ? <p className="muted" role="status">등판 투수를 불러오고 있어요.</p> : <div className="matchup-empty compact">이 경기의 투수 기록이 아직 없어요.</div>}</section>
      {detailLoading ? <div className="matchup-empty" role="status">{selectedPitcher ? `${selectedPitcher.pitcher_name}의 경기 기록을 불러오고 있어요.` : "등판 투수의 경기 기록을 불러오고 있어요."}</div> : detail && selectedPitcher && <>
        <section className="matchup-pair-workspace" aria-label="타자를 선택하면 이전 맞대결 자동 조회">
          <div className="matchup-pair-picker"><div className="matchup-section-title"><div><h3><span className="matchup-step-number">3</span> 상대 타자 선택</h3><p>{selectedPitcher.pitcher_name}과 비교할 타자를 눌러 주세요.</p></div></div><div className="matchup-filter-tabs" role="tablist" aria-label="선택할 타자 범위"><button type="button" role="tab" aria-selected={!showSubstitutes} onClick={() => setShowSubstitutes(false)}>선발 타순</button><button type="button" role="tab" aria-selected={showSubstitutes} onClick={() => setShowSubstitutes(true)}>교체 포함</button></div><ol className="matchup-pair-batters">{selectableBatters.map((batter) => <li key={batter.batter_id}><button type="button" aria-label={`${batter.batter_name} 이전 맞대결 선택`} aria-pressed={selectedBatterId === batter.batter_id} onClick={() => chooseBatter(batter.batter_id)}><span className="matchup-order">{batter.batting_order ?? "·"}</span><span><strong>{batter.batter_name}</strong><small>{batter.position}{batter.is_starter === false ? " · 교체" : ""}</small></span><span className="matchup-pair-arrow" aria-hidden="true">›</span></button></li>)}</ol>{!selectableBatters.length && <p className="muted">확인된 출전 타자가 없어요.</p>}</div>
          <article ref={pairPanelRef} className="matchup-pair-result" aria-live="polite"><p className="matchup-kicker">선택한 두 선수의 이전 맞대결</p><h3>{selectedBatter ? `${selectedPitcher.pitcher_name} vs ${selectedBatter.batter_name}` : `${selectedPitcher.pitcher_name}의 상대 타자를 골라 주세요`}</h3><p className="matchup-pair-scope">{detail.game.season} 시즌 · {detail.game.game_date} 이전<br />선택한 날짜의 모든 경기는 제외해요.</p>{!selectedBatter ? <div className="matchup-pair-placeholder"><strong>타자를 누르면 이전 표본이 바로 나와요.</strong><span>옆의 선발 타순에서 한 명을 선택해 주세요.</span></div> : !identifiedPair ? <div className="matchup-pair-placeholder"><strong>선수 식별 정보 확인이 필요해요.</strong><span>{selectedPitcher.pitcher_name}과 {selectedBatter.batter_name}의 선수 ID가 확인되지 않아 이전 기록을 연결할 수 없어요.</span></div> : pairLoading ? <div className="matchup-pair-placeholder" role="status">{selectedPitcher.pitcher_name}과 {selectedBatter.batter_name}의 이전 맞대결을 불러오고 있어요.</div> : currentPair?.error ? <div className="matchup-pair-placeholder"><strong>이전 맞대결을 불러오지 못했어요.</strong><span>{currentPair.error}</span><button type="button" className="secondary" onClick={() => setPairRetry((current) => current + 1)}>다시 시도</button></div> : matchup ? <><dl className="matchup-pair-metrics">{[["이전 맞대결 타석", matchup.plate_appearances], ["안타", matchup.hits], ["홈런", matchup.home_runs], ["삼진", matchup.strikeouts], ["볼넷", matchup.walks], ["사구", matchup.hit_by_pitch]].map(([label, count]) => <div key={label}><dt>{label}</dt><dd>{count}</dd></div>)}</dl>{matchup.plate_appearances === 0 ? <p className="matchup-pair-summary">{detail.game.season} 시즌 {detail.game.game_date} 이전에 확인된 {selectedPitcher.pitcher_name}과 {selectedBatter.batter_name}의 맞대결은 <strong>0타석</strong>이에요.</p> : <p className="matchup-pair-summary">{matchup.game_count !== undefined ? `${matchup.game_count}경기에서 ` : ""}{matchup.plate_appearances}타석을 확인했어요.{matchup.first_seen_date && <> 표본 날짜는 {matchup.first_seen_date}{matchup.last_seen_date && matchup.last_seen_date !== matchup.first_seen_date ? ` ~ ${matchup.last_seen_date}` : ""}예요.</>}{matchup.plate_appearances < 10 && <> 적은 표본이므로 참고 기록으로 확인해 주세요.</>}</p>}{!!matchup.history_events?.length && <div className="matchup-pair-events"><h4>이전 타석 기록</h4><ol>{matchup.history_events.map((event) => <li key={`${event.game_pk}-${event.at_bat_number}`}><span>{event.game_date}{event.inning ? ` · ${event.inning}회` : ""}</span><strong>{eventNames[event.event] ?? event.event}</strong></li>)}</ol></div>}</> : null}{!!history?.data_warnings?.length && <ul className="matchup-data-warnings matchup-pair-warnings">{history.data_warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}{(history?.source_date_range?.from || history?.source_date_range?.through) && <p className="matchup-pair-coverage">타석 자료 범위 {history?.source_date_range?.from ?? "확인되지 않음"} ~ {history?.source_date_range?.through ?? "확인되지 않음"}<br />이 범위에서 선택한 날짜 이전 기록만 집계해요.</p>}</article>
        </section>
        <section className="matchup-pitching-sheet"><div className="matchup-section-title"><div><p className="matchup-kicker">그날의 투구 기록</p><h3>{selectedPitcher.pitcher_name}</h3></div><span>{value(selectedPitcher.game_fields, "등판")}{value(selectedPitcher.game_fields, "결과") !== "—" ? ` · ${value(selectedPitcher.game_fields, "결과")}` : ""}</span></div><dl className="matchup-pitching-metrics">{pitcherStats.map((key) => <div key={key}><dt>{key === "4사구" ? "볼넷·사구" : key}</dt><dd>{value(selectedPitcher.game_fields, key)}</dd></div>)}</dl>{detail.direct_matchup_available ? <div className="matchup-evidence"><strong>{selectedPitcher.pitcher_name}의 당일 직접 상대 타석 기록이에요.</strong><span>{detail.direct_totals?.plate_appearances}타석 · {detail.direct_totals?.hits}안타 · {detail.direct_totals?.strikeouts}삼진 · {detail.direct_totals?.walks}볼넷. 적재된 완료 타석 범위에서 확인한 기록이에요.</span></div> : <div className="matchup-evidence"><strong>아래 타자 성적은 이 경기 전체 성적이에요.</strong><span>{selectedPitcher.pitcher_name}만을 상대한 성적은 아니에요. 해당 투수의 타석별 기록이 있는 경기에서는 직접 맞대결을 함께 보여드려요.</span></div>}</section>
        {!!detail.data_warnings?.length && <ul className="matchup-data-warnings" aria-label="기록 확인 사항">{detail.data_warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
        <section className="matchup-batting-sheet"><div className="matchup-section-title"><div><h3>{teamName(detail.opponent_team_code)} 당일 출전 성적</h3><p>선발 타순과 교체 선수를 함께 확인해 보세요.</p></div><span>{shownBatters.length}명</span></div><div className="matchup-filter-tabs" role="tablist" aria-label="출전 타자 표시 범위"><button type="button" role="tab" aria-selected={filter === "all"} onClick={() => setFilter("all")}>전체 출전</button><button type="button" role="tab" aria-selected={filter === "starters"} onClick={() => setFilter("starters")}>선발 타순</button>{detail.direct_matchup_available && <button type="button" role="tab" aria-selected={filter === "faced"} onClick={() => setFilter("faced")}>{selectedPitcher.pitcher_name} 상대</button>}</div>
          {shownBatters.length ? <ol className="matchup-game-batters">{shownBatters.map((batter) => <li key={batter.batter_id}><div className="matchup-batter-heading"><span className={`matchup-order ${batter.is_starter === false ? "substitute" : ""}`}>{batter.batting_order ?? "·"}</span><div><strong>{batter.batter_name}<small>{batter.position}</small></strong><span>{batter.is_starter === true ? "선발" : batter.is_starter === false ? "교체 출전" : "타석 기록 확인"}</span></div></div><div className="matchup-batter-game-data"><span className="matchup-stat-context">경기 전체 타격 성적</span><dl>{["AB", "H", "RBI", "R"].map((key) => <div key={key}><dt>{labels[key]}</dt><dd>{value(batter.game_fields, key)}</dd></div>)}</dl></div>{batter.direct_matchup && <div className="matchup-direct-result"><strong>{selectedPitcher.pitcher_name} 상대</strong><span>{batter.direct_matchup.plate_appearances}타석 · {batter.direct_matchup.hits}안타 · {batter.direct_matchup.strikeouts}삼진 · {batter.direct_matchup.walks}볼넷 · {batter.direct_matchup.home_runs}홈런</span></div>}<details className="matchup-batter-extra"><summary>이닝별 결과와 시즌 참고 기록</summary><div className="matchup-inning-results">{Object.entries(batter.game_fields).filter(([key, item]) => /회$/.test(key) && item).map(([key, item]) => <div key={key}><small>{key}</small><strong>{item}</strong></div>)}{!Object.keys(batter.game_fields).some((key) => /회$/.test(key) && batter.game_fields[key]) && <span>이닝별 결과가 없어요.</span>}</div><p className="matchup-season-label">시즌 누적 참고 · 선택 경기일 이전 누적 성적과 다를 수 있어요.</p><dl className="matchup-season-reference">{["AVG", "HR", "OBP", "OPS"].map((key) => <div key={key}><dt>{labels[key]}</dt><dd>{value(batter.season_fields, key)}</dd></div>)}</dl></details></li>)}</ol> : <div className="matchup-empty compact">이 범위에서 확인된 타자가 없어요.</div>}
        </section>
      </>}
    </>}
  </div>;
}
