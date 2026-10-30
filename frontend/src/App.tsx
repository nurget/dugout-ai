import { useState } from "react";
import { useAgentStream } from "./hooks/useAgentStream";
import "./App.css";

const EXAMPLE_QUESTION =
  "경기 ID 1의 상태 ID 1과 선수 ID 1을 조회하고 KIA의 다른 투수 후보를 알려줘.";

function App() {
  const [message, setMessage] = useState(EXAMPLE_QUESTION);

  const {
    answer,
    tools,
    status,
    error,
    sendMessage,
    cancel,
  } = useAgentStream();

  const loading = [
    "connecting",
    "analyzing",
    "generating",
  ].includes(status);

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();

    if (!message.trim() || loading) return;
    void sendMessage(message.trim());
  }

  return (
    <main className="app">
      <header>
        <div className="eyebrow">BASEBALL DECISION INTELLIGENCE</div>
        <h1>DUGOUT AI</h1>
        <p>경기 데이터를 확인하고, 근거 있는 야구 전략을 분석합니다.</p>
      </header>

      <section className="panel">
        <form onSubmit={handleSubmit}>
          <label htmlFor="question">감독에게 묻고 싶은 질문</label>
          <textarea
            id="question"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={4}
            maxLength={1000}
          />

          <div className="actions">
            <button type="submit" disabled={loading}>
              {loading ? "분석 중..." : "분석 시작"}
            </button>

            {loading && (
              <button type="button" className="secondary" onClick={cancel}>
                중단
              </button>
            )}
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="section-title">
          <h2>Agent 실행 과정</h2>
          <span className="status">{status}</span>
        </div>

        {tools.length === 0 ? (
          <p className="muted">실행한 Tool이 여기에 표시됩니다.</p>
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
        <h2>AI 분석 결과</h2>
        <div className="answer" aria-live="polite">
          {answer || "아직 분석 결과가 없습니다."}
        </div>

        {error && <p className="error">{error}</p>}
      </section>
    </main>
  );
}

export default App;