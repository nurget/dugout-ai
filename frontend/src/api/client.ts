export type UserId = string;
export type UserRole = "MANAGER" | "COACH";
export type TeamCode = "KIA" | "SS" | "LG" | "KT" | "SSG" | "NC" | "OB" | "LT" | "HH" | "WO";
export type SeasonPhase = "REGULAR" | "WILDCARD" | "SEMIPLAYOFF" | "PLAYOFF" | "KOREAN_SERIES";

export type User = { id: UserId; username: string; team_code: TeamCode; role: UserRole };
export type TeamSummary = { username: string; team_code: TeamCode; role: UserRole; season: number };
export type Game = { game_pk: string; game_date: string; home_team_code: string; away_team_code: string; home_score: number | null; away_score: number | null; status: string };
export type KboGameRecord = Game & { source_name: string; source_batch_id: string | null };
export type PlayerQualification = { team_games: number | null; min_plate_appearances: number | null; min_innings: number | null; actual_plate_appearances: number | null; actual_outs: number | null; is_qualified: boolean | null; basis: "TEAM_RECORD" | "COMPLETED_GAMES" | "UNKNOWN"; source_url?: string | null; reason: string | null };
export type KboPlayerRecord = { player_id: string; player_name: string; team_code: string; raw_fields: Record<string, string>; qualification?: PlayerQualification; metrics?: Record<string, number | null>; position?: string | null; profile?: Record<string, string>; source_url: string; source_urls?: string[]; collected_at?: string | null; source_batch_id: string | null; imported_at: string };
export type KboTeamCategory = "standings" | "batting" | "pitching" | "defense" | "running";
export type KboTeamRecord = { team_code: string; raw_fields: Record<string, string>; metrics?: Record<string, number | null>; source_url: string; source_urls?: string[]; collected_at?: string | null; imported_at: string };
export type KboTeamRecordsResponse = { season: number; category: KboTeamCategory; count: number; data: KboTeamRecord[]; note: string };
export type KboGameBoxscore = { game_pk: string; game_date: string; source_url: string; teams: Array<{ team_code: string; batters: Array<{ player_id: string; player_name: string; batting_order: number; is_starter: boolean; position?: string | null; raw_fields: Record<string, string> }>; pitchers?: Array<{ player_id: string; player_name: string; raw_fields: Record<string, string> }> }> };
export type Pitcher = { id: number | string; pitcher_name: string; games: number; batters_faced: number | null; strikeouts: number; walks: number; k_pct: number | null; bb_pct: number | null; k_minus_bb_pct: number | null; stat_source?: "KBO_RECORDS" };
export type Batter = {
  player_id: string; player_name: string; team_code: string; games: number;
  plate_appearances: number; at_bats: number; hits: number; singles: number;
  doubles: number; triples: number; home_runs: number; walks: number;
  strikeouts: number; hit_by_pitch: number; sacrifice_flies: number;
  sacrifice_bunts: number; unclassified_outcomes: number; total_bases: number;
  batting_average: number | null; on_base_percentage: number | null;
  slugging_percentage: number | null; ops: number | null;
};
export type TeamBattingStats = {
  season: number; team_code: string; as_of_date: string | null;
  cutoff: "EXCLUSIVE" | null; stat_source: "PBP_DERIVED";
  stat_definition: string; snapshot_id: string | null; source_name: string | null;
  coverage: { date_min: string | null; date_max: string | null; accepted_plate_appearances: number };
  count: number; data: Batter[]; limitations: string[];
};
export type AsOfPitcher = { pitcher_id: string; pitcher_name: string; batters_faced: number | null; identity_status: string; season_fields?: Record<string, string> };
export type MatchupBatter = { batter_id: string; batter_name: string; batter_stand: string | null; last_seen_date: string | null; batting_order?: number; position?: string | null; season_fields?: Record<string, string>; game_fields?: Record<string, string> };
export type MatchupGame = { game_pk: string; game_date: string; home_team_code: string; away_team_code: string; opponent_team_code: string; home_score: number | null; away_score: number | null; status: string; lineup_source: string; batters: MatchupBatter[]; batters_count: number; available_batters?: MatchupBatter[]; lineup_note?: string };
export type DirectMatchupStats = { plate_appearances: number; hits: number; strikeouts: number; walks: number; home_runs: number; hit_by_pitch: number };
export type GameMatchupPitcher = { pitcher_id: string; pitcher_name: string; appearance_order: number; identity_status: string; game_fields: Record<string, string>; season_fields: Record<string, string> };
export type GamePitcherMatchupResponse = {
  game: Game & { season: number };
  team_code: string;
  opponent_team_code: string;
  pitchers: GameMatchupPitcher[];
  selected_pitcher: GameMatchupPitcher | null;
  batters: Array<{ batter_id: string; batter_name: string; batting_order: number | null; is_starter: boolean | null; position: string | null; game_fields: Record<string, string>; season_fields: Record<string, string>; direct_matchup: DirectMatchupStats | null }>;
  direct_matchup_available: boolean;
  direct_totals: DirectMatchupStats | null;
  note: string;
  data_warnings?: string[];
};
export type MatchupAnalysis = {
  team_code: string; opponent_team_code: string; as_of_date: string; lineup_source: string;
  coverage: string; source_name: string | null; source_date_range: { from: string | null; through: string | null } | null;
  pitcher_hand: string; limitations: string[];
  season_batter_records?: Array<{ player_id: string; player_name: string; raw_fields: Record<string, string> }>;
  season_reference_note?: string;
  data_warnings?: string[];
  totals_by_pitcher: Array<{ pitcher_id: string; pitcher_name: string; pa: number; hits: number; strikeouts: number; walks: number; home_runs: number; hit_by_pitch: number }>;
  matchups: Array<{ lineup_order: number; batter_id: string; batter_name: string; batter_stand: string | null; pitcher_id: string; pitcher_name: string; plate_appearances: number; hits: number; strikeouts: number; walks: number; home_runs: number; hit_by_pitch: number; sample_tier: string; interpretation: string; game_count?: number; first_seen_date?: string | null; last_seen_date?: string | null; history_events?: Array<{ game_date: string; game_pk: string; inning: number | null; event: string; at_bat_number: number }> }>;
};
export type BullpenComparisonResult = {
  type: "bullpen_comparison";
  run_id?: string;
  team_code: string;
  as_of_date: string;
  data_through_date?: string | null;
  data_snapshot_id?: string | null;
  coverage?: { status: string; expected_final_games: number; games_with_appearance_data: number; missing_games: number };
  provenance?: { status: string; source_batch_ids: string[]; untracked_appearance_rows: number; untracked_game_rows: number };
  comparison_status?: string;
  availability_verified: boolean;
  candidates: Array<{ pitcher_id: string; pitcher_name: string; k_minus_bb_pct: number; games?: number | null; batters_faced: number; data_through_date?: string | null; identity_status?: string | null; identity_source?: string | null; pitches_last_3_days: number | null; consecutive_days: number | null; workload_status: string }>;
  withheld: Array<{ pitcher_id: string; pitcher_name?: string; reason: string }>;
};
export type RecommendationReview = {
  run_id: string;
  outcome: "ACCEPTABLE_SET" | "NONE_ACCEPTABLE" | "NEEDS_MORE_INFO";
  acceptable_candidate_ids: string[];
  reviewed_at: string;
};
export type SavedMessage = { id: string; role: "user" | "assistant"; content: string; created_at: string; analysis_results: BullpenComparisonResult[] };
type LoginResponse = { access_token: string; token_type: "bearer"; expires_in: number };
type TeamGamesResponse = { team_code: TeamCode; season: number; season_type: "REGULAR" | "POSTSEASON"; count: number; data: Game[] };
type KboGamesResponse = { season: number; season_type: "REGULAR" | "POSTSEASON"; count: number; data: KboGameRecord[]; note: string };
type KboPlayerRecordsResponse = { season: number; season_type: "REGULAR" | "POSTSEASON"; category: "batter" | "pitcher"; count: number; data: KboPlayerRecord[]; note: string };
type TeamPitchersResponse = { team_code: TeamCode; season: number; season_type: string; count: number; data: Pitcher[]; note: string };
type ConversationMessagesResponse = { conversation_id: string; messages: SavedMessage[] };

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
export const tokenKey = "dugout_access_token";

