import { useEffect, useState } from "react";
import { useAgentStream } from "./hooks/useAgentStream";
import "./App.css";

type SavedMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

const EXAMPLE_QUESTION =
  "경기 ID 1의 상태 ID 1과 선수 ID 1을 조회하고 KIA의 다른 투수 후보를 알려줘.";

function App() {
  const [message, setMessage] = useState(EXAMPLE_QUESTION);
  const [savedMessages, setSavedMessages] = useState<SavedMessage[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const {
    conversationId,
    answer,
    tools,
    status,
    error,
    historyVersion,
    sendMessage,
    cancel,
    startNewConversation,
  } = useAgentStream();

  const loading = [
    "connecting",
    "analyzing",
    "generating",
  ].includes(status);

  useEffect(() => {
    if (!conversationId) {
      setSavedMessages([]);
      setHistoryError(null);
      return;
    }

    const controller = new AbortController();

    async function loadMessages() {
      try {
        const response = await fetch(
          `/api/agent/conversations/${conversationId}/messages`,
          { signal: controller.signal }
        );

        if (!response.ok) {
          throw new Error(`대화 조회 실패: ${response.status}`);
        }

        const data: { messages: SavedMessage[] } =
          await response.json();

        if (!controller.signal.aborted) {
          setSavedMessages(data.messages);
          setHistoryError(null);
        }
      } catch (err) {
        if (controller.signal.aborted) return;

        const message =
          err instanceof Error ? err.message : "대화 조회 오류";

        setHistoryError(message);
        console.error("[DUGOUT] 대화 복원 실패:", err);
      }
    }

    void loadMessages();

    return () => controller.abort();
  }, [conversationId, historyVersion]);

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();

    if (!message.trim() || loading) return;

    void sendMessage(message.trim());
  }

  function handleNewConversation() {
    if (loading) return;

    startNewConversation();
    setSavedMessages([]);
    setHistoryError(null);
    setMessage("");
  }

  return (
    <main className="app">
      <header>
        <div className="eyebrow">
          BASEBALL DECISION INTELLIGENCE
        </div>
        <h1>DUGOUT AI</h1>
        <p>
          경기 데이터를 확인하고, 근거 있는 야구 전략을 분석합니다.
        </p>
      </header>

      <section className="panel">
        <form onSubmit={handleSubmit}>
          <label htmlFor="question">
            감독에게 묻고 싶은 질문
          </label>

          <textarea
            id="question"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={4}
            maxLength={1000}
            placeholder="경기 상황이나 투수 교체 전략을 질문해 보세요."
          />

          <div className="actions">
            <button type="submit" disabled={loading || !message.trim()}>
              {loading ? "분석 중..." : "분석 시작"}
            </button>

            {loading && (
              <button
                type="button"
                className="secondary"
                onClick={cancel}
              >
                중단
              </button>
            )}
          </div>
        </form>

        <div className="conversation-controls">
          <button
            type="button"
            className="secondary"
            onClick={handleNewConversation}
            disabled={loading}
          >
            새 대화
          </button>

          {conversationId && (
            <small>
              대화 ID: {conversationId.slice(0, 8)}...
            </small>
          )}
        </div>
      </section>

      <section className="panel">
        <div className="section-title">
          <h2>Agent 실행 과정</h2>
          <span className="status">{status}</span>
        </div>

        {tools.length === 0 ? (
          <p className="muted">
            {loading
              ? "Agent가 필요한 정보를 확인하고 있습니다."
              : "아직 실행한 Tool이 없습니다."}
          </p>
        ) : (
          <div className="tool-list">
            {tools.map((tool, index) => (
              <div className="tool" key={index}>
                <strong>{tool.tool}</strong>
                <span>
                  {tool.ok === undefined
                    ? "실행 중"
                    : tool.ok
                      ? "성공"
                      : `실패: ${tool.error?.code ?? "UNKNOWN"}`}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <h2>이전 대화</h2>

        {historyError && (
          <p className="error">{historyError}</p>
        )}

        {savedMessages.length === 0 ? (
          <p className="muted">저장된 대화가 없습니다.</p>
        ) : (
          <div className="saved-messages">
            {savedMessages.map((item) => (
              <div
                key={item.id}
                className={`saved-message ${item.role}`}
              >
                <strong>
                  {item.role === "user" ? "사용자" : "DUGOUT AI"}
                </strong>
                <p>{item.content}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <h2>AI 분석 결과</h2>

        <div className="answer" aria-live="polite">
          {status === "completed"
            ? "분석이 완료되었습니다. 이전 대화에서 결과를 확인할 수 있습니다."
            : answer || "아직 분석 결과가 없습니다."}
        </div>

        {error && <p className="error">{error}</p>}
      </section>
    </main>
  );
}

export default App;