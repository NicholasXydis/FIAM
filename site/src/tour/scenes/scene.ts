import gsap from "gsap";
import * as THREE from "three";
import { seeded } from "../../shared/math";
import { C } from "../../shared/palette";
import { type Formation, N, type Sim } from "../gl/sim";
import type { Shot, Stage } from "../gl/stage";
import type { Sound } from "../sound";
import { h } from "../../shared/dom";
import { type Box, boxes, coarse, declutter, every, phone, small, stale } from "../layout";
import { type Label } from "../ui";

export { C } from "../../shared/palette";

// Shared by every scene: the stage, particles, page layer and sound.
export interface World {
  stage: Stage;
  sim: Sim;
  layer: HTMLElement;
  sound: Sound;
  go: (i: number) => void;
  next: () => void;
}

// A tour scene: panel, 3D group, labels, and how it enters and leaves.
export abstract class Scene {
  abstract name: string;
  abstract summary: string;
  group = new THREE.Group();
  panel: HTMLElement;
  controls: HTMLElement;
  labels: Label[] = [];
  shot: Shot = { eye: [0, 0, 30], look: [0, 0, 0] };
  stagger = 1.1;
  duration = 1.4;
  dwell = 14;
  physics = { stiff: 9, damp: 1.25, flow: 0.5, spin: 0.04, mouse: 1 };
  // What small screens fit into their band: a world box, and a zoom cap.
  frame: THREE.Vector3[] = [];
  zoomCap = 1.3;
  active = false;
  private covers: Box[] = [];
  protected timeline: gsap.core.Timeline | null = null;

  // Mounts panel and controls on the page, and the group unseen in 3D.
  constructor(protected w: World) {
    this.panel = h("section", { class: "panel" });
    this.controls = h("div", { class: "controls" });
    w.layer.append(this.panel, this.controls);
    this.group.visible = false;
    w.stage.scene.add(this.group);
  }

  // Where every particle rests here, handed to sim.show on arrival.
  abstract formation(): Formation;

  // Puts a label on the page and in the list hide and place walk.
  addLabel(label: Label) {
    this.labels.push(label);
    this.w.layer.append(label.el);
    return label;
  }

  // Hook run as the scene arrives, once its panel starts rising in.
  enter() {}
  // Hook run as the scene goes, once its panel starts fading out.
  leave() {}
  // Hook run every frame with the frame's seconds and the tour clock.
  tick(_dt: number, _t: number) {}
  // Tooltip HTML for a screen point in pixels, or null for none.
  hover(_x: number, _y: number): string | null {
    return null;
  }
  // Hook run on a click or tap that is neither a drag nor a swipe.
  click(_x: number, _y: number) {}
  // Sees each key before the tour does, and returns true if it used it.
  key(_e: KeyboardEvent) {
    return false;
  }

  // Brings the scene in: panel rises, its group fades up, then enter.
  show() {
    this.active = true;
    this.group.visible = true;
    this.panel.classList.add("on");
    this.controls.classList.add("on");
    gsap.fromTo(
      [this.panel, this.controls],
      { opacity: 0, y: 16 },
      { opacity: 1, y: 0, duration: 0.9, delay: 0.35, ease: "power3.out" },
    );
    const items = this.panel.querySelectorAll("[data-rise]");
    gsap.fromTo(
      items,
      { opacity: 0, y: 18, filter: "blur(6px)" },
      { opacity: 1, y: 0, filter: "blur(0px)", duration: 0.9, delay: 0.45, stagger: 0.08, ease: "power3.out" },
    );
    fade(this.group, 1, 1.2, 0.3, undefined, 0);
    this.enter();
  }

  // Exits: stops the timeline, hides the labels, fades panel and group.
  hide() {
    this.active = false;
    this.timeline?.kill();
    this.timeline = null;
    gsap.to([this.panel, this.controls], {
      opacity: 0,
      y: -10,
      duration: 0.4,
      ease: "power2.in",
      onComplete: () => {
        if (this.active) return;
        this.panel.classList.remove("on");
        this.controls.classList.remove("on");
      },
    });
    for (const l of this.labels) l.hide();
    fade(this.group, 0, 0.6, 0, () => {
      if (!this.active) this.group.visible = false;
    });
    this.leave();
  }

  // Flags every label shown, so place draws them from the next frame.
  showLabels() {
    for (const l of this.labels) l.shown = true;
  }

  // Pins each label to its 3D point on screen, called every frame.
  place(camera: THREE.Camera) {
    for (const l of this.labels) l.place(camera);
    if (!small() || !every(4)) return;
    // On small screens, labels step clear of boxes and of each other.
    if (every(12) || !this.covers.length) this.covers = boxes(this);
    declutter(this.labels, this.covers);
  }
}

