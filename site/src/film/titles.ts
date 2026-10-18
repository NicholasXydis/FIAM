import * as THREE from "three";
import { h } from "../shared/dom";
import { out, ramp, span } from "../shared/math";

// One title, *starred* words in italic gold, each word on its own cue.
export interface Title {
  at: number;
  out: number;
  text: string;
  // Each word's own time, by default 0.09 s apart.
  words?: number[];
  // The small line above and the line below, each with its time.
  eyebrow?: [number, string];
  sub?: [number, string];
  tone: "light" | "dark" | "storm";
  place: "line" | "low";
  // A cut ends it at once, otherwise it leaves softly.
  cut?: boolean;
}

// A title and the elements built for it.
interface Built {
  title: Title;
  el: HTMLElement;
  words: HTMLElement[];
  eyebrow?: HTMLElement | undefined;
  sub?: HTMLElement | undefined;
}

// The words of a line as spans, gold between stars, | a line break.
function words(text: string) {
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

// A CSS blur of k times px, or none once it is all but gone.
const blur = (k: number, px: number) => (k > 0.001 ? `blur(${(k * px).toFixed(2)}px)` : "none");

// Every title of the film, shown and hidden by time.
export class Titles {
  el = h("div", { class: "titles" });
  private built: Built[];

  // Builds each title's card, eyebrow above, big line, sub below.
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

  // Fades each title's words in and out at time t.
  update(t: number) {
    for (const b of this.built) {
      const T = b.title;
      // Shown from just before its first word or eyebrow until it goes.
      const on = t >= T.at - 0.05 && t < T.out + (T.cut ? 0 : 0.01);
      const lead = T.eyebrow ? Math.min(T.at, T.eyebrow[0]) : T.at;
      const live = t >= lead - 0.05 && t < T.out;
      b.el.style.display = on || live ? "" : "none";
      if (!(on || live)) continue;
      // A soft exit over the last 0.55 s, or none on a cut.
      const leave = T.cut ? 0 : out(ramp(t, T.out - 0.55, T.out));
      // Each word rises in and sharpens over 0.95 s on its own cue.
      b.words.forEach((w, i) => {
        const at = T.words?.[i] ?? T.at + i * 0.09;
        const k = out(ramp(t, at, at + 0.95));
        const hide = 1 - k + leave;
        w.style.opacity = (k * (1 - leave)).toFixed(3);
        w.style.filter = blur(Math.min(1, hide), 16);
        w.style.transform = `translateY(${((1 - k) * 0.28 - leave * 0.12).toFixed(3)}em)`;
      });
      // The eyebrow and sub rise in over 0.8 s on their own cues.
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

// Scratch point for projecting onto the screen.
const pinned = new THREE.Vector3();

// Pins a name over its point on screen, faded by k, or hides it.
function pin(
  el: HTMLElement,
  k: number,
  at: THREE.Vector3 | undefined,
  camera: THREE.Camera,
  w: number,
  h: number,
  lift: string,
) {
  el.style.display = k > 0 ? "" : "none";
  if (!k || !at) return;
  pinned.copy(at).project(camera);
  el.style.opacity = k.toFixed(3);
  el.style.transform = `translate(${((pinned.x * 0.5 + 0.5) * w).toFixed(1)}px, ${((0.5 - pinned.y * 0.5) * h).toFixed(1)}px) translate(-50%, ${lift})`;
}

// Small year marks that sit on the water where each shock began.
export class Marks {
  el = h("div", { class: "marks" });
  private items: { el: HTMLElement; at: THREE.Vector3; t: number }[];

  // One span per year, cyan when the market rose.
  constructor(list: { text: string; at: THREE.Vector3; t: number; up: boolean }[]) {
    this.items = list.map((m) => {
      const el = h("span", { class: m.up ? "mark up" : "mark" }, m.text);
      this.el.append(el);
      return { el, at: m.at, t: m.t };
    });
  }

  // Pins each year mark to its ripple for 1.5 s, fading in and out.
  update(t: number, camera: THREE.Camera, w: number, h: number) {
    for (const m of this.items) pin(m.el, span(t, m.t, m.t + 1.5, 0.2, 0.7), m.at, camera, w, h, "-160%");
  }
}

// Names that ride beside moving things, such as each agent's role.
export class Tags {
  el = h("div", { class: "marks" });
  private items: HTMLElement[];

  // One tag per role, each shown between the two cues.
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

  // Pins each role's name beside its agent, arriving 0.2 s apart.
  update(t: number, at: THREE.Vector3[], camera: THREE.Camera, w: number, h: number) {
    this.items.forEach((el, i) =>
      pin(el, span(t, this.from + i * 0.2, this.to, 0.35, 0.5), at[i], camera, w, h, "-190%"),
    );
  }
}

// The last card, name as it is said, then line, team and small print.
export class End {
  el: HTMLElement;
  private parts: [HTMLElement, number][];

  // Builds the card, each part with the time it arrives.
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
    // The name on its word, the rest in turn over the next 1.3 s.
    this.parts = [
      [name, lines.name],
      [tag, at],
      [rule, at + 0.5],
      [event, at + 0.8],
      [team, at + 1.0],
      [note, at + 1.3],
    ];
  }

  // Fades the card's parts in, then the whole card out.
  update(t: number) {
    const leave = ramp(t, this.fade, this.fade + 0.9);
    this.el.style.display = t >= this.parts[0][1] - 0.05 ? "" : "none";
    for (const [el, at] of this.parts) {
      const k = out(ramp(t, at, at + 1.1));
      el.style.opacity = (k * (1 - leave)).toFixed(3);
      el.style.filter = blur(1 - k, 12);
      // The rule draws out sideways, the rest rise into place.
      el.style.transform = el.classList.contains("end-rule")
        ? `scaleX(${k.toFixed(3)})`
        : `translateY(${((1 - k) * 0.35).toFixed(3)}em)`;
    }
  }
}
