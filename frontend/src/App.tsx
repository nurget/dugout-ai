import { useEffect, useState } from "react";
import { useAgentStream } from "./hooks/useAgentStream";
import "./App.css";

const EXAMPLE_QUESTION =
  "7회말 1사 1루, 선발 투수가 95구입니다. 지금 교체하는 편이 나을까요?";

type SavedMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

const STATUS_LABEL: Record<string, string> = {
  idle: "준비됨",
  connecting: "연결 중",
  analyzing: "데이터 확인 중",
  generating: "분석 중",
  completed: "완료",
  cancelled: "중단됨",
  failed: "실패",
};

function App() {
  const [message, setMessage] = useState(EXAMPLE_QUESTION);
  const [savedMessages, setSavedMessages] = useState<SavedMessage[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const {
    conversationId, answer, tools, status, error, historyVersion,
    sendMessage, cancel, startNewConversation,
  } = useAgentStream();

  useEffect(() => {
    if (!conversationId) return;
    const controller = new AbortController();

    async function loadMessages() {
      try {
        const response = await fetch(
          `/api/agent/conversations/${conversationId}/messages`,
          { signal: controller.signal }
        );
        if (response.status === 404) {
          setSavedMessages([]);
          setHistoryError(null);
          return;
        }

        if (!response.ok) throw new Error(`대화 조회 실패: ${response.status}`);
        const data: { messages: SavedMessage[] } = await response.json();
        setSavedMessages(data.messages);
        setHistoryError(null);
      } catch (loadError) {
        if (!controller.signal.aborted) {
          setHistoryError(loadError instanceof Error ? loadError.message : "대화 조회 오류");
          console.error("대화 복원 실패", loadError);
        }
      }
    }

    void loadMessages();
    return () => controller.abort();
  }, [conversationId, historyVersion]);

  const loading = ["connecting", "analyzing", "generating"].includes(status);
  const displayedMessages = conversationId ? savedMessages : [];

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!message.trim() || loading) return;

    const submittedMessage = message.trim();
    setMessage("");
    void sendMessage(submittedMessage);
  }

  function handleQuestionKeyDown(
    event: React.KeyboardEvent<HTMLTextAreaElement>
  ) {
    if (event.key !== "Enter" || event.shiftKey) return;

    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  function handleNewConversation() {
    if (loading) return;
    startNewConversation();
    setSavedMessages([]);
    setHistoryError(null);
    setMessage("");
  }

  return (
    <main className="dashboard">
      <header className="app-header">
        <div className="wordmark">DUGOUT</div>
        <div className="header-actions">
          <span className={`run-status ${loading ? "active" : ""}`}>
            <i />{STATUS_LABEL[status] ?? status}
          </span>
          <button type="button" className="text-button" onClick={handleNewConversation} disabled={loading}>
            새 분석
          </button>
        </div>
      </header>

      <section className="game-overview" aria-label="현재 경기 상황">
        <div className="game-title">
          <span className="section-kicker">GAME SITUATION</span>
          <strong>KIA <b>3</b><em>:</em><b>3</b> 삼성</strong>
        </div>
        <div className="overview-metric"><span>이닝</span><strong>7회말</strong></div>
        <div className="overview-metric"><span>아웃 / 주자</span><strong>1사 · 1루</strong></div>
        <div className="overview-metric"><span>현재 투수</span><strong>선발 · 95구</strong></div>
        <div className="overview-metric"><span>다음 타자</span><strong>좌타자</strong></div>
      </section>

      <section className="main-panel" aria-label="투수 교체 분석">
        <div className="panel-heading">
          <div><span className="section-kicker">ANALYSIS</span><h1>투수 교체 분석</h1></div>
          {conversationId && <span className="record-id">ID {conversationId.slice(0, 8)}</span>}
        </div>

        <div className="analysis-content" aria-live="polite">
          {displayedMessages.map((item) => (
            <article className={`message ${item.role}`} key={item.id}>
              <span>{item.role === "user" ? "질문" : "분석 결과"}</span>
              <p>{item.content}</p>
            </article>
          ))}
          {answer && <article className="message assistant current"><span>분석 결과</span><p>{answer}</p></article>}
          {!answer && displayedMessages.length === 0 && !loading && (
            <div className="empty-state"><p>경기 상황에 대해 질문을 입력하세요.</p></div>
          )}
          {loading && !answer && <div className="loading-line"><i /><span>경기 데이터를 확인하고 있습니다</span></div>}
        </div>

        {tools.length > 0 && (
          <div className="tool-trace">
            <span>확인한 데이터</span>
            {tools.map((tool, index) => (
              <span className="tool-item" key={`${tool.tool}-${index}`}>
                <i className={tool.ok === false ? "fail" : tool.ok ? "done" : ""} />
                {tool.tool.replaceAll("_", " ")}
              </span>
            ))}
          </div>
        )}

        {historyError && <p className="error">저장된 대화를 불러오지 못했습니다: {historyError}</p>}
        {error && <p className="error">{error}</p>}

        <form className="composer" onSubmit={handleSubmit}>
          <label htmlFor="question">분석할 상황</label>
          <textarea id="question" value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={handleQuestionKeyDown} rows={2} maxLength={1000} placeholder="질문을 입력하세요" />
          <div className="composer-actions">
            <span>분석 결과는 의사결정 참고용입니다.</span>
            {loading ? <button type="button" className="cancel" onClick={cancel}>중단</button> : <button type="submit" disabled={!message.trim()}>분석하기</button>}
          </div>
        </form>
      </section>
    </main>
  );
}

export default App;
