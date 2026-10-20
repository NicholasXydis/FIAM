import * as THREE from "three";
import type { Stage } from "./gl/stage";
import type { Scene } from "./scenes/scene";
import type { Label } from "./ui";

// How the tour lays out: the desktop corners, or a small layout.
export type Mode = "desktop" | "corners" | "stack" | "side";

// A rectangle on screen in CSS pixels, flagged if it is the header's.
export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
  head?: boolean;
}

// A finger rather than a mouse, read once and kept in step.
const touch = matchMedia("(pointer: coarse)");
let current: Mode = "desktop";
// Frames since load, so slow work can run every few frames only.
let frames = 0;
// Set when a fold opens or the window changes, so the band refits.
let dirty = true;

// Side for landscape phones, stack for portrait, corners or desktop.
function pick(): Mode {
  const w = innerWidth;
  const h = innerHeight;
  if (w > h && h <= 500) return "side";
  if ((h >= w && w <= 1100) || w <= 760) return "stack";
  if (w < 1280 || (touch.matches && w <= 1366)) return "corners";
  return "desktop";
}

// Whether a small layout is on; the desktop keeps its first code paths.
export const small = () => current !== "desktop";
// Whether the layout is a phone's: stacked, or the landscape column.
export const phone = () => current === "stack" || current === "side";
// Whether the layout is the portrait stack, phones and tablets alike.
export const portrait = () => current === "stack";
// Whether the pointer is a finger.
export const coarse = () => touch.matches;
// Marks the band to be measured again on the next frame.
export const stale = () => void (dirty = true);
// True on every nth frame, for work that need not run each one.
export const every = (n: number) => frames % n === 0;
// Counts a frame, once at the top of each.
export const tick = () => void frames++;

// Sets the mode from the window and writes it for the CSS to follow.
export function setMode() {
  const next = pick();
  const changed = next !== current;
  current = next;
  const root = document.documentElement;
  root.dataset["tour"] = next;
  root.toggleAttribute("data-small", next !== "desktop");
  root.toggleAttribute("data-phone", next === "stack" || next === "side");
  dirty = true;
  return changed;
}

// An element's box on screen, or null while it is hidden or empty.
function rect(el: Element | null): Box | null {
  if (!el || el.closest("[hidden]")) return null;
  const s = getComputedStyle(el);
  if (s.display === "none" || s.visibility === "hidden") return null;
  const b = el.getBoundingClientRect();
  return b.width && b.height ? { x: b.left, y: b.top, w: b.width, h: b.height } : null;
}

// What the scene must not sit under: header, story, controls, dock.
export function boxes(scene: Scene): Box[] {
  const card = [...document.querySelectorAll(".card")].map(rect).find(Boolean) ?? null;
  const head = [rect(document.querySelector(".topbar")), rect(document.querySelector(".tour-back"))];
  const all = [
    ...head.map((b) => b && { ...b, head: true }),
    rect(scene.panel),
    card ? null : rect(scene.controls),
    card,
    rect(document.querySelector(".dock")),
  ];
  return all.filter((b): b is Box => b !== null);
}

// Whether two boxes overlap.
const hit = (a: Box, b: Box) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

// The free band between the top and bottom boxes, or right of a column.
function band(list: Box[]): Box {
  const W = innerWidth;
  const H = innerHeight;
  const head = Math.max(0, ...list.filter((b) => b.head).map((b) => b.y + b.h));
  const top = list.filter((b) => b.y + b.h / 2 < H / 2);
  const low = list.filter((b) => b.y + b.h / 2 >= H / 2);
  const y0 = Math.max(0, ...top.map((b) => b.y + b.h)) + 10;
  const y1 = Math.min(H, ...low.map((b) => b.y)) - 10;
  const gap = { x: 10, y: y0, w: W - 20, h: Math.max(0, y1 - y0) };
  // The side band, right of the boxes that sit in the left half.
  const left = list.filter((b) => b.y >= head - 1 && b.x + b.w / 2 < W / 2 && b.w < W * 0.6);
  const right = list.filter((b) => b.y >= head - 1 && b.x + b.w / 2 >= W / 2 && b.w < W * 0.6);
  const x0 = Math.max(0, ...left.map((b) => b.x + b.w)) + 10;
  const sy1 = Math.min(H, ...right.map((b) => b.y)) - 10;
  const side = { x: x0, y: head + 6, w: W - 10 - x0, h: sy1 - head - 6 };
  const clear = side.w > 0 && side.h > 0 && !list.some((b) => hit(side, b));
  return left.length && clear && side.w * side.h > gap.w * gap.h ? side : gap;
}

// Scratch vectors for projecting, so fitting allocates little.
const v = new THREE.Vector3();
const shot = new THREE.Vector3();

