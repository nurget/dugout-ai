import { useRef, useState } from "react";

type Status =
  | "idle"
  | "connecting"
  | "analyzing"
  | "generating"
  | "completed"
  | "failed"
  | "cancelled";

type ToolEvent = {
  tool: string;
  ok?: boolean;
  round?: number;
  error?: {
    code: string;
    message: string;
  } | null;
};

const STORAGE_KEY = "dugout_conversation_id";

export function useAgentStream() {
  const [answer, setAnswer] = useState("");
  const [tools, setTools] = useState<ToolEvent[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);

  const [conversationId, setConversationId] = useState<string | null>(
    () => sessionStorage.getItem(STORAGE_KEY)
  );

  const [historyVersion, setHistoryVersion] = useState(0);
  const controllerRef = useRef<AbortController | null>(null);

  // 동일한 요청이 진행 중일 때 중복 전송되는 것을 막는다.
  const runningRef = useRef(false);

  async function sendMessage(message: string) {
    if (runningRef.current || !message.trim()) return;

    runningRef.current = true;

    const controller = new AbortController();
    controllerRef.current = controller;

    setAnswer("");
    setTools([]);
    setError(null);
    setStatus("connecting");

    console.log("[DUGOUT] 요청 시작:", message);

    let receivedCompleted = false;
    let receivedError = false;

    function processEvent(block: string) {
      const lines = block.split("\n");

      const eventLine = lines.find((line) =>
        line.startsWith("event:")
      );

      const dataLines = lines
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart());

      if (!eventLine || dataLines.length === 0) return;

      const eventName = eventLine.slice(6).trim();
      const data = JSON.parse(dataLines.join("\n"));

      console.log("[DUGOUT] SSE:", eventName, data);

      switch (eventName) {
        case "conversation":
          sessionStorage.setItem(
            STORAGE_KEY,
            data.conversation_id
          );
          setConversationId(data.conversation_id);
          break;

        case "started":
          setStatus("analyzing");
          break;

        case "tool_start":
          setTools((prev) => [...prev, data as ToolEvent]);
          break;

        case "tool_result":
          setTools((prev) => {
            const next = [...prev];

            const index = next.findLastIndex(
              (tool) =>
                tool.tool === data.tool &&
                tool.ok === undefined
            );

            if (index !== -1) {
              next[index] = { ...next[index], ...data };
            }

            return next;
          });
          break;

        case "answer_delta":
          setStatus("generating");
          setAnswer((prev) => prev + data.delta);
          break;

        case "completed":
          receivedCompleted = true;
          setStatus("completed");

          // DB 저장 완료 이벤트를 받은 뒤에만 이력을 다시 조회한다.
          setHistoryVersion((prev) => prev + 1);
          break;

        case "error":
          receivedError = true;
          setError(data.message ?? "AI 분석 중 오류가 발생했습니다.");
          setStatus("failed");
          break;
      }
    }

    try {
      const response = await fetch("/api/agent/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message,
          conversation_id: conversationId,
        }),
        signal: controller.signal,
      });

      console.log("[DUGOUT] HTTP:", response.status);

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error(
            "저장된 대화를 찾을 수 없습니다. '새 대화'를 눌러주세요."
          );
        }

        throw new Error(`API 요청 실패: HTTP ${response.status}`);
      }

      if (!response.body) {
        throw new Error("스트리밍 응답 본문이 없습니다.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let buffer = "";

      // TextDecoder는 바이트가 청크 경계에서 잘려도 복원할 수 있다.
      // 줄바꿈 정규화는 전체 텍스트가 아닌 SSE 파싱 단계에서 처리한다.
      function consumeBuffer() {
        const normalized = buffer.replace(/\r\n/g, "\n");
        const lastBoundary = normalized.lastIndexOf("\n\n");

        if (lastBoundary === -1) return;

        const complete = normalized.slice(0, lastBoundary);
        buffer = normalized.slice(lastBoundary + 2);

        for (const block of complete.split("\n\n")) {
          if (block.trim()) processEvent(block);
        }
      }

      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        consumeBuffer();
      }

      buffer += decoder.decode();
      consumeBuffer();

      if (!receivedCompleted && !receivedError) {
        throw new Error(
          "완료 이벤트 없이 스트리밍 연결이 종료되었습니다."
        );
      }
    } catch (err) {
      if (controller.signal.aborted) {
        setStatus("cancelled");
      } else {
        const message =
          err instanceof Error ? err.message : "알 수 없는 오류";

        console.error("[DUGOUT] 요청 실패:", err);

        setError(message);
        setStatus("failed");
      }
    } finally {
      runningRef.current = false;

      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    }
  }

  function cancel() {
    controllerRef.current?.abort();
  }

  function startNewConversation() {
    // 진행 중인 요청의 취소 처리가 끝나기 전에는 새 대화를 열지 않는다.
    if (runningRef.current) return;

    sessionStorage.removeItem(STORAGE_KEY);

    setConversationId(null);
    setAnswer("");
    setTools([]);
    setError(null);
    setStatus("idle");
  }

  return {
    conversationId,
    answer,
    tools,
    status,
    error,
    historyVersion,
    sendMessage,
    cancel,
    startNewConversation,
  };
}