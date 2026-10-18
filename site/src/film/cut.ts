import * as THREE from "three";
import crashes from "../data/crashes.json";
import { agents, crowd, headline, journey, months } from "../data/fiam.json";
import { monthName } from "../shared/data";
import { TEAM } from "../content/credits";
import words from "../../ad/voice/words.json";
import { Gimbal } from "./gimbal";
import type { Key } from "./rig";
import type { Title } from "./titles";
import type { Shock } from "./water";

// The film runs 62 s and fades to black from 61.1 s.
export const LENGTH = 62;
export const FADE = 61.1;

// Figures the film reads from the data, stocks rounded down to 100s.
export const ROLES = agents.map((a) => a.name);
export const SHARPE = headline.sharpe;
const BETA = headline.beta;
const INVESTORS = crowd.agents + crowd.copycats;
const STOCKS = Math.floor(journey.stocks / 100) * 100;

// Part starts, on 2 s bars at 120 BPM from the music, except dusk.
export const AT = {
  panic: 9.3,
  cut: 10.4,
  studio: 12.2,
  music: 13.6,
  shelf: 17.6,
  dusk: 23.0,
  agents: 23.6,
  crowd: 33.6,
  sea: 41.6,
  stats: 45.6,
  outro: 49.6,
};

// When each line plays, from and to splitting one file over two shots.
export const VOICE = [
  { key: "rise", at: 1.2 },
  { key: "panic", at: 7.6 },
  { key: "dont", at: 11.0 },
  { key: "neutral", at: 14.0, to: 2.1 },
  { key: "neutral", at: 18.2, from: 2.1 },
  { key: "agents", at: 24.4 },
  { key: "crowd", at: 34.4 },
  { key: "crises", at: 41.9 },
  { key: "close", at: 50.0 },
  { key: "brand", at: 55.4 },
];

// The voice's lines by name.
type Line = keyof typeof words;

// The film time a word is said, by index or first match in any case.
export function said(key: Line, which: number | string) {
  const list = words[key] as [string, number, number][];
  const i = typeof which === "number" ? which : list.findIndex(([w]) => w.toLowerCase() === which.toLowerCase());
  const start = list[i][1];
  // The voice cue whose part of the file holds the word.
  const v = VOICE.find((p) => p.key === key && start >= (p.from ?? -Infinity) && start < (p.to ?? Infinity))!;
  return v.at + start - (v.from ?? 0);
}

// Every shock since 2000 on the water, its ripple as big as the move.
export const SHOCKS: (Shock & { year: string })[] = crashes.map((c, i) => {
  // Spread by the golden angle, then hit one every 0.22 s from 41.8 s.
  const a = i * 2.39996 + 0.5;
  const r = 4 + 8 * ((i * 0.618 + 0.3) % 1);
  return {
    x: Math.sin(a) * r,
    z: Math.cos(a) * r * 0.7 - 2,
    at: 41.8 + i * 0.22,
    amp: 0.06 + Math.abs(c.market) * 0.55,
    up: c.market > 0,
    year: c.first.slice(0, 4),
  };
});

