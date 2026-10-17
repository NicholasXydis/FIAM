import * as THREE from "three";
import { out, ramp, span } from "./ease";

export function h(tag: string, props: Record<string, string> = {}, ...children: (Node | string)[]) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "html") el.innerHTML = value;
    else el.setAttribute(key, value);
  }
  el.append(...children);
  return el;
}

// One line of words on screen. Words in *stars* are set in italic gold. Each word arrives at its own
// time (spread evenly unless given) and the line leaves together, softly or on a hard cut.
export interface Title {
  at: number;
  out: number;
  text: string;
  words?: number[];
  eyebrow?: [number, string];
  sub?: [number, string];
  tone: "light" | "dark" | "storm";
  place: "line" | "low";
  cut?: boolean;
}

interface Built {
  title: Title;
  el: HTMLElement;
  words: HTMLElement[];
  eyebrow?: HTMLElement;
  sub?: HTMLElement;
}

export function words(text: string) {
  let gold = false;
  return text.split(" ").map((w) => {
    if (w === "|") return h("br");
    const open = w.startsWith("*");
    if (open) gold = true;
    const span = h("span", { class: gold ? "w gold" : "w" }, w.replaceAll("*", ""));
    if (w.endsWith("*")) gold = false;
    return span;
  });
}

const blur = (k: number, px: number) => (k > 0.001 ? `blur(${(k * px).toFixed(2)}px)` : "none");

export class Titles {
  el = h("div", { class: "titles" });
  private built: Built[];

  constructor(list: Title[]) {
    this.built = list.map((title) => {
      const ws = words(title.text);
      const big = h("p", { class: "big" }, ...ws.flatMap((w, i) => (i ? [" ", w] : [w])));
      const eyebrow = title.eyebrow ? h("p", { class: "eyebrow" }, title.eyebrow[1]) : undefined;
      const sub = title.sub ? h("p", { class: "sub" }, title.sub[1]) : undefined;
      const el = h(
        "div",
        { class: `card ${title.tone} ${title.place}` },
        ...[eyebrow, big, sub].filter((x) => x !== undefined),
      );
      this.el.append(el);
      return { title, el, words: ws, eyebrow, sub };
    });
  }

  update(t: number) {
    for (const b of this.built) {
      const T = b.title;
      const on = t >= T.at - 0.05 && t < T.out + (T.cut ? 0 : 0.01);
      const lead = T.eyebrow ? Math.min(T.at, T.eyebrow[0]) : T.at;
      const live = t >= lead - 0.05 && t < T.out;
      b.el.style.display = on || live ? "" : "none";
      if (!(on || live)) continue;
      const leave = T.cut ? 0 : out(ramp(t, T.out - 0.55, T.out));
      b.words.forEach((w, i) => {
        const at = T.words?.[i] ?? T.at + i * 0.09;
        const k = out(ramp(t, at, at + 0.95));
        const hide = 1 - k + leave;
        w.style.opacity = (k * (1 - leave)).toFixed(3);
        w.style.filter = blur(Math.min(1, hide), 16);
        w.style.transform = `translateY(${((1 - k) * 0.28 - leave * 0.12).toFixed(3)}em)`;
      });
      for (const [part, at] of [
        [b.eyebrow, T.eyebrow?.[0]],
        [b.sub, T.sub?.[0]],
      ] as [HTMLElement | undefined, number | undefined][]) {
        if (!part || at === undefined) continue;
        const k = out(ramp(t, at, at + 0.8));
        part.style.opacity = (k * (1 - leave)).toFixed(3);
        part.style.filter = blur(Math.min(1, 1 - k + leave), 8);
        part.style.transform = `translateY(${((1 - k) * 0.5).toFixed(3)}em)`;
      }
    }
  }
}

// Small year marks that sit on the water where each shock began.
export class Marks {
  el = h("div", { class: "marks" });
  private items: { el: HTMLElement; at: THREE.Vector3; t: number }[];
  private v = new THREE.Vector3();

  constructor(list: { text: string; at: THREE.Vector3; t: number; up: boolean }[]) {
    this.items = list.map((m) => {
      const el = h("span", { class: m.up ? "mark up" : "mark" }, m.text);
      this.el.append(el);
      return { el, at: m.at, t: m.t };
    });
  }

  update(t: number, camera: THREE.Camera, w: number, h: number) {
    for (const m of this.items) {
      const k = span(t, m.t, m.t + 1.5, 0.2, 0.7);
      m.el.style.display = k > 0 ? "" : "none";
      if (!k) continue;
      this.v.copy(m.at).project(camera);
      m.el.style.opacity = k.toFixed(3);
      m.el.style.transform = `translate(${((this.v.x * 0.5 + 0.5) * w).toFixed(1)}px, ${((0.5 - this.v.y * 0.5) * h).toFixed(1)}px) translate(-50%, -160%)`;
    }
  }
}

// Names that ride beside moving things, such as each agent's role.
export class Tags {
  el = h("div", { class: "marks" });
  private items: HTMLElement[];
  private v = new THREE.Vector3();

  constructor(
    names: string[],
    private from: number,
    private to: number,
  ) {
    this.items = names.map((name) => {
      const el = h("span", { class: "tag" }, name);
      this.el.append(el);
      return el;
    });
  }

  update(t: number, at: THREE.Vector3[], camera: THREE.Camera, w: number, h: number) {
    this.items.forEach((el, i) => {
      const k = span(t, this.from + i * 0.2, this.to, 0.35, 0.5);
      el.style.display = k > 0 ? "" : "none";
      if (!k || !at[i]) return;
      this.v.copy(at[i]).project(camera);
      el.style.opacity = k.toFixed(3);
      el.style.transform = `translate(${((this.v.x * 0.5 + 0.5) * w).toFixed(1)}px, ${((0.5 - this.v.y * 0.5) * h).toFixed(1)}px) translate(-50%, -190%)`;
    });
  }
}

// The last card: the name as it is said, then the line under it, who made it and the honest small
// print.
export class End {
  el: HTMLElement;
  private parts: [HTMLElement, number][];

  constructor(
    lines: { at: number; name: number; title: string; tag: string; event: string; team: string; note: string },
    private fade: number,
  ) {
    const at = lines.at;
    const name = h("p", { class: "end-name", html: lines.title });
    const tag = h("p", { class: "end-tag" }, ...words(lines.tag).flatMap((w, i) => (i ? [" ", w] : [w])));
    const rule = h("div", { class: "end-rule" });
    const event = h("p", { class: "end-event" }, lines.event);
    const team = h("p", { class: "end-team" }, lines.team);
    const note = h("p", { class: "end-note" }, lines.note);
    this.el = h("div", { class: "end" }, h("div", { class: "end-stack" }, name, tag, rule, event, team), note);
    this.parts = [
      [name, lines.name],
      [tag, at],
      [rule, at + 0.5],
      [event, at + 0.8],
      [team, at + 1.0],
      [note, at + 1.3],
    ];
  }

  update(t: number) {
    const leave = ramp(t, this.fade, this.fade + 0.9);
    this.el.style.display = t >= this.parts[0][1] - 0.05 ? "" : "none";
    for (const [el, at] of this.parts) {
      const k = out(ramp(t, at, at + 1.1));
      el.style.opacity = (k * (1 - leave)).toFixed(3);
      el.style.filter = blur(1 - k, 12);
      el.style.transform = el.classList.contains("end-rule")
        ? `scaleX(${k.toFixed(3)})`
        : `translateY(${((1 - k) * 0.35).toFixed(3)}em)`;
    }
  }
}