// The biggest zoom to the cap that fits frame and labels, and offset.
function fit(stage: Stage, scene: Scene, room: Box) {
  const rest = stage.restCamera();
  const cx = innerWidth / 2;
  const cy = innerHeight / 2;
  // A world point's place on screen through the resting camera.
  const onScreen = (p: THREE.Vector3): [number, number] => {
    v.copy(p).project(rest);
    return [(v.x * 0.5 + 0.5) * innerWidth, (-v.y * 0.5 + 0.5) * innerHeight];
  };
  const points = scene.frame.map(onScreen);
  const labels = scene.labels
    .filter((l) => l.fits && l.shown)
    .map((l) => {
      const [x, y] = onScreen(l.where);
      const a = l.anchor === "center" ? 0.5 : l.anchor === "right" ? 1 : 0;
      return { x, y, a, w: l.width, h: l.height };
    });
  // The screen box of everything at a zoom about the centre.
  const extent = (z: number) => {
    let x0 = Infinity;
    let x1 = -Infinity;
    let y0 = Infinity;
    let y1 = -Infinity;
    for (const [x, y] of points) {
      x0 = Math.min(x0, cx + z * (x - cx));
      x1 = Math.max(x1, cx + z * (x - cx));
      y0 = Math.min(y0, cy + z * (y - cy));
      y1 = Math.max(y1, cy + z * (y - cy));
    }
    for (const l of labels) {
      const X = cx + z * (l.x - cx);
      const Y = cy + z * (l.y - cy);
      x0 = Math.min(x0, X - l.a * l.w);
      x1 = Math.max(x1, X + (1 - l.a) * l.w);
      y0 = Math.min(y0, Y - l.h / 2);
      y1 = Math.max(y1, Y + l.h / 2);
    }
    return { x0, x1, y0, y1 };
  };
  // A shot other than the scene's own, such as a year, is only centred.
  const own = stage.eye.target.distanceTo(shot.set(...scene.shot.eye)) < 0.01;
  if (!own) return { zoom: 1, ox: 0, oy: cy - (room.y + room.h / 2) };
  let lo = 0.3;
  let hi = scene.zoomCap;
  for (let k = 0; k < 22 && points.length + labels.length; k++) {
    const z = (lo + hi) / 2;
    const e = extent(z);
    if (e.x1 - e.x0 <= room.w - 32 && e.y1 - e.y0 <= room.h - 16) lo = z;
    else hi = z;
  }
  if (!points.length && !labels.length) return { zoom: 1, ox: 0, oy: 0 };
  const e = extent(lo);
  return { zoom: lo, ox: (e.x0 + e.x1) / 2 - (room.x + room.w / 2), oy: (e.y0 + e.y1) / 2 - (room.y + room.h / 2) };
}

// Fits the camera to the band on small screens, never on the desktop.
export function frame(stage: Stage, scene: Scene, moved: boolean) {
  if (!small()) {
    stage.view = null;
    return;
  }
  if (!moved && !dirty && !every(10)) return;
  dirty = false;
  squeeze(scene);
  stage.view = fit(stage, scene, band(boxes(scene)));
}

// In the side layout, a body that would meet the controls gets 1 line.
function squeeze(scene: Scene) {
  const body = scene.panel.querySelector<HTMLElement>(".body");
  if (!body) return;
  const side = current === "side";
  if (!side) body.classList.remove("tight");
  scene.panel.style.maxHeight = "";
  if (!side) return;
  // Still too tall, the panel scrolls above the controls instead.
  const top = scene.panel.getBoundingClientRect().top;
  const room = scene.controls.getBoundingClientRect().top - 8 - top;
  const line = parseFloat(getComputedStyle(body).lineHeight) || 18;
  const spare = room - scene.panel.scrollHeight;
  if (spare < 0) body.classList.add("tight");
  else if (spare > line) body.classList.remove("tight");
  scene.panel.style.maxHeight = `${Math.max(0, room)}px`;
}

// Moves labels clear of boxes and each other; only priority 0 may hide.
export function declutter(labels: Label[], blocks: Box[]) {
  const order = labels.filter((l) => l.shown && l.box).sort((p, q) => q.prio - p.prio);
  const placed: Box[] = [];
  for (const l of order) {
    const r0 = l.box!;
    const step = r0.h + 4;
    // Important labels look further afield before giving up.
    const far = l.prio > 0 ? [2 * step, -3 * step, 3 * step] : [];
    const tries = l.moves ? [l.dy, 0, -step, step, -2 * step, ...far].filter((d, i, all) => all.indexOf(d) === i) : [0];
    let found: number | null = null;
    for (const dy of tries) {
      const r = { x: r0.x, y: r0.y + dy, w: r0.w, h: r0.h };
      if (r.y < 0 || r.y + r.h > innerHeight) continue;
      if (blocks.some((b) => hit(r, b)) || placed.some((p) => hit(r, p))) continue;
      found = dy;
      placed.push(r);
      break;
    }
    l.dy = found ?? l.dy;
    // With no room, an important label stays unless a box covers it.
    const kept = { ...r0, y: r0.y + l.dy };
    l.blocked = found === null && (l.prio === 0 || !l.moves || blocks.some((b) => hit(kept, b)));
    if (found === null && !l.blocked) placed.push(kept);
  }
}

// Shrinks each slide's title on small screens until it fits one line.
export function titles(list: Scene[]) {
  for (const scene of list) {
    const head = scene.panel.querySelector<HTMLElement>(".headline");
    if (!head) continue;
    head.style.fontSize = "";
    if (!small()) continue;
    const width = scene.panel.clientWidth;
    const base = parseFloat(getComputedStyle(head).fontSize);
    if (!width || head.scrollWidth <= width) continue;
    head.style.fontSize = `${Math.max(18, Math.floor((base * width) / head.scrollWidth))}px`;
  }
}

// A scene's world box as its eight corners, for the fit.
export function corners(x0: number, y0: number, z0: number, x1: number, y1: number, z1: number) {
  const out: THREE.Vector3[] = [];
  for (const x of [x0, x1]) for (const y of [y0, y1]) for (const z of [z0, z1]) out.push(new THREE.Vector3(x, y, z));
  return out;
}

// Points round a ring of radius r at height y, for round scenes.
export function round(r: number, y: number, n = 24) {
  return Array.from(
    { length: n },
    (_, i) => new THREE.Vector3(Math.cos((i / n) * 6.283) * r, y, Math.sin((i / n) * 6.283) * r),
  );
}
