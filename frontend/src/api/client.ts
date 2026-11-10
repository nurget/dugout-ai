export type UserId = string;
export type UserRole = "MANAGER" | "COACH";
export type TeamCode = "KIA" | "SS" | "LG" | "KT" | "SSG" | "NC" | "OB" | "LT" | "HH" | "WO";
export type SeasonPhase = "REGULAR" | "WILDCARD" | "SEMIPLAYOFF" | "PLAYOFF" | "KOREAN_SERIES";

export type User = { id: UserId; username: string; team_code: TeamCode; role: UserRole };
export type TeamSummary = { username: string; team_code: TeamCode; role: UserRole; season: number };
export type Game = { game_pk: string; game_date: string; home_team_code: string; away_team_code: string; home_score: number | null; away_score: number | null; status: string };
export type Pitcher = { id: number | string; pitcher_name: string; games: number; batters_faced: number | null; strikeouts: number; walks: number; k_pct: number | null; bb_pct: number | null; k_minus_bb_pct: number | null; stat_source?: "KBO_OFFICIAL" };
export type AsOfPitcher = { pitcher_id: string; pitcher_name: string; batters_faced: number; identity_status: string };
export type MatchupBatter = { batter_id: string; batter_name: string; batter_stand: string | null; last_seen_date: string };
export type MatchupGame = { game_pk: string; game_date: string; home_team_code: string; away_team_code: string; opponent_team_code: string; home_score: number | null; away_score: number | null; status: string; lineup_source: string; batters: MatchupBatter[]; batters_count: number };
export type MatchupAnalysis = {
  team_code: string; opponent_team_code: string; as_of_date: string; lineup_source: string;
  coverage: string; source_name: string | null; source_date_range: { from: string | null; through: string | null } | null;
  pitcher_hand: string; limitations: string[];
  totals_by_pitcher: Array<{ pitcher_id: string; pitcher_name: string; pa: number; hits: number; strikeouts: number; walks: number; home_runs: number; hit_by_pitch: number }>;
  matchups: Array<{ lineup_order: number; batter_id: string; batter_name: string; batter_stand: string | null; pitcher_id: string; pitcher_name: string; plate_appearances: number; hits: number; strikeouts: number; walks: number; home_runs: number; hit_by_pitch: number; sample_tier: string; interpretation: string }>;
};
export type BullpenComparisonResult = {
  type: "bullpen_comparison";
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
export type SavedMessage = { id: string; role: "user" | "assistant"; content: string; created_at: string; analysis_results: BullpenComparisonResult[] };
type LoginResponse = { access_token: string; token_type: "bearer"; expires_in: number };
type TeamGamesResponse = { team_code: TeamCode; season: number; season_type: "REGULAR" | "POSTSEASON"; count: number; data: Game[] };
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
  pitchers: (phase: SeasonPhase = "REGULAR") => request<TeamPitchersResponse>(`/api/teams/me/pitchers?season=2026&season_type=${phase}`),
  asOfPitchers: (asOfDate: string) => request<{ data: AsOfPitcher[] }>(`/api/teams/me/pitchers?season=2026&as_of_date=${encodeURIComponent(asOfDate)}`),
  matchupBatters: (opponent: TeamCode, asOfDate: string, query: string) => request<{ data: MatchupBatter[] }>(`/api/teams/me/matchup-batters?opponent_team_code=${encodeURIComponent(opponent)}&season=2026&as_of_date=${encodeURIComponent(asOfDate)}&query=${encodeURIComponent(query)}`),
  matchupGames: (gameDate: string) => request<{ team_code: TeamCode; game_date: string; count: number; data: MatchupGame[]; note: string }>(`/api/teams/me/matchup-games?season=2026&game_date=${encodeURIComponent(gameDate)}`),
  pitcherMatchups: (payload: { season: number; as_of_date: string; opponent_team_code: string; pitcher_ids: string[]; batter_ids: string[] }) => request<MatchupAnalysis>("/api/teams/me/pitcher-matchups", { method: "POST", body: JSON.stringify(payload) }),
  messages: (id: string) => request<ConversationMessagesResponse>(`/api/agent/conversations/${id}/messages`),
};

export function apiUrl(path: string) { return `${baseUrl}${path}`; }
