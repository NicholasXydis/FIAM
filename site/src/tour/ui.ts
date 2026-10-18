import gsap from "gsap";
import * as THREE from "three";
import { MONTH_COUNT } from "../shared/data";
import { h } from "../shared/dom";

// The one tooltip, its last text and size kept to spare layout.
export const tip = h("div", { class: "tip glass", "aria-hidden": "true" });
let tipHtml = "";
let tipW = 0;
let tipH = 0;

// Puts the tooltip by the mouse, measuring only when its text changes.
export function showTip(html: string, x: number, y: number) {
  const shown = tip.classList.contains("on");
  tip.classList.add("on");
  if (html !== tipHtml || !shown) {
    if (html !== tipHtml) tip.innerHTML = html;
    tipHtml = html;
    tipW = tip.offsetWidth;
    tipH = tip.offsetHeight;
  }
  // Sits 18 px right of the pointer, or left near the edge, 12 px in.
  const w = tipW;
  const t = tipH;
  const left = x + 18 + w > innerWidth - 12 ? x - w - 18 : x + 18;
  const top = Math.min(Math.max(12, y - t / 2), innerHeight - t - 12);
  tip.style.transform = `translate(${left}px, ${top}px)`;
}

// Fades the tooltip out; its text stays for the next show.
export function hideTip() {
  tip.classList.remove("on");
}

// Scratch reused per call, so hover and labels allocate nothing.
const v = new THREE.Vector3();
const caster = new THREE.Raycaster();
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

// A DOM label pinned to a 3D point, writing to the page only on change.
export class Label {
  el: HTMLElement;
  at: THREE.Vector3;
  // Wanted by its scene; it shows only while its point is in front too.
  shown = false;
  private last = "";
  private on = false;

  // Anchors the label at its point by its left, centre or right side.
  constructor(
    html: string,
    at: THREE.Vector3 | [number, number, number],
    public align: "left" | "center" | "right" = "center",
    cls = "",
  ) {
    this.el = h("div", { class: `label3d ${cls}`, html });
    this.at = Array.isArray(at) ? new THREE.Vector3(...at) : at;
  }

  // Sets the label's text, touching the page only if it changed.
  set(html: string) {
    if (this.el.innerHTML !== html) this.el.innerHTML = html;
  }

  // Follows its point on screen, and fades out while the point is behind.
  place(camera: THREE.Camera) {
    screen(this.at, camera, spot);
    const shift = this.align === "center" ? "-50%" : this.align === "right" ? "-100%" : "0%";
    const transform = `translate(${spot.x.toFixed(1)}px, ${spot.y.toFixed(1)}px) translate(${shift}, -50%)`;
    if (transform !== this.last) {
      this.el.style.transform = transform;
      this.last = transform;
    }
    const on = this.shown && spot.front;
    if (on !== this.on) {
      this.el.classList.toggle("on", on);
      this.on = on;
    }
  }

  // Fades the label out until its scene sets it shown again.
  hide() {
    this.shown = false;
    this.on = false;
    this.el.classList.remove("on");
  }
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
    onUpdate: () => {
      el.textContent = format(state.x);
    },
  });
}

// A big number over its caption; value is the number to count into.
export function stat(value: string, label: string) {
  const b = h("b", {}, value);
  return { el: h("div", {}, b, h("span", {}, label)), value: b };
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

// A chip button; passing pressed makes it a toggle with aria-pressed.
export function chip(text: string, onClick: () => void, pressed?: boolean) {
  const b = h("button", { class: "chip", type: "button", html: text }) as HTMLButtonElement;
  if (pressed !== undefined) b.setAttribute("aria-pressed", String(pressed));
  b.addEventListener("click", onClick);
  return b;
}

// A side card for one item: label, name, a Close chip and its details.
export class SideCard {
  el = h("aside", { class: "card glass", hidden: true });

  // Placed 72 px down and at least 56 px in from the right edge.
  constructor(
    layer: HTMLElement,
    private onClose: () => void,
  ) {
    this.el.style.right = "max(56px, env(safe-area-inset-right, 0px))";
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
  input.addEventListener("input", () => {
    player.stop();
    scene.set(+input.value);
  });
  return { player, input };
}
