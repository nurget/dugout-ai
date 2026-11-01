import type { BullpenComparisonResult } from "../api/client";
import "./BullpenComparisonCard.css";

type Props = { result: BullpenComparisonResult };

function workloadMessage(status: string) {
  if (status === "REVIEW_REQUIRED") return "최근 투구 부담 추가 검토 필요";
  if (status === "NO_HIGH_LOAD_FLAG") return "최근 기록상 높은 부담 신호 없음";
  return "투구 부담 확인 불가";
}

export function BullpenComparisonCard({ result }: Props) {
  return <section className="bullpen-comparison">
    <header className="bullpen-comparison__header"><div><h3>불펜 후보 비교</h3><p>{result.team_code} · {result.as_of_date}</p></div><span className="bullpen-comparison__tag">조건부 비교</span></header>
    <div className="bullpen-comparison__grid">{result.candidates.map((pitcher) => <article className="bullpen-comparison__player" key={pitcher.pitcher_id}>
      <h4>{pitcher.pitcher_name}</h4><p className="bullpen-comparison__id">ID {pitcher.pitcher_id}</p>
      <div className="bullpen-comparison__metric"><span>시즌 K-BB%</span><strong>{pitcher.k_minus_bb_pct.toFixed(2)}%</strong></div>
      <div className="bullpen-comparison__metric"><span>상대 타자 수</span><strong>{pitcher.batters_faced}명</strong></div>
      <div className="bullpen-comparison__metric"><span>최근 3일 투구 수</span><strong>{pitcher.pitches_last_3_days === null ? "확인 불가" : `${pitcher.pitches_last_3_days}구`}</strong></div>
      <div className="bullpen-comparison__metric"><span>연속 등판</span><strong>{pitcher.consecutive_days === null ? "확인 불가" : `${pitcher.consecutive_days}일`}</strong></div>
      <p className="bullpen-comparison__status">{workloadMessage(pitcher.workload_status)}</p>
    </article>)}</div>
    {result.withheld.length > 0 && <div className="bullpen-comparison__withheld"><strong>비교 보류</strong>{result.withheld.map((player) => <p key={player.pitcher_id}>{player.pitcher_name ?? player.pitcher_id}: {player.reason}</p>)}</div>}
    <footer className="bullpen-comparison__notice">시즌 전체 성적과 기준일 직전 3일 기록을 결합한 조건부 비교입니다. 선수 ID는 잠정 매핑일 수 있으며 당일 엔트리, 컨디션 및 등판 가능 여부는 확인되지 않았습니다.</footer>
  </section>;
}
