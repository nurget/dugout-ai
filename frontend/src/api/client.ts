export type UserId = string;
export type UserRole = "MANAGER" | "COACH";
export type TeamCode = "KIA" | "SS" | "LG" | "KT" | "SSG" | "NC" | "OB" | "LT" | "HH" | "WO";
export type SeasonPhase = "REGULAR" | "WILDCARD" | "SEMIPLAYOFF" | "PLAYOFF" | "KOREAN_SERIES";

export type User = { id: UserId; username: string; team_code: TeamCode; role: UserRole };
export type TeamSummary = { username: string; team_code: TeamCode; role: UserRole; season: number };
export type Game = { game_pk: string; game_date: string; home_team_code: string; away_team_code: string; home_score: number | null; away_score: number | null; status: string };
export type Pitcher = { id: number | string; pitcher_name: string; games: number; batters_faced: number | null; strikeouts: number; walks: number; k_pct: number | null; bb_pct: number | null; k_minus_bb_pct: number | null; stat_source?: "KBO_OFFICIAL" };
export type BullpenComparisonResult = {
  type: "bullpen_comparison";
  team_code: string;
  as_of_date: string;
  availability_verified: boolean;
  candidates: Array<{ pitcher_id: string; pitcher_name: string; k_minus_bb_pct: number; batters_faced: number; pitches_last_3_days: number | null; consecutive_days: number | null; workload_status: string }>;
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
  messages: (id: string) => request<ConversationMessagesResponse>(`/api/agent/conversations/${id}/messages`),
};

export function apiUrl(path: string) { return `${baseUrl}${path}`; }
