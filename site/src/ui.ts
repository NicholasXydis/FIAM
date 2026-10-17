import gsap from "gsap";
import * as THREE from "three";

type Child = Node | string | null | undefined | false;

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Record<string, string | number | boolean | EventListener> = {},
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "html") el.innerHTML = String(value);
    else if (value !== false) el.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children) if (child) el.append(child);
  return el;
}

export const tip = h("div", { class: "tip glass", role: "status" });
let tipHtml = "";

// The tooltip measures itself only when its text changes, so following the mouse costs no layout.
export function showTip(html: string, x: number, y: number) {
  if (html !== tipHtml) {
    tip.innerHTML = html;
    tipHtml = html;
  }
  tip.classList.add("on");
  const w = tip.offsetWidth;
  const t = tip.offsetHeight;
  const left = x + 18 + w > innerWidth - 12 ? x - w - 18 : x + 18;
  const top = Math.min(Math.max(12, y - t / 2), innerHeight - t - 12);
  tip.style.transform = `translate(${left}px, ${top}px)`;
}

export function hideTip() {
  tip.classList.remove("on");
}

const v = new THREE.Vector3();
const caster = new THREE.Raycaster();
const ndc = new THREE.Vector2();

// A ray from the camera through a screen point.
export function rayAt(x: number, y: number, camera: THREE.Camera) {
  ndc.set((x / innerWidth) * 2 - 1, -(y / innerHeight) * 2 + 1);
  caster.setFromCamera(ndc, camera);
  return caster;
}

// Where a world point lands on screen, in pixels, and whether it is in front of the camera.
export function screen(p: THREE.Vector3, camera: THREE.Camera, out = { x: 0, y: 0, front: true }) {
  v.copy(p).project(camera);
  out.x = (v.x * 0.5 + 0.5) * innerWidth;
  out.y = (-v.y * 0.5 + 0.5) * innerHeight;
  out.front = v.z < 1;
  return out;
}

const spot = { x: 0, y: 0, front: true };

// The index of the point nearest a screen position, within a radius in pixels, or -1.
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

// A DOM label pinned to a point in the 3D scene. It writes to the page only when it moves.
export class Label {
  el: HTMLElement;
  at: THREE.Vector3;
  shown = false;
  private last = "";
  private on = false;

  constructor(
    html: string,
    at: THREE.Vector3 | [number, number, number],
    public align: "left" | "center" | "right" = "center",
    cls = "",
  ) {
    this.el = h("div", { class: `label3d ${cls}`, html });
    this.at = Array.isArray(at) ? new THREE.Vector3(...at) : at;
  }

  set(html: string) {
    if (this.el.innerHTML !== html) this.el.innerHTML = html;
  }

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

  hide() {
    this.shown = false;
    this.on = false;
    this.el.classList.remove("on");
  }
}

// Counts a number up from zero into an element, formatted the same way at every step.
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

export function stat(value: string, label: string) {
  const b = h("b", {}, value);
  return { el: h("div", {}, b, h("span", {}, label)), value: b };
}

export function fill(input: HTMLInputElement) {
  const p = ((+input.value - +input.min) / (+input.max - +input.min)) * 100;
  input.style.setProperty("--fill", `${p}%`);
}

export function slider(id: string, label: string, min: number, max: number, step: number, value: number) {
  const input = h("input", { id, type: "range", min, max, step, value, "aria-label": label }) as HTMLInputElement;
  fill(input);
  input.addEventListener("input", () => fill(input));
  return input;
}

export function chip(text: string, onClick: () => void, pressed?: boolean) {
  const b = h("button", { class: "chip", type: "button", html: text }) as HTMLButtonElement;
  if (pressed !== undefined) b.setAttribute("aria-pressed", String(pressed));
  b.addEventListener("click", onClick);
  return b;
}

export const swatch = (color: string, outline = false) =>
  `<span class="swatch" style="${outline ? `border:1px solid ${color};background:none` : `background:${color}`}"></span>`;
