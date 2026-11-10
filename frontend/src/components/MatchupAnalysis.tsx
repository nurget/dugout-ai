import { useEffect, useState } from "react";
import { api, ApiError, type AsOfPitcher, type MatchupAnalysis, type MatchupBatter, type MatchupGame, type TeamCode } from "../api/client";
import "./MatchupAnalysis.css";

const today = () => new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const tier = (value: string) => ({ NO_DIRECT_HISTORY: "맞대결 없음", VERY_SMALL: "매우 작은 표본", LIMITED: "제한된 표본", OBSERVATIONAL: "관측 표본" }[value] ?? value);
const teamName: Record<string, string> = { KIA: "KIA 타이거즈", SS: "삼성 라이온즈", SAM: "삼성 라이온즈", LG: "LG 트윈스", KT: "KT 위즈", SSG: "SSG 랜더스", SK: "SSG 랜더스", NC: "NC 다이노스", OB: "두산 베어스", DOO: "두산 베어스", LT: "롯데 자이언츠", LOT: "롯데 자이언츠", HH: "한화 이글스", HAN: "한화 이글스", WO: "키움 히어로즈", KIW: "키움 히어로즈" };

export function MatchupAnalysis({ teamCode, logout }: { teamCode: TeamCode; logout: () => void }) {
  const [asOfDate, setAsOfDate] = useState(today);
  const [games, setGames] = useState<MatchupGame[]>([]);
  const [selectedGamePk, setSelectedGamePk] = useState("");
  const [pitchers, setPitchers] = useState<AsOfPitcher[]>([]);
  const [selectedPitchers, setSelectedPitchers] = useState<string[]>([]);
  const [lineup, setLineup] = useState<MatchupBatter[]>([]);
  const [analysis, setAnalysis] = useState<MatchupAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedAsOfDate, setLoadedAsOfDate] = useState<string | null>(null);
  const loadingPitchers = loadedAsOfDate !== asOfDate;
  const [loadedGamesDate, setLoadedGamesDate] = useState<string | null>(null);
  const loadingGames = loadedGamesDate !== asOfDate;
  const selectedGame = games.find((game) => game.game_pk === selectedGamePk) ?? null;
  const opponent = selectedGame?.opponent_team_code;
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    api.asOfPitchers(asOfDate).then(({ data }) => {
      if (!active) return;
      setPitchers(data);
      setLoadedAsOfDate(asOfDate);
    }).catch((err) => {
      if (!active) return;
      if (err instanceof ApiError && err.status === 401) logout();
      setError(err instanceof Error ? err.message : "투수 목록을 불러오지 못했습니다.");
      setPitchers([]);
      setLoadedAsOfDate(asOfDate);
    });
    return () => { active = false; };
  }, [asOfDate, logout]);

  useEffect(() => {
    let active = true;
    setGames([]);
    setSelectedGamePk("");
    setLineup([]);
    setAnalysis(null);
    setLoadedGamesDate(null);
    api.matchupGames(asOfDate).then(({ data }) => {
      if (!active) return;
      setGames(data);
      setSelectedGamePk(data[0]?.game_pk ?? "");
      setLineup(data[0]?.batters ?? []);
      setLoadedGamesDate(asOfDate);
    }).catch((err) => {
      if (!active) return;
      if (err instanceof ApiError && err.status === 401) logout();
      setError(err instanceof Error ? err.message : "해당 날짜의 경기를 불러오지 못했습니다.");
      setLoadedGamesDate(asOfDate);
    });
    return () => { active = false; };
  }, [asOfDate, logout]);

  function moveBatter(index: number, direction: -1 | 1) {
    const next = [...lineup];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setLineup(next);
    setAnalysis(null);
  }

  async function compare() {
    setBusy(true);
    setError(null);
    setAnalysis(null);
    try {
      const result = await api.pitcherMatchups({
        season: Number(asOfDate.slice(0, 4)), as_of_date: asOfDate,
        opponent_team_code: opponent!, pitcher_ids: selectedPitchers,
        batter_ids: lineup.map((batter) => batter.batter_id),
      });
      setAnalysis(result);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) logout();
      setError(err instanceof Error ? err.message : "맞대결을 조회하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return <>
    <div className="page-head">
      <p className="eyebrow">HISTORICAL MATCHUPS · BETA</p>
      <h2>상대 타순 맞대결</h2>
      <p className="muted">경기 날짜를 고르면 해당 경기의 상대팀과 PBP 관측 타자를 불러와 기준일 이전 맞대결을 보여줍니다.</p>
      <p className="notice">자동 입력 타순은 PBP에서 첫 타석이 나온 순서이며 공식 선발 라인업과 다를 수 있습니다. 직접 맞대결 기록은 표본이 작을 수 있습니다.</p>
    </div>
    <section className="panel matchup-panel">
      <div className="matchup-controls">
        <label>경기 날짜<input type="date" min="2026-01-01" max={today()} value={asOfDate} onChange={(e) => { setAsOfDate(e.target.value); setSelectedPitchers([]); setGames([]); setLineup([]); setAnalysis(null); setError(null); }} /></label>
        {games.length > 1 && <label>경기<select value={selectedGamePk} onChange={(e) => { const game = games.find((item) => item.game_pk === e.target.value); setSelectedGamePk(e.target.value); setLineup(game?.batters ?? []); setAnalysis(null); }}>
          {games.map((game, index) => <option value={game.game_pk} key={game.game_pk}>{teamName[game.away_team_code] ?? game.away_team_code} @ {teamName[game.home_team_code] ?? game.home_team_code} · {index + 1}차전</option>)}
        </select></label>}
      </div>
      {loadingGames ? <p className="muted">해당 날짜의 경기를 찾는 중…</p> : selectedGame ? <p className="matchup-game-summary">{teamName[selectedGame.away_team_code] ?? selectedGame.away_team_code} @ {teamName[selectedGame.home_team_code] ?? selectedGame.home_team_code} · 상대팀 <strong>{teamName[opponent!] ?? opponent}</strong> · {selectedGame.batters_count ? `PBP 관측 타자 ${selectedGame.batters_count}명` : "경기는 확인했지만 PBP 타자 데이터가 없습니다."}</p> : <p className="muted">{asOfDate}에 {teamName[teamCode] ?? teamCode} 경기가 등록되어 있지 않습니다.</p>}
      <div className="matchup-columns">
        <section className="matchup-step">
          <h3>1. 후보 투수 선택 <small>최대 5명</small></h3>
          {loadingPitchers ? <p className="muted">기준일 누적 기록을 불러오는 중…</p> : pitchers.length ? <div className="matchup-options">
            {pitchers.map((pitcher) => <label key={pitcher.pitcher_id}>
              <input type="checkbox" checked={selectedPitchers.includes(pitcher.pitcher_id)} disabled={!selectedPitchers.includes(pitcher.pitcher_id) && selectedPitchers.length >= 5} onChange={(e) => setSelectedPitchers((items) => e.target.checked ? [...items, pitcher.pitcher_id] : items.filter((id) => id !== pitcher.pitcher_id))} />
              <span>{pitcher.pitcher_name}<small>{pitcher.batters_faced} BF · ID {pitcher.pitcher_id}</small></span>
            </label>)}
          </div> : <p className="muted">기준일 누적 투수 데이터가 없습니다.</p>}
        </section>
        <section className="matchup-step">
          <h3>2. 경기에서 관측된 타자 <small>{lineup.length}명</small></h3>
          <p className="muted">첫 타석이 나온 순서로 자동 정렬했습니다.</p>
          <ol className="matchup-lineup">{lineup.map((batter, index) => <li key={batter.batter_id}>
            <span>{batter.batter_name}<small>{batter.batter_stand ?? "손 정보 없음"}</small></span>
            <div><button type="button" aria-label="타순 위로" onClick={() => moveBatter(index, -1)} disabled={index === 0}>↑</button><button type="button" aria-label="타순 아래로" onClick={() => moveBatter(index, 1)} disabled={index === lineup.length - 1}>↓</button><button type="button" aria-label="타순에서 제거" onClick={() => { setLineup((items) => items.filter((item) => item.batter_id !== batter.batter_id)); setAnalysis(null); }}>×</button></div>
          </li>)}</ol>
        </section>
      </div>
      {error && <p className="error matchup-error">{error}</p>}
      <div className="matchup-submit"><small>기준일 당일 경기 결과는 맞대결 통계에서 제외됩니다.</small><button className="primary" onClick={() => void compare()} disabled={busy || loadingPitchers || loadingGames || !opponent || !selectedPitchers.length || !lineup.length}>{busy ? "맞대결 조회 중…" : "직접 맞대결 비교"}</button></div>
    </section>
    {analysis && <section className="panel matchup-output">
      <div className="panel-title"><h3>{teamName[opponent!] ?? opponent} 상대 직접 맞대결</h3><span>{analysis.as_of_date} 기준</span></div>
      <p className="matchup-source">출처: {analysis.source_name ?? "확인 불가"} · 기록 기간: {analysis.source_date_range?.from ?? "?"} ~ {analysis.source_date_range?.through ?? "?"}</p>
      <div className="table-wrap"><table><thead><tr><th>타순</th><th>타자</th><th>후보 투수</th><th>타석</th><th>안타</th><th>삼진</th><th>볼넷</th><th>홈런</th><th>표본</th></tr></thead><tbody>
        {analysis.matchups.map((row) => <tr key={`${row.pitcher_id}-${row.batter_id}`}><td>{row.lineup_order}</td><td>{row.batter_name} ({row.batter_stand ?? "?"})</td><td>{row.pitcher_name}</td><td>{row.plate_appearances}</td><td>{row.hits}</td><td>{row.strikeouts}</td><td>{row.walks}</td><td>{row.home_runs}</td><td>{tier(row.sample_tier)}</td></tr>)}
      </tbody></table></div>
      <ul className="matchup-limitations">{analysis.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
    </section>}
  </>;
}
