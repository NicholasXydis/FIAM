import gsap from "gsap";
import * as THREE from "three";
import { MONTH_COUNT, weights } from "../shared/data";
import { type Child, h } from "../shared/dom";
import { every, small, stale } from "./layout";

// The one tooltip, shared by every scene.
export const tip = h("div", { class: "tip glass", "aria-hidden": "true" });
// The tooltip's last text, so it is only rewritten on change.
let tipHtml = "";
// Its width when last measured.
let tipW = 0;
// Its height when last measured.
let tipH = 0;

// Puts the tooltip by the mouse or above a finger, measured on change.
export function showTip(html: string, x: number, y: number, above = false) {
  const shown = tip.classList.contains("on");
  tip.classList.add("on");
  // New text or a fresh show: write it and measure it again.
  if (html !== tipHtml || !shown) {
    if (html !== tipHtml) tip.innerHTML = html;
    tipHtml = html;
    tipW = tip.offsetWidth;
    tipH = tip.offsetHeight;
  }
  // 18 px right of a mouse, or 28 px above a finger, kept 12 px in.
  const w = tipW;
  const t = tipH;
  const side = x + 18 + w > innerWidth - 12 ? x - w - 18 : x + 18;
  const left = above ? Math.max(12, Math.min(innerWidth - w - 12, x - w / 2)) : Math.max(12, side);
  const high = y - t - 28 < 64 ? y + 28 : y - t - 28;
  const top = Math.min(Math.max(12, above ? high : y - t / 2), innerHeight - t - 12);
  tip.style.transform = `translate(${left}px, ${top}px)`;
}

// Fades the tooltip out; its text stays for the next show.
export function hideTip() {
  tip.classList.remove("on");
}

// Scratch: a point projected onto the screen.
const v = new THREE.Vector3();
// Scratch: the raycaster each call to rayAt reuses.
const caster = new THREE.Raycaster();
// Scratch: a pixel in the camera's -1 to 1 space.
const ndc = new THREE.Vector2();

// The ray through a screen pixel, in a shared caster each call reuses.
export function rayAt(x: number, y: number, camera: THREE.Camera) {
  ndc.set((x / innerWidth) * 2 - 1, -(y / innerHeight) * 2 + 1);
  caster.setFromCamera(ndc, camera);
  return caster;
}

// Where a world point lands on screen in pixels, and if it is in front.
export function screen(p: THREE.Vector3, camera: THREE.Camera, out = { x: 0, y: 0, front: true }) {
  v.copy(p).project(camera);
  out.x = (v.x * 0.5 + 0.5) * innerWidth;
  out.y = (-v.y * 0.5 + 0.5) * innerHeight;
  out.front = v.z < 1;
  return out;
}

// The scratch spot that nearest and every Label share.
const spot = { x: 0, y: 0, front: true };

// The point nearest a screen spot within a radius (30 px), or -1.
export function nearest(points: THREE.Vector3[], x: number, y: number, camera: THREE.Camera, radius = 30) {
  let best = -1;
  let bestD = radius * radius;
  // Keep the nearest point in front within the radius.
  points.forEach((p, i) => {
    screen(p, camera, spot);
    const d = (spot.x - x) ** 2 + (spot.y - y) ** 2;
    if (spot.front && d < bestD) {
      bestD = d;
      best = i;
    }
  });
  return best;
}

// Where an anchored label sits against its point.
type Align = "left" | "center" | "right";

// A DOM label pinned to a 3D point, writing to the page only on change.
export class Label {
  el: HTMLElement;
  at: THREE.Vector3;
  // Wanted by its scene; it shows only while its point is in front too.
  shown = false;
  // Small screens: rank (0 may hide), if the fit counts it, own words.
  prio = 0;
  fits = true;
  // Axis marks stay on their point, hiding rather than nudged off it.
  moves = true;
  small: { html?: string; at?: THREE.Vector3; align?: Align; cls?: string } | null = null;
  // Its measured size, screen box and nudge, kept for the small layouts.
  width = 0;
  height = 0;
  box: { x: number; y: number; w: number; h: number } | null = null;
  dy = 0;
  blocked = false;
  private text: string;
  private last = "";
  private on = false;
  private measured = "";

