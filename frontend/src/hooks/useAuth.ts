/* eslint-disable react-hooks/set-state-in-effect */
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, clearToken, getToken, setToken, type User } from "../api/client";

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(Boolean(getToken()));

  const logout = useCallback(() => { clearToken(); setUser(null); }, []);
  const refresh = useCallback(async () => {
    if (!getToken()) { setChecking(false); return; }
    setChecking(true);
    try { setUser(await api.me()); }
    catch (error) { if (error instanceof ApiError && error.status === 401) logout(); else setUser(null); }
    finally { setChecking(false); }
  }, [logout]);

  useEffect(() => { void refresh(); }, [refresh]);
  const login = useCallback(async (username: string, password: string) => {
    const response = await api.login(username, password);
    setToken(response.access_token);
    try { setUser(await api.me()); } catch (error) { logout(); throw error; }
  }, [logout]);
  return { user, checking, login, logout, refresh };
}
