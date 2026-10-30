import { useRef, useState } from "react";

type ToolEvent = {
  tool: string;
  ok?: boolean;
  round?: number;
  error?: {
    code: string;
    message: string;
  } | null;
};

export function useAgentStream() {
  const [answer, setAnswer] = useState("");
  const [tools, setTools] = useState<ToolEvent[]>([]);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState<string | null>(null);

  const abortController = useRef<AbortController | null>(null);

  async function sendMessage(message: string) {
    abortController.current?.abort();

    const controller = new AbortController();
    abortController.current = controller;

    setAnswer("");
    setTools([]);
    setError(null);
    setStatus("connecting");

    try {
      const response = await fetch("/api/agent/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`요청 실패: HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      // 네트워크 청크와 SSE 이벤트의 경계는 일치하지 않는다.
      // 따라서 잘린 이벤트를 버리지 않고 다음 청크와 이어 붙인다.
      let buffer = "";
      let completed = false;

      function processEvent(block: string) {
        const lines = block.split("\n");
        const eventLine = lines.find((line) =>
          line.startsWith("event:")
        );

        const dataLines = lines
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart());

        if (!eventLine || dataLines.length === 0) return;

        const event = eventLine.slice(6).trim();
        const data = JSON.parse(dataLines.join("\n"));

        switch (event) {
          case "started":
            setStatus("analyzing");
            break;

          case "tool_start":
            setTools((prev) => [...prev, data]);
            break;

          case "tool_result":
            setTools((prev) => {
              const next = [...prev];
              const index = next.findLastIndex(
                (tool) =>
                  tool.tool === data.tool &&
                  tool.ok === undefined
              );

              if (index >= 0) {
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
            completed = true;
            setStatus("completed");
            break;

          case "error":
            completed = true;
            setError(data.message ?? "AI 분석에 실패했습니다.");
            setStatus("failed");
            break;
        }
      }

      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        buffer += decoder
          .decode(value, { stream: true })
          .replace(/\r\n/g, "\n");

        let boundary = buffer.indexOf("\n\n");

        while (boundary !== -1) {
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);

          processEvent(block);
          boundary = buffer.indexOf("\n\n");
        }
      }

      if (!completed) {
        throw new Error("스트림이 완료 이벤트 없이 종료됐습니다.");
      }
    } catch (err) {
      if (controller.signal.aborted) {
        setStatus("cancelled");
        return;
      }

      setError(
        err instanceof Error ? err.message : "알 수 없는 오류"
      );
      setStatus("failed");
    } finally {
      if (abortController.current === controller) {
        abortController.current = null;
      }
    }
  }

  function cancel() {
    abortController.current?.abort();
  }

  return {
    answer,
    tools,
    status,
    error,
    sendMessage,
    cancel,
  };
}