// Panel opening: the headline with its emphasis, then the body.
export function header(title: string, body: string) {
  const text = h("p", { class: "body", "data-rise": true }, coarse() ? body.replace(/\bClick\b/g, "Tap") : body);
  // On phones a clamped body opens and closes with a tap.
  text.addEventListener("click", () => {
    if (!phone()) return;
    text.classList.toggle("open");
    stale();
  });
  return [h("h2", { class: "headline text-[44px] md:text-[56px]", "data-rise": true, html: title }), text];
}

// A panel's row of figures, rising in with the rest.
export const stats = (...items: HTMLElement[]) => h("div", { class: "stats", "data-rise": true }, ...items);

// Fades materials to a share of rest opacity, from a share if given.
function fade(group: THREE.Object3D, to: number, duration: number, delay = 0, done?: () => void, from?: number) {
  // Skips keep objects; rest is a material's opacity at its first fade.
  group.traverse((o) => {
    const m = (o as THREE.Mesh).material as THREE.Material | THREE.Material[] | undefined;
    if (!m || o.userData.keep) return;
    for (const one of Array.isArray(m) ? m : [m]) {
      const u = (one as THREE.ShaderMaterial).uniforms;
      const target = (u?.uOpacity ?? one) as unknown as Record<string, number>;
      const key = u?.uOpacity ? "value" : "opacity";
      if (one.userData.rest === undefined) one.userData.rest = target[key];
      gsap.killTweensOf(target, key);
      if (from !== undefined) target[key] = from * one.userData.rest;
      gsap.to(target, { [key]: to * one.userData.rest, duration, delay, ease: "power2.inOut" });
    }
  });
  if (done) gsap.delayedCall(duration + delay, done);
}

// Scratch vector for where and pick, so hovering allocates nothing.
const v = new THREE.Vector3();

// A particle's target now; orbiters (negative size) turn as on the GPU.
function where(f: Formation, i: number, sim: Sim, out = v) {
  out.set(f.x(i), f.y(i), f.z(i));
  if (f.pos[i * 4 + 3] >= 0) return out;
  const a =
    ((sim.u.uCalm.value as number) * (sim.u.uSpin.value as number) * 1.8) / (1 + 0.14 * Math.hypot(out.x, out.z));
  const c = Math.cos(a);
  const s = Math.sin(a);
  return out.set(c * out.x - s * out.z, out.y, s * out.x + c * out.z);
}

// Index in [from, to) nearest a screen point within radius px, or -1.
export function pick(f: Formation, from: number, to: number, x: number, y: number, w: World, radius = 16) {
  let best = -1;
  let bestD = radius * radius;
  const camera = w.stage.camera;
  for (let i = from; i < Math.min(to, N); i++) {
    if (f.pos[i * 4 + 3] === 0 || f.col[i * 4 + 3] < 0.05) continue;
    where(f, i, w.sim).project(camera);
    if (v.z > 1) continue;
    const d = ((v.x * 0.5 + 0.5) * innerWidth - x) ** 2 + ((-v.y * 0.5 + 0.5) * innerHeight - y) ** 2;
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

// Dust's second tint, each grain leaning up to 40% toward it.
const ice = new THREE.Color(C.ice);

// Leftovers as a faint, slowly turning dust disc, so nothing is empty.
export function dust(f: Formation, from: number, seed = 1, radius = 26, thickness = 1.4, alpha = 0.22) {
  const r = seeded(seed);
  const tint = new THREE.Color();
  for (let i = from; i < N; i++) {
    const arm = Math.floor(r() * 2);
    const d = Math.pow(r(), 0.7) * radius + 2;
    const a = arm * Math.PI + d * 0.32 + (r() - 0.5) * 0.9;
    const y = (r() - 0.5) * thickness * (1 + d / radius);
    tint.setHex(C.dust).lerp(ice, r() * 0.4);
    f.put(i, Math.cos(a) * d, y, Math.sin(a) * d, -(0.25 + r() * 0.5), tint, alpha * (0.4 + r() * 0.8));
  }
}

// Soft ball or thin shell for nodes and orbs, returns the next index.
export function ball(
  f: Formation,
  k: number,
  count: number,
  at: THREE.Vector3,
  radius: number,
  size: number,
  color: number | THREE.Color,
  alpha: number,
  r: () => number,
  shell = false,
) {
  for (let j = 0; j < count && k < N; j++, k++) {
    const u = r() * 2 - 1;
    const t = r() * Math.PI * 2;
    const rr = shell ? radius * (1 + (r() - 0.5) * 0.15) : Math.pow(r(), 0.5) * radius;
    const q = Math.sqrt(1 - u * u);
    f.put(k, at.x + rr * q * Math.cos(t), at.y + rr * u, at.z + rr * q * Math.sin(t), size, color, alpha);
  }
  return k;
}