  // Anchors the label at its point by its left, centre or right side.
  constructor(
    html: string,
    at: THREE.Vector3 | [number, number, number],
    public align: Align = "center",
    cls = "",
  ) {
    this.el = h("div", { class: `label3d ${cls}`, html });
    this.at = Array.isArray(at) ? new THREE.Vector3(...at) : at;
    this.text = html;
    if (cls.includes("big")) this.prio = 3;
  }

  // The point it sits at: the small layout's, when it has one.
  get where() {
    return (small() && this.small?.at) || this.at;
  }
  // The side it anchors by: the small layout's, when it has one.
  get anchor() {
    return (small() && this.small?.align) || this.align;
  }

  // Sets the label's text, touching the page only if it changed.
  set(html: string) {
    this.text = html;
    if (this.el.innerHTML !== html) this.el.innerHTML = html;
  }

  // Follows its point on screen, and fades out while the point is behind.
  place(camera: THREE.Camera) {
    if (small()) return this.placeSmall(camera);
    if (this.measured) this.restore();
    screen(this.at, camera, spot);
    const shift = this.align === "center" ? "-50%" : this.align === "right" ? "-100%" : "0%";
    const transform = `translate(${spot.x.toFixed(1)}px, ${spot.y.toFixed(1)}px) translate(${shift}, -50%)`;
    // Move it only when its place on screen changed.
    if (transform !== this.last) {
      this.el.style.transform = transform;
      this.last = transform;
    }
    const on = this.shown && spot.front;
    // Fade it in or out only when that changed.
    if (on !== this.on) {
      this.el.classList.toggle("on", on);
      this.on = on;
    }
  }

  // Small screens: its own words, measured, kept inside the screen edges.
  private placeSmall(camera: THREE.Camera) {
    const html = this.small?.html ?? this.text;
    if (this.el.innerHTML !== html) this.el.innerHTML = html;
    if (this.small?.cls) this.el.classList.add(this.small.cls);
    // Measure again when its words change, or every 30 frames.
    if (this.measured !== html || every(30)) {
      this.measured = html;
      this.width = this.el.offsetWidth;
      this.height = this.el.offsetHeight;
    }
    screen(this.where, camera, spot);
    const a = this.anchor === "center" ? 0.5 : this.anchor === "right" ? 1 : 0;
    const left = Math.max(8, Math.min(innerWidth - 8 - this.width, spot.x - a * this.width));
    const top = spot.y - this.height / 2;
    this.box = { x: left, y: top, w: this.width, h: this.height };
    const transform = `translate(${left.toFixed(1)}px, ${(top + this.dy).toFixed(1)}px)`;
    // Move it only when its place on screen changed.
    if (transform !== this.last) {
      this.el.style.transform = transform;
      this.last = transform;
    }
    const on = this.shown && spot.front && !this.blocked;
    // Fade it in or out only when that changed.
    if (on !== this.on) {
      this.el.classList.toggle("on", on);
      this.on = on;
    }
  }

  // Back on the desktop: its own words and class again, nothing nudged.
  private restore() {
    this.measured = "";
    this.dy = 0;
    this.blocked = false;
    this.box = null;
    if (this.small?.cls) this.el.classList.remove(this.small.cls);
    if (this.el.innerHTML !== this.text) this.el.innerHTML = this.text;
    this.last = "";
  }

  // Fades the label out until its scene sets it shown again.
  hide() {
    this.shown = false;
    this.on = false;
    this.el.classList.remove("on");
  }
}

// A toggle on small screens that shows the nodes it folds away.
export function fold(box: HTMLElement, row: HTMLElement, nodes: Element[], label: string) {
  box.classList.add("fold");
  for (const n of nodes) n.setAttribute("data-more", "");
  const b = chip(
    label,
    // Each press opens or closes the folded nodes.
    () => {
      const open = box.classList.toggle("open");
      b.setAttribute("aria-pressed", String(open));
      stale();
    },
    false,
  );
  b.classList.add("more-toggle");
  row.append(b);
  return b;
}

// Counts up from zero over 1.6 s, easing out, one format at every step.
export function count(el: HTMLElement, to: number, format: (x: number) => string, duration = 1.6, delay = 0) {
  const state = { x: 0 };
  el.textContent = format(0);
  return gsap.to(state, {
    x: to,
    duration,
    delay,
    ease: "expo.out",
    // Write the number at each step, in the given format.
    onUpdate: () => {
      el.textContent = format(state.x);
    },
  });
}

