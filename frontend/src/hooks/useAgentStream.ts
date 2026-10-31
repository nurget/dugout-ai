import { useRef, useState } from "react";
import { apiUrl, getToken } from "../api/client";

export type AgentStatus = "idle" | "connecting" | "analyzing" | "generating" | "completed" | "failed" | "cancelled";
export type ToolEvent = { tool: string; ok?: boolean; round?: number; duration_ms?: number; error?: { code: string; message: string } | null };

export function useAgentStream(accountId: number | null, onUnauthorized: () => void) {
  const storageKey = accountId ? `dugout_conversation_id:${accountId}` : "";
  const [conversationId, setConversationId] = useState<string | null>(() => storageKey ? sessionStorage.getItem(storageKey) : null);
  const [answer, setAnswer] = useState(""); const [tools, setTools] = useState<ToolEvent[]>([]); const [status, setStatus] = useState<AgentStatus>("idle"); const [error, setError] = useState<string | null>(null); const [historyVersion, setHistoryVersion] = useState(0);
  const controllerRef = useRef<AbortController | null>(null); const runningRef = useRef(false);
  function storeConversation(id: string | null) { if (!storageKey) return; if (id) sessionStorage.setItem(storageKey, id); else sessionStorage.removeItem(storageKey); setConversationId(id); }
  async function sendMessage(message: string) {
    if (!accountId || runningRef.current || !message.trim()) return;
    runningRef.current = true; const controller = new AbortController(); controllerRef.current = controller; setAnswer(""); setTools([]); setError(null); setStatus("connecting"); let completed = false; let streamError = false;
    const processEvent = (block: string) => { const name = block.split("\n").find((line) => line.startsWith("event:"))?.slice(6).trim(); const raw = block.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n"); if (!name || !raw) return; let data: Record<string, unknown>; try { data = JSON.parse(raw) as Record<string, unknown>; } catch { return; }
      if (name === "conversation" && typeof data.conversation_id === "string") storeConversation(data.conversation_id); else if (name === "started") setStatus("analyzing"); else if (name === "tool_start") setTools((old) => [...old, data as unknown as ToolEvent]); else if (name === "tool_result") setTools((old) => { const index = old.findLastIndex((tool) => tool.tool === data.tool && tool.ok === undefined); return index < 0 ? old : old.map((tool, i) => i === index ? { ...tool, ...data as ToolEvent } : tool); }); else if (name === "answer_delta" && typeof data.delta === "string") { setStatus("generating"); setAnswer((old) => old + data.delta); } else if (name === "completed") { completed = true; setStatus("completed"); setHistoryVersion((old) => old + 1); } else if (name === "error") { streamError = true; setError(typeof data.message === "string" ? data.message : "AI 분석 중 오류가 발생했습니다."); setStatus("failed"); } };
    try { const token = getToken(); const response = await fetch(apiUrl("/api/agent/chat/stream"), { method: "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify({ message: message.trim(), conversation_id: conversationId }), signal: controller.signal }); if (response.status === 401) { onUnauthorized(); throw new Error("로그인이 만료되었습니다."); } if (response.status === 404) { storeConversation(null); throw new Error("저장된 대화를 찾을 수 없어 새 대화를 시작했습니다."); } if (!response.ok) throw new Error(`AI 요청에 실패했습니다. (${response.status})`); if (!response.body) throw new Error("스트리밍 응답 본문이 없습니다."); const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ""; const consume = () => { const normalized = buffer.replace(/\r\n/g, "\n"); const boundary = normalized.lastIndexOf("\n\n"); if (boundary < 0) return; buffer = normalized.slice(boundary + 2); normalized.slice(0, boundary).split("\n\n").filter(Boolean).forEach(processEvent); }; while (true) { const { done, value } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true }); consume(); } buffer += decoder.decode(); consume(); if (!completed && !streamError) throw new Error("완료 이벤트 없이 스트리밍 연결이 종료되었습니다."); }
    catch (caught) { if (controller.signal.aborted) setStatus("cancelled"); else { setError(caught instanceof Error ? caught.message : "알 수 없는 오류"); setStatus("failed"); } } finally { runningRef.current = false; if (controllerRef.current === controller) controllerRef.current = null; }
  }
  function cancel() { controllerRef.current?.abort(); }
  function startNewConversation() { if (runningRef.current) return; storeConversation(null); setAnswer(""); setTools([]); setError(null); setStatus("idle"); }
  return { conversationId, answer, tools, status, error, historyVersion, sendMessage, cancel, startNewConversation };
}