// When a word of the panic line is said.
const P = (n: number | string) => said("panic", n);
// Every title, timed to the words it shows.
export const TITLES: Title[] = [
  { at: P("panic"), out: AT.cut, cut: true, text: "Markets *panic.*", tone: "storm", place: "line" },
  { at: said("dont", 0), out: 12.9, text: "We *don't.*", tone: "light", place: "line" },
  {
    at: said("neutral", "market"),
    out: 17.3,
    text: "Market *neutral.*",
    words: [said("neutral", "market"), said("neutral", "neutral")],
    eyebrow: [said("neutral", "Quark"), "QUARCC Purple"],
    sub: [said("neutral", "neutral") + 0.5, `Beta ${BETA.toFixed(2)} to the market`],
    tone: "dark",
    place: "low",
  },
  {
    at: said("neutral", "Long"),
    out: 23.3,
    text: "Long the *strongest.* | Short the *weakest.*",
    // A 0 holds the place of each line break.
    words: ["Long", "the", "strongest", 0, "short", 10, "weakest"].map((w) =>
      w === 0 ? 0 : said("neutral", w as string | number),
    ),
    eyebrow: [17.9, `12 signals · ${STOCKS.toLocaleString("en-US")} US stocks · every month`],
    tone: "dark",
    place: "low",
  },
  {
    at: said("agents", "read"),
    out: 33.3,
    text: "They *read.* | They *challenge.* | They *verify.*",
    words: [
      said("agents", "They"),
      said("agents", "read"),
      0,
      said("agents", "challenge") - 0.15,
      said("agents", "challenge"),
      0,
      said("agents", "check") - 0.15,
      said("agents", "check"),
    ],
    eyebrow: [said("agents", "Seven"), "Seven AI agents"],
    sub: [said("agents", "machines"), "Gemma 4 and Qwen3.8, running on our own machines"],
    tone: "light",
    place: "low",
  },
  {
    at: said("crowd", "Thirty"),
    out: 41.2,
    text: "30 of them think like *4.*",
    words: ["Thirty", "of", "them", "think", "like", "four"].map((w) => said("crowd", w)),
    eyebrow: [said("crowd", "sixty"), `${INVESTORS} AI investors`],
    tone: "light",
    place: "low",
  },
  {
    at: said("crises", "barely"),
    out: 45.3,
    text: "Barely *moved.*",
    words: [said("crises", "barely"), said("crises", "moved")],
    eyebrow: [said("crises", "seventeen"), `${crashes.length} replayed crises since 2000`],
    tone: "light",
    place: "low",
  },
  {
    at: 47.0,
    out: 49.4,
    text: `Sharpe *${SHARPE.toFixed(2)}.*`,
    words: [47.0, 47.25],
    eyebrow: [46.3, `After costs, ${months[0].slice(0, 4)} to ${months[months.length - 1].slice(0, 4)}`],
    sub: [47.8, `Beta ${BETA.toFixed(2)} · backtested`],
    tone: "light",
    place: "low",
  },
  {
    at: said("close", "We"),
    out: 55.3,
    text: "We stay *level.*",
    words: [said("close", "We"), said("close", "stays"), said("close", "level")],
    eyebrow: [said("close", 0), "AI will move markets"],
    tone: "light",
    place: "low",
  },
];

// The end card, its tag on the spoken Calm and its name on Quark.
export const END = {
  at: said("brand", "Calm"),
  name: said("brand", "Quark"),
  title: "QUARCC Purple <em>·</em> FIAM",
  tag: "Calm, *by design.*",
  event: "McGill-FIAM Asset Management Hackathon 2026 · Finals",
  team: TEAM.map((name) => name.replaceAll(" ", " ")).join(" · "),
  note: `Backtested results, ${monthName(months[0])} to ${monthName(months[months.length - 1])}. Crisis replays are hypothetical. Not a live record. Not an offer to invest.`,
};

// The agents' cues, from the words that name them.
export const AGENTS = {
  enter: AT.agents + 0.3,
  read: said("agents", "read"),
  argue: said("agents", "challenge"),
  ring: said("agents", "check") - 0.35,
  verify: said("agents", "check"),
  rest: AT.crowd - 0.2,
};

// The sounds the score lines up with the picture.
export const SOUNDS = [
  { at: 0, kind: "open" },
  { at: said("rise", "alike"), kind: "herd" },
  { at: P("panic"), kind: "panic" },
  { at: AT.cut, kind: "cut" },
  { at: AT.cut + 0.3, kind: "note" },
  { at: AT.studio, kind: "swell" },
  { at: AT.music, kind: "music" },
  { at: 14.6, kind: "knock" },
  { at: 15.8, kind: "knock", strength: 0.8 },
  { at: AT.shelf, kind: "whoosh", strength: 0.6 },
  { at: said("neutral", "strongest"), kind: "rise" },
  { at: said("neutral", "weakest"), kind: "fall" },
  { at: 21.8, kind: "glass" },
  ...ROLES.map((_, i) => ({ at: AT.agents + 0.7 + i * 0.2, kind: "ping", strength: 0.45 + 0.05 * i })),
  { at: AGENTS.read, kind: "papers" },
  { at: AGENTS.argue, kind: "argue" },
  { at: AGENTS.verify, kind: "chime" },
  { at: AT.crowd, kind: "crane" },
  { at: said("crowd", "Thirty"), kind: "herd" },
  { at: AT.sea, kind: "whoosh", strength: 0.8 },
  ...SHOCKS.map((s) => ({ at: s.at, kind: "shock", strength: Math.min(1, s.amp * 3) })),
  { at: 46.2, kind: "count" },
  { at: 47.6, kind: "land" },
  { at: AT.outro, kind: "resolve" },
  { at: END.name, kind: "sting" },
];

// The dial's height, the centre of the studio shots.
const C = Gimbal.centre;

