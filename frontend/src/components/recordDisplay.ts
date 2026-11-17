export const recordTeams = [
  ["", "전체 구단"], ["KIA", "KIA 타이거즈"], ["SS", "삼성 라이온즈"],
  ["LG", "LG 트윈스"], ["KT", "KT 위즈"], ["SSG", "SSG 랜더스"],
  ["NC", "NC 다이노스"], ["OB", "두산 베어스"], ["LT", "롯데 자이언츠"],
  ["HH", "한화 이글스"], ["WO", "키움 히어로즈"],
] as const;

const teamNames: Record<string, string> = { KIA: "KIA", HT: "KIA", SS: "삼성", LG: "LG", KT: "KT", SSG: "SSG", SK: "SSG", NC: "NC", OB: "두산", LT: "롯데", HH: "한화", WO: "키움" };
export const presentTeam = (code: string) => teamNames[code] ?? code;
export const recordTeamCode = (code: string) => ({ KIA: "HT", SSG: "SK" } as Record<string, string>)[code] ?? code;
export const statLabels: Record<string, string> = {
  "선수명": "선수", "팀명": "구단", AVG: "타율", G: "경기", PA: "타석", AB: "타수", H: "안타", "2B": "2루타", "3B": "3루타", HR: "홈런", RBI: "타점", BB: "볼넷", SO: "삼진", OBP: "출루율", SLG: "장타율", OPS: "OPS", ERA: "평균자책점", W: "승", L: "패", SV: "세이브", HLD: "홀드", IP: "이닝", WHIP: "이닝당 출루 허용", WPCT: "승률", ER: "자책점", TB: "루타", SAC: "희생번트", SF: "희생플라이", HBP: "몸에 맞는 공", HP: "몸에 맞는 공", GDP: "병살타", CS: "도루 실패", SB: "도루", IBB: "고의4구", NP: "투구 수", TBF: "상대 타자", BF: "상대 타자", QS: "퀄리티스타트", CG: "완투", SHO: "완봉", WP: "폭투", BK: "보크", E: "실책", FPCT: "수비율", PO: "자살", A: "보살", DP: "병살", RTO: "도루 저지", SBA: "도루 시도", "순위": "순위", "승": "승", "패": "패", "무": "무", "경기": "경기", "승률": "승률", "게임차": "게임 차", "연속": "최근 연속 결과", "최근10경기": "최근 10경기", "최근 10경기": "최근 10경기",
};
export const statName = (key: string, category: string) => {
  if (key === "R") return category === "batter" || category === "batting" ? "득점" : "실점";
  if (category === "defense" && key === "SB") return "허용 도루";
  if (category === "defense" && key === "CS") return "도루 저지";
  if (key === "PKO") return category === "running" ? "견제사" : "견제 아웃";
  return ({ "CS%": "도루 저지율", "SB%": "도루 성공률", OOB: "주루사", PB: "포일" } as Record<string, string>)[key] ?? statLabels[key] ?? key;
};
export const displayDate = (date: string | null | undefined) => date ? new Date(date).toLocaleString("ko-KR", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" }) : null;
export function formatWinLossDraw(value: string) {
  const counts = new Map(Array.from(value.matchAll(/(\d+)\s*(승|패|무)/g), (match) => [match[2], match[1]]));
  return counts.size === 3 ? ["승", "패", "무"].map((unit) => `${counts.get(unit)}${unit}`).join(" ") : value.replace(/(승|패|무)(?=\d)/g, "$1 ");
}
export function numericStat(value: string | undefined) {
  if (!value || value === "-" || value === "—") return null;
  const clean = value.replaceAll(",", "").replace(/%$/, "");
  const inning = clean.match(/^(\d+)\s+(\d)\/3$/);
  if (inning) return Number(inning[1]) + Number(inning[2]) / 3;
  const fraction = clean.match(/^(\d)\/3$/);
  if (fraction) return Number(fraction[1]) / 3;
  const parsed = Number(clean);
  return Number.isFinite(parsed) ? parsed : null;
}