export function getToken() { return localStorage.getItem(tokenKey); }
export function setToken(token: string) { localStorage.setItem(tokenKey, token); }
export function clearToken() { localStorage.removeItem(tokenKey); }

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}, token = getToken()): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = `요청에 실패했습니다. (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail ?? body.message ?? message;
    } catch {
      message = `요청에 실패했습니다. (${response.status})`;
    }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) => request<LoginResponse>("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }, null),
  register: (username: string, password: string, teamCode: TeamCode) => request<User>("/api/auth/register", { method: "POST", body: JSON.stringify({ username, password, team_code: teamCode }) }, null),
  me: () => request<User>("/api/auth/me"),
  team: () => request<TeamSummary>("/api/teams/me"),
  games: (phase: SeasonPhase = "REGULAR") => request<TeamGamesResponse>(`/api/teams/me/games?season=2026&season_type=${phase === "REGULAR" ? "REGULAR" : "POSTSEASON"}${phase === "REGULAR" ? "" : `&season_phase=${phase}`}`),
  kboGames: (season: number, seasonType: "REGULAR" | "POSTSEASON", teamCode?: string) => {
    const query = new URLSearchParams({ season: String(season), season_type: seasonType, limit: "1000" });
    if (teamCode) query.set("team_code", teamCode);
    return request<KboGamesResponse>(`/api/kbo/games?${query}`);
  },
  kboPlayerRecords: (season: number, seasonType: "REGULAR" | "POSTSEASON", category: "batter" | "pitcher", teamCode?: string, name?: string, includePitchers = false, qualifiedOnly = false) => {
    const query = new URLSearchParams({ season: String(season), season_type: seasonType, category, limit: "1000" });
    if (teamCode) query.set("team_code", teamCode);
    if (name) query.set("name", name);
    if (includePitchers) query.set("include_pitchers", "true");
    if (qualifiedOnly) query.set("qualified_only", "true");
    return request<KboPlayerRecordsResponse>(`/api/kbo/records/players?${query}`);
  },
  kboTeamRecords: (season: number, category: KboTeamCategory, teamCode?: string) => {
    const query = new URLSearchParams({ season: String(season), category });
    if (teamCode) query.set("team_code", teamCode);
    return request<KboTeamRecordsResponse>(`/api/kbo/records/teams?${query}`);
  },
  kboCoverage: (season: number) => request<{ season: number; stat_source: string; data: Array<{ scope: "players" | "teams"; category: string; season_type: string; count: number; collected_at: string | null; imported_at: string | null }> }>(`/api/kbo/records/coverage?season=${season}`),
  matchupCalendar: (season: number) => request<{ season: number; latest_game_date: string | null; data: Array<{ game_date: string; count: number }> }>(`/api/kbo/matchups/calendar?season=${season}`),
  matchupPitchers: (gameDate: string) => request<{ data: Array<AsOfPitcher & { batters_faced: number | null; record_source: string; season_fields?: Record<string, string> }>; note: string }>(`/api/kbo/matchups/pitchers?season=${gameDate.slice(0, 4)}&game_date=${encodeURIComponent(gameDate)}`),
  kboGameDetails: (gamePk: string) => request<KboGameBoxscore>(`/api/kbo/games/${encodeURIComponent(gamePk)}/boxscore`),
  gamePitcherMatchup: (gamePk: string, pitcherId?: string) => request<GamePitcherMatchupResponse>(`/api/kbo/games/${encodeURIComponent(gamePk)}/pitcher-matchup${pitcherId ? `?pitcher_id=${encodeURIComponent(pitcherId)}` : ""}`),
  pitchers: (phase: SeasonPhase = "REGULAR") => request<TeamPitchersResponse>(`/api/teams/me/pitchers?season=2026&season_type=${phase}`),
  batters: (season: number, asOfDate: string) => request<TeamBattingStats>(`/api/teams/me/batters?season=${season}&as_of_date=${encodeURIComponent(asOfDate)}`),
  asOfPitchers: (asOfDate: string) => request<{ data: AsOfPitcher[] }>(`/api/teams/me/pitchers?season=2026&as_of_date=${encodeURIComponent(asOfDate)}`),
  matchupBatters: (opponent: TeamCode, asOfDate: string, query: string) => request<{ data: MatchupBatter[] }>(`/api/teams/me/matchup-batters?opponent_team_code=${encodeURIComponent(opponent)}&season=2026&as_of_date=${encodeURIComponent(asOfDate)}&query=${encodeURIComponent(query)}`),
  matchupGames: (gameDate: string) => request<{ team_code: TeamCode; game_date: string; count: number; data: MatchupGame[]; note: string }>(`/api/teams/me/matchup-games?season=2026&game_date=${encodeURIComponent(gameDate)}`),
  pitcherMatchups: (payload: { season: number; as_of_date: string; opponent_team_code: string; pitcher_ids: string[]; batter_ids: string[] }) => request<MatchupAnalysis>("/api/teams/me/pitcher-matchups", { method: "POST", body: JSON.stringify(payload) }),
  messages: (id: string) => request<ConversationMessagesResponse>(`/api/agent/conversations/${id}/messages`),
  recommendationReview: (runId: string) => request<{ review: RecommendationReview | null }>(`/api/agent/runs/${encodeURIComponent(runId)}/recommendation-review`),
  saveRecommendationReview: (runId: string, payload: { outcome: RecommendationReview["outcome"]; acceptable_candidate_ids: string[] }) => request<{ review: RecommendationReview }>(`/api/agent/runs/${encodeURIComponent(runId)}/recommendation-review`, { method: "PUT", body: JSON.stringify(payload) }),
};

export function apiUrl(path: string) { return `${baseUrl}${path}`; }
