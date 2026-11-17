import type { CSSProperties } from "react";
import type { TeamCode } from "./api/client";

// UI accents follow each club's identity; light surfaces and readable text are derived here.
export const teamPrimaryColors: Record<TeamCode, string> = {
  KIA: "#EA0029", HH: "#FC4E00", LG: "#C30452", SS: "#074CA1",
  SSG: "#CE0E2D", KT: "#000000", NC: "#315288", OB: "#131230",
  LT: "#041E42", WO: "#820024",
};
const aliases: Record<string, TeamCode> = { HT: "KIA", SK: "SSG", SAM: "SS", DOO: "OB", LOT: "LT", HAN: "HH", KIW: "WO" };
const rgb = (hex: string) => [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16));
function mix(color: string, target: string, amount: number) {
  const to = rgb(target);
  return `#${rgb(color).map((value, index) => Math.round(value * (1 - amount) + to[index] * amount).toString(16).padStart(2, "0")).join("")}`;
}
function luminance(color: string) {
  return rgb(color).map((value) => value / 255).map((value) => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4).reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
}
function contrast(a: string, b: string) {
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (values[0] + .05) / (values[1] + .05);
}
export function getTeamKey(code: string): TeamCode | null {
  const key = (aliases[code.toUpperCase()] ?? code.toUpperCase()) as TeamCode;
  return key in teamPrimaryColors ? key : null;
}
export function getTeamPalette(code: string) {
  const primary = teamPrimaryColors[getTeamKey(code) as TeamCode] ?? "#3182F6";
  const weak = mix(primary, "#FFFFFF", .93);
  let ink = primary;
  for (let step = 0; step < 16 && contrast(ink, weak) < 4.5; step += 1) ink = mix(ink, "#000000", .08);
  return { primary, background: weak, foreground: ink };
}
export function getTeamTheme(code: string): CSSProperties {
  const { primary, background: weak, foreground: ink } = getTeamPalette(code);
  return {
    "--brand-primary": primary,
    "--brand-on-primary": contrast(primary, "#FFFFFF") >= 4.5 ? "#FFFFFF" : "#191F28",
    "--blue": ink,
    "--weak": weak,
    "--brand-soft": mix(primary, "#FFFFFF", .975),
    "--brand-line": mix(primary, "#FFFFFF", .65),
    "--brand-ring": `${primary}40`,
  } as CSSProperties;
}