// A big number over its caption; value is the number to count into.
export function stat(value: string, label: string) {
  const b = h("b", {}, value);
  const caption = h("span", {}, label);
  return { el: h("div", {}, b, caption), value: b, caption };
}

// Sets --fill so the track is painted purple up to the slider's value.
export function fill(input: HTMLInputElement) {
  const p = ((+input.value - +input.min) / (+input.max - +input.min)) * 100;
  input.style.setProperty("--fill", `${p}%`);
}

// A range slider named for screen readers, its fill tracking its value.
export function slider(id: string, label: string, min: number, max: number, step: number, value: number) {
  const input = h("input", { id, type: "range", min, max, step, value, "aria-label": label }) as HTMLInputElement;
  fill(input);
  input.addEventListener("input", () => fill(input));
  return input;
}

// A frosted box of controls: rounded glass, padded, parts in a column.
export const box = (cls: string, ...parts: Child[]) =>
  h("div", { class: `glass rounded-2xl px-4 py-3 flex flex-col ${cls}` }, ...parts);

// A tile that acts as a button; the tour's Space and Enter press it.
export function asButton(el: HTMLElement, press: () => void) {
  el.setAttribute("role", "button");
  el.tabIndex = 0;
  el.addEventListener("click", press);
  return el;
}

// A legend, a line each; light() brightens some and fades the rest.
export function legendOf(lines: string[]) {
  const items = lines.map((html) => h("p", { class: "text-[13px] text-ink-2", html }));
  // Faded by script, so no class word adds styles to the tour.
  const light = (lit: number[]) =>
    items.forEach((line, i) =>
      line.animate({ opacity: lit.includes(i) ? 1 : 0.35 }, { duration: 300, fill: "forwards" }),
    );
  return { el: h("div", { class: "flex flex-col gap-1 pt-1" }, ...items), light };
}

// A chip button; passing pressed makes it a toggle with aria-pressed.
export function chip(text: string, onClick: () => void, pressed?: boolean) {
  const b = h("button", { class: "chip", type: "button", html: text }) as HTMLButtonElement;
  if (pressed !== undefined) b.setAttribute("aria-pressed", String(pressed));
  b.addEventListener("click", onClick);
  return b;
}

// A stock search: up to six tickers that start with it, then names.
export function finder(example: string, none: string, tickers: string[], names: string[], go: (i: number) => void) {
  const input = h("input", {
    class: "search",
    type: "search",
    placeholder: `Find a stock, like ${example}`,
    "aria-label": "Find a stock",
    autocomplete: "off",
    spellcheck: "false",
  }) as HTMLInputElement;
  const matches = h("div", { class: "flex flex-wrap gap-1.5 empty:hidden" });
  // Each keystroke lists the hits as chips, or says there are none.
  const suggest = () => {
    const q = input.value.trim().toUpperCase();
    matches.innerHTML = "";
    if (!q) return;
    const hits: number[] = [];
    // Tickers that start with the search come first.
    for (let i = 0; i < tickers.length && hits.length < 6; i++) if (tickers[i]?.startsWith(q)) hits.push(i);
    // Then names that contain it, up to six hits in all.
    for (let i = 0; i < names.length && hits.length < 6; i++) {
      if (!hits.includes(i) && names[i]?.toUpperCase().includes(q)) hits.push(i);
    }
    if (!hits.length) matches.append(h("span", { class: "text-[12px] text-ink-3" }, none));
    // A ticker held by two stocks gets the first word of each name.
    const twice = (i: number) => hits.some((j) => j !== i && tickers[j] === tickers[i]);
    // One chip per hit, which opens that stock.
    for (const i of hits) {
      const label = `${tickers[i] || "No ticker"}${twice(i) ? ` ${names[i]?.split(" ")[0] ?? ""}` : ""}`;
      matches.append(chip(label, () => go(i)));
    }
  };
  // Typing suggests, Enter takes the first hit, Escape leaves the box.
  input.addEventListener("input", suggest);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") (matches.firstElementChild as HTMLButtonElement | null)?.click();
    if (e.key === "Escape") input.blur();
  });
  return { input, matches };
}

