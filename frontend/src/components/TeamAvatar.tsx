import type { TeamCode } from "../api/client";
import { getTeamKey, getTeamPalette } from "../teamTheme";

const symbols: Record<TeamCode, string> = {
  KIA: "🐯", OB: "🐻", HH: "🦅", SS: "🦁", NC: "🦖",
  LT: "🐦", LG: "👯", KT: "🧙", SSG: "🛸", WO: "🦸",
};

export function TeamAvatar({ teamCode, large = false }: { teamCode: string; large?: boolean }) {
  const key = getTeamKey(teamCode);
  const palette = getTeamPalette(teamCode);
  return <span className={`team-avatar${large ? " team-avatar--large" : ""}`} style={{ backgroundColor: palette.background, color: palette.foreground }} aria-hidden="true">{key ? symbols[key] : "⚾"}</span>;
}
