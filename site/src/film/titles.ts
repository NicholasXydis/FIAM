import * as THREE from "three";
import { MARK } from "virtual:qr";
import { h } from "../shared/dom";
import { inOut, out, ramp, span } from "../shared/math";

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
  // Animates on the film's clock, so it can move while the story holds.
  film?: boolean;
  // How long each word takes to leave, if not the usual EXIT.
  exit?: number;
  place: "line" | "low";
}

// How long each word takes to leave, and how far apart the words go.
const EXIT = 0.55;
const STAGGER = 0.05;

// The logo and name as the site shows them, the mark then the name.
export const BRAND = `<span class="brand"><svg class="brand-mark" viewBox="0 0 512 512" aria-hidden="true">${MARK}</svg><span>QUARCC <em>Purple</em></span></span>`;
// A dark halo under light text, so it reads over any picture.
const HALO = "0 0 0.12em rgb(4 3 9 / 0.75)";

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
      // A title may be only its small lines, with no big line between.
      const ws = title.text ? words(title.text) : [];
      const big = title.text ? h("p", { class: "big" }, ...ws.flatMap((w, i) => (i ? [" ", w] : [w]))) : undefined;
      const eyebrow = title.eyebrow ? h("p", { class: "eyebrow", html: title.eyebrow[1] }) : undefined;
      const sub = title.sub ? h("p", { class: "sub" }, title.sub[1]) : undefined;
      // A card of four lines or more is tall, set a little smaller and lower.
      const tall = title.text.split("|").length >= 4 ? " tall" : "";
      const el = h(
        "div",
        { class: `card ${title.tone} ${title.place}${tall}` },
        ...[eyebrow, big, sub].filter((x) => x !== undefined),
      );
      this.el.append(el);
      return { title, el, words: ws, eyebrow, sub };
    });
  }

  // Fades each title's words in and out at story time t, or film clock.
  update(story: number, clock = story) {
    for (const b of this.built) {
      const T = b.title;
      const t = T.film ? clock : story;
      // Shown from just before its first word or eyebrow until it goes.
      const on = t >= T.at - 0.05 && t < T.out + 0.01;
      const lead = T.eyebrow ? Math.min(T.at, T.eyebrow[0]) : T.at;
      const live = t >= lead - 0.05 && t < T.out;
      b.el.style.display = on || live ? "" : "none";
      if (!(on || live)) continue;
      // Words leave in reading order, lifting and blurring, gone by out.
      const spans = b.words.filter((w) => w.tagName === "SPAN");
      const exit = T.exit ?? EXIT;
      const first = T.out - exit - STAGGER * Math.max(0, spans.length - 1);
      const gone = (j: number) => inOut(ramp(t, first + j * STAGGER, first + j * STAGGER + exit));
      // Each word rises in and sharpens over 0.95 s on its own cue.
      b.words.forEach((w, i) => {
        const at = T.words?.[i] ?? T.at + i * 0.09;
        const k = out(ramp(t, at, at + 0.95));
        const leave = gone(Math.max(0, spans.indexOf(w)));
        w.style.opacity = (k * (1 - leave)).toFixed(3);
        w.style.filter = blur(Math.min(1, 1 - k + leave), 16);
        w.style.transform = `translateY(${((1 - k) * 0.28 - leave * 0.3).toFixed(3)}em)`;
        // A gold word catches the light as it lands, then keeps a soft glow.
        if (w.classList.contains("gold") && T.tone !== "dark") {
          const glow = (22 + 48 * Math.sin(Math.PI * k)) * (1 - leave);
          w.style.textShadow = `0 0 0.32em color-mix(in srgb, var(--em) ${glow.toFixed(1)}%, transparent), ${HALO}`;
        }
      });
      // Eyebrow and sub rise in on their cues, leave with the end words.
      for (const [part, at, leave] of [
        [b.eyebrow, T.eyebrow?.[0], gone(0)],
        [b.sub, T.sub?.[0], gone(spans.length - 1)],
      ] as [HTMLElement | undefined, number | undefined, number][]) {
        if (!part || at === undefined) continue;
        const k = out(ramp(t, at, at + 0.8));
        part.style.opacity = (k * (1 - leave)).toFixed(3);
        part.style.filter = blur(Math.min(1, 1 - k + leave), 8);
        part.style.transform = `translateY(${((1 - k) * 0.5 - leave * 0.3).toFixed(3)}em)`;
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
  inside = false,
) {
  el.style.display = k > 0 ? "" : "none";
  if (!k || !at) return;
  pinned.copy(at).project(camera);
  el.style.opacity = k.toFixed(3);
  let x = (pinned.x * 0.5 + 0.5) * w;
  // Inside keeps the whole label in frame, 2% of the width from the edge.
  if (inside) {
    const half = el.offsetWidth / 2 + w * 0.02;
    x = Math.min(Math.max(x, half), w - half);
  }
  el.style.transform = `translate(${x.toFixed(1)}px, ${((0.5 - pinned.y * 0.5) * h).toFixed(1)}px) translate(-50%, ${lift})`;
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
      pin(el, span(t, this.from + i * 0.2, this.to, 0.35, 0.5), at[i], camera, w, h, "-190%", h > w),
    );
  }
}

// The last card: the logo and name as it is said, then line and names.
export class End {
  el: HTMLElement;
  private parts: [HTMLElement, number][];

  // Builds the card, each part with the time it arrives.
  constructor(
    lines: { at: number; name: number; tag: string; event: string; team: string },
    private fade: number,
  ) {
    const at = lines.at;
    const name = h("p", { class: "end-name", html: BRAND });
    const tag = h("p", { class: "end-tag" }, ...words(lines.tag).flatMap((w, i) => (i ? [" ", w] : [w])));
    const rule = h("div", { class: "end-rule" });
    const event = h("p", { class: "end-event" }, lines.event);
    const team = h("p", { class: "end-team" }, lines.team);
    this.el = h("div", { class: "end" }, h("div", { class: "end-stack" }, name, tag, rule, event, team));
    // The name on its word, the rest in turn over the next second.
    this.parts = [
      [name, lines.name],
      [tag, at],
      [rule, at + 0.5],
      [event, at + 0.8],
      [team, at + 1.0],
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
