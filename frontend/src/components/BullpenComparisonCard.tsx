import { useEffect, useState } from "react";
import { api, type BullpenComparisonResult, type RecommendationReview } from "../api/client";
import "./BullpenComparisonCard.css";

type Props = { result: BullpenComparisonResult; canReview: boolean };

function workloadMessage(status: string) {
  if (status === "REVIEW_REQUIRED") return "최근 투구 부담 추가 검토 필요";
  if (status === "NO_HIGH_LOAD_FLAG") return "최근 기록상 높은 부담 신호 없음";
  return "투구 부담 확인 불가";
}

export function BullpenComparisonCard({ result, canReview }: Props) {
  const [outcome, setOutcome] = useState<RecommendationReview["outcome"]>("ACCEPTABLE_SET");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [reviewedAt, setReviewedAt] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  useEffect(() => {
    if (!result.run_id || !canReview) return;
    let active = true;
    api.recommendationReview(result.run_id)
      .then(({ review }) => {
        if (!active || !review) return;
        setOutcome(review.outcome);
        setSelectedIds(review.acceptable_candidate_ids);
        setReviewedAt(review.reviewed_at);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [result.run_id, canReview]);

  const saveReview = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!result.run_id || saving) return;
    setSaving(true);
    setReviewError(null);
    try {
      const { review } = await api.saveRecommendationReview(result.run_id, {
        outcome,
        acceptable_candidate_ids: outcome === "ACCEPTABLE_SET" ? selectedIds : [],
      });
      setReviewedAt(review.reviewed_at);
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : "평가를 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  };

  const toggleCandidate = (pitcherId: string) => {
    setSelectedIds((current) => current.includes(pitcherId)
      ? current.filter((id) => id !== pitcherId)
      : [...current, pitcherId]);
  };

  return <section className="bullpen-comparison">
    <header className="bullpen-comparison__header"><div><h3>불펜 후보 비교</h3><p>{result.team_code} · {result.as_of_date}</p></div><span className="bullpen-comparison__tag">{result.comparison_status === "WITHHELD" ? "비교 보류" : "기준일 누적 비교"}</span></header>
    <div className="bullpen-comparison__grid">{result.candidates.map((pitcher) => <article className="bullpen-comparison__player" key={pitcher.pitcher_id}>
      <h4>{pitcher.pitcher_name}</h4><p className="bullpen-comparison__id">ID {pitcher.pitcher_id}</p>
      <div className="bullpen-comparison__metric"><span>기준일까지 K-BB%</span><strong>{pitcher.k_minus_bb_pct.toFixed(2)}%</strong></div>
      <div className="bullpen-comparison__metric"><span>상대 타자 수</span><strong>{pitcher.batters_faced}명</strong></div>
      {pitcher.identity_status === "TENTATIVE" && <p className="bullpen-comparison__status">선수 ID 잠정 연결</p>}
      <div className="bullpen-comparison__metric"><span>최근 3일 투구 수</span><strong>{pitcher.pitches_last_3_days === null ? "확인 불가" : `${pitcher.pitches_last_3_days}구`}</strong></div>
      <div className="bullpen-comparison__metric"><span>연속 등판</span><strong>{pitcher.consecutive_days === null ? "확인 불가" : `${pitcher.consecutive_days}일`}</strong></div>
      <p className="bullpen-comparison__status">{workloadMessage(pitcher.workload_status)}</p>
    </article>)}</div>
    {result.withheld.length > 0 && <div className="bullpen-comparison__withheld"><strong>비교 보류</strong>{result.withheld.map((player) => <p key={player.pitcher_id}>{player.pitcher_name ?? player.pitcher_id}: {player.reason}</p>)}</div>}
    <footer className="bullpen-comparison__notice">기준일 당일 경기는 제외하고 그 이전 등판 기록으로 누적 성적을 계산했습니다. 기록 범위: {result.data_through_date ?? "확인 불가"}. {result.coverage?.status === "PARTIAL" ? `종료 경기 ${result.coverage.missing_games}건의 투수 기록이 없어 비교를 제한했습니다. ` : ""}{result.provenance?.status === "UNTRACKED" ? "일부 원천 행의 적재 버전을 확인할 수 없습니다. " : ""}선수 ID가 잠정 연결된 후보는 비교를 제한할 수 있습니다. 이 비교는 당일 엔트리, 컨디션 및 등판 가능 여부를 확인하지 않습니다.</footer>
    {canReview && result.run_id && result.candidates.length > 0 && <form className="bullpen-review" onSubmit={saveReview}>
      <div><strong>이 후보 비교를 검토해 주세요</strong><p>선택한 후보가 적절했는지 기록합니다. 이 평가는 경기 결과의 예측 적중률과는 별개입니다.</p></div>
      <fieldset>
        <legend>검토 결과</legend>
        <label><input type="radio" name={`outcome-${result.run_id}`} checked={outcome === "ACCEPTABLE_SET"} onChange={() => setOutcome("ACCEPTABLE_SET")} /> 적절한 후보 선택</label>
        <label><input type="radio" name={`outcome-${result.run_id}`} checked={outcome === "NONE_ACCEPTABLE"} onChange={() => { setOutcome("NONE_ACCEPTABLE"); setSelectedIds([]); }} /> 적절한 후보 없음</label>
        <label><input type="radio" name={`outcome-${result.run_id}`} checked={outcome === "NEEDS_MORE_INFO"} onChange={() => { setOutcome("NEEDS_MORE_INFO"); setSelectedIds([]); }} /> 정보 부족</label>
      </fieldset>
      {outcome === "ACCEPTABLE_SET" && <fieldset>
        <legend>적절하다고 판단한 후보</legend>
        {result.candidates.map((candidate) => <label key={candidate.pitcher_id}>
          <input type="checkbox" checked={selectedIds.includes(candidate.pitcher_id)} onChange={() => toggleCandidate(candidate.pitcher_id)} />
          {candidate.pitcher_name}
        </label>)}
      </fieldset>}
      <div className="bullpen-review__actions">
        <button type="submit" disabled={saving || (outcome === "ACCEPTABLE_SET" && selectedIds.length === 0)}>{saving ? "저장 중…" : reviewedAt ? "평가 수정" : "평가 저장"}</button>
        {reviewedAt && <small>마지막 저장: {new Date(reviewedAt).toLocaleString("ko-KR")}</small>}
      </div>
      {reviewError && <p className="error" role="alert">{reviewError}</p>}
    </form>}
  </section>;
}