// Each part is one glide. The opening backs away from the first light.
export const opening = (s: THREE.Vector3): Key[] => [
  [0.0, { at: [s.x, s.y, s.z], r: 0.12, yaw: 20, pitch: 26, fov: 30 }],
  [2.6, { at: [s.x, s.y, s.z], r: 1.8, yaw: 28, pitch: 32, fov: 30, blur: 0.004 }],
  [5.4, { at: [s.x * 0.8, -3, s.z * 0.8], r: 24, yaw: 36, pitch: 36, fov: 32 }],
  [10.4, { at: [s.x * 0.35, -10, s.z * 0.35], r: 125, yaw: 50, pitch: 31, fov: 34 }],
];

// The studio, a dolly zoom on the dial, then up to look down on it.
export const STUDIO: Key[] = [
  [12.2, { at: [0, C, 0], r: 3.05, yaw: 0, pitch: 0, fov: 46 }],
  [13.7, { at: [0, C, 0], r: 3.05, yaw: 0, pitch: 0, fov: 26 }],
  [15.0, { at: [0, 2.9, 0], r: 3.8, yaw: -14, pitch: 10, fov: 26, focus: 0.9, blur: 0.005 }],
  [16.4, { at: [0, 2.4, 0], r: 4.6, yaw: -32, pitch: 21, fov: 28, blur: 0.005 }],
  [17.6, { at: [0, C, 0], r: 2.1, yaw: -50, pitch: 56, fov: 28, blur: 0.003 }],
];

// The shelf, dipping under the glass, circling, then out to the world.
export const SHELF: Key[] = [
  [17.6, { at: [0, 2.8, 0], r: 4.6, yaw: -10, pitch: 72, fov: 32 }],
  [19.6, { at: [0, 2.9, 0], r: 4.4, yaw: 4, pitch: 40, fov: 34, blur: 0.0045 }],
  [21.0, { at: [0, 2.8, 0], r: 3.8, yaw: 18, pitch: 14, fov: 44, blur: 0.0045 }],
  [21.8, { at: [0, 2.8, 0], r: 3.6, yaw: 24, pitch: 0, fov: 50, blur: 0.0045 }],
  [22.6, { at: [0, 2.6, 0], r: 3.8, yaw: 30, pitch: -14, fov: 46, blur: 0.0045 }],
  [24.2, { at: [0, 2.8, 0], r: 5.2, yaw: 42, pitch: 3, fov: 32, blur: 0.0035 }],
  [25.6, { at: [0, 2.9, 0], r: 5.4, yaw: 54, pitch: 6, fov: 34 }],
  [28.8, { at: [0, 3.1, 0], r: 4.2, yaw: 80, pitch: 4, fov: 38, blur: 0.006 }],
  [30.8, { at: [0, 3.2, 0], r: 5.0, yaw: 104, pitch: 18, fov: 34, blur: 0.0045 }],
  [32.6, { at: [0, 3.3, 0], r: 6.2, yaw: 120, pitch: 34, fov: 32, blur: 0.003 }],
  [35.6, { at: [0, 3.0, 0], r: 14, yaw: 136, pitch: 42, fov: 32 }],
  [38.6, { at: [0, 0, 0], r: 60, yaw: 146, pitch: 30, fov: 34 }],
  [41.6, { at: [0, -10, 0], r: 130, yaw: 152, pitch: 22, fov: 36 }],
];

// The sea, skimming the water, then over the dial, then far away.
export const SEA: Key[] = [
  [41.6, { at: [0, 0.7, 0], r: 6.4, yaw: -14, pitch: 3, fov: 36, blur: 0.0045 }],
  [44.0, { at: [0, 0.75, 0], r: 4.8, yaw: 2, pitch: 5, fov: 34, blur: 0.005 }],
  [45.6, { at: [0, 0.7, 0], r: 3.4, yaw: 6, pitch: 30, fov: 32, blur: 0.0045 }],
  [47.0, { at: [0, 0.62, 0], r: 2.9, yaw: 4, pitch: 64, fov: 32, blur: 0.0035 }],
  [49.6, { at: [0, 0.62, 0], r: 2.7, yaw: 0, pitch: 86, fov: 32, blur: 0.003 }],
  [52.6, { at: [0, 1, 0], r: 8, yaw: 10, pitch: 54, fov: 32 }],
  [62.0, { at: [0, -10, 0], r: 140, yaw: 30, pitch: 28, fov: 36 }],
];

// A year mark just above the water where each shock starts.
export const MARKS = SHOCKS.map((s) => ({
  text: s.year,
  at: new THREE.Vector3(s.x, 0.25, s.z),
  t: s.at,
  up: s.up,
}));