// A stock's weight by month as bars, longs up, shorts down, now dashed.
export function spark(stock: number, month: number) {
  const w = weights(stock);
  const W = 292;
  const H = 76;
  const top = Math.max(0.2, ...Array.from(w, Math.abs));
  // A month to x across the chart.
  const x = (i: number) => (i / (MONTH_COUNT - 1)) * W;
  // A weight to a height, zero in the middle.
  const y = (v: number) => H / 2 - (v / top) * (H / 2 - 6);
  // One bar per month held: up for long, down for short.
  const bars = Array.from(w, (v, i) => {
    if (!v) return "";
    const color = v > 0 ? "var(--m-long)" : "var(--m-short)";
    const height = Math.max(1, Math.abs(y(v) - H / 2));
    return `<rect x="${x(i) - 1.6}" y="${Math.min(y(v), H / 2)}" width="3.2" height="${height}" rx="1.2" fill="${color}"/>`;
  }).join("");
  const now = x(month);
  return `<svg viewBox="-4 0 ${W + 8} ${H}" width="100%" height="${H}" role="img" aria-label="Weight by month">
    <line x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}" stroke="rgb(237 233 246 / .25)" stroke-width="1"/>
    ${bars}
    <line x1="${now}" x2="${now}" y1="2" y2="${H - 2}" stroke="var(--ink)" stroke-width="1" stroke-dasharray="2 3"/>
  </svg>`;
}

// A side card for one item: label, name, a Close chip and its details.
export class SideCard {
  el = h("aside", { class: "card glass", hidden: true });

  // Placed 72 px down and 56 px in from the right, less on small phones.
  constructor(
    layer: HTMLElement,
    private onClose: () => void,
  ) {
    this.el.style.right = "max(16px, env(safe-area-inset-right, 0px), min(56px, 100vw - 346px))";
    this.el.style.top = "72px";
    layer.append(this.el);
  }

  // Fills the card afresh with a label, a name and the details below.
  show(label: string, name: string, ...details: HTMLElement[]) {
    this.el.hidden = false;
    this.el.innerHTML = "";
    this.el.append(
      h(
        "div",
        { class: "flex items-start justify-between gap-3" },
        h("div", {}, h("p", { class: "eyebrow" }, label), h("p", { class: "headline text-[26px]" }, name)),
        chip("Close", this.onClose),
      ),
      ...details,
    );
  }

  // Takes the card off the screen, keeping what it showed.
  hide() {
    this.el.hidden = true;
  }
}

// A colour square for keys and legends, filled or just outlined.
export const swatch = (color: string, outline = false) =>
  `<span class="swatch" style="${outline ? `border:1px solid ${color};background:none` : `background:${color}`}"></span>`;

// Steps the months on a timer behind a Play and Pause chip, or Space.
export class Player {
  playing = false;
  button = chip("Play", () => (this.playing ? this.stop() : this.start()), false);
  private timer: gsap.core.Tween | null = null;

  // Seconds per month, the last month, and hooks into the scene's month.
  constructor(
    private delay: number,
    private last: number,
    private at: () => number,
    private go: (month: number) => void,
    private live: () => boolean,
  ) {}

  // Plays on from the current month, or from the first if at the end.
  start() {
    this.timer?.kill();
    if (this.at() >= this.last) this.go(0);
    this.playing = true;
    this.button.textContent = "Pause";
    this.button.setAttribute("aria-pressed", "true");
    // Each beat moves a month, stopping at the end or once the scene goes.
    const next = () => {
      if (!this.playing || !this.live()) return;
      if (this.at() >= this.last) return this.stop();
      this.go(this.at() + 1);
      this.timer = gsap.delayedCall(this.delay, next);
    };
    this.timer = gsap.delayedCall(this.delay, next);
  }

  // Stops on the current month.
  stop() {
    this.playing = false;
    this.timer?.kill();
    this.button.textContent = "Play";
    this.button.setAttribute("aria-pressed", "false");
  }

  // Space plays or pauses; true when it handled the key.
  key(e: KeyboardEvent) {
    if (e.key !== " ") return false;
    if (this.playing) this.stop();
    else this.start();
    return true;
  }
}

// A month slider and its Play chip; dragging the slider stops the play.
export function months(id: string, delay: number, scene: { month: number; active: boolean; set(month: number): void }) {
  const player = new Player(
    delay,
    MONTH_COUNT - 1,
    () => scene.month,
    (m) => scene.set(m),
    () => scene.active,
  );
  const input = slider(id, "Month", 0, MONTH_COUNT - 1, 1, 0);
  // Dragging stops the play and shows the chosen month.
  input.addEventListener("input", () => {
    player.stop();
    scene.set(+input.value);
  });
  return { player, input };
}
