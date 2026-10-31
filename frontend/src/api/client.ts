export type User = { id: number; username: string; team_code: string; role: "MANAGER" | "COACH" | string };
export type TeamSummary = { username: string; team_code: string; role: string; season: number };
export type Game = { game_pk: string; game_date: string; home_team_code: string; away_team_code: string; home_score: number | null; away_score: number | null; status: string };
export type Pitcher = { id: number; pitcher_name: string; games: number; batters_faced: number; strikeouts: number; walks: number; k_pct: number; bb_pct: number; k_minus_bb_pct: number };
export type SavedMessage = { id: string; role: "user" | "assistant"; content: string; created_at: string };

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
    try { const body = await response.json(); message = body.detail ?? body.message ?? message; } catch { /* non-JSON error */ }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) => request<{ access_token: string; token_type: string; expires_in: number }>("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }, null),
  me: () => request<User>("/api/auth/me"),
  team: () => request<TeamSummary>("/api/teams/me"),
  games: () => request<{ data: Game[] }>("/api/teams/me/games?season=2026"),
  pitchers: () => request<{ data: Pitcher[]; note: string }>("/api/teams/me/pitchers?season=2026"),
  messages: (id: string) => request<{ messages: SavedMessage[] }>(`/api/agent/conversations/${id}/messages`),
};

export function apiUrl(path: string) { return `${baseUrl}${path}`; }
