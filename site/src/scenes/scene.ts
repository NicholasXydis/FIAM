import gsap from "gsap";
import * as THREE from "three";
import { type Formation, N, type Sim } from "../gl/sim";
import type { Shot, Stage } from "../gl/stage";
import type { Sound } from "../sound";
import { h, type Label } from "../ui";

export const C = {
  purple: 0xa98bff,
  gold: 0xf2c14e,
  cyan: 0x5cc8e0,
  orange: 0xf08a4b,
  ink: 0xede9f6,
  dust: 0x6f63a8,
  dim: 0x3a3360,
  ice: 0x9fb6ff,
};

export interface World {
  stage: Stage;
  sim: Sim;
  layer: HTMLElement;
  sound: Sound;
  go: (i: number) => void;
  next: () => void;
}

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
  active = false;
  protected timeline: gsap.core.Timeline | null = null;

  constructor(protected w: World) {
    this.panel = h("section", { class: "panel" });
    this.controls = h("div", { class: "controls" });
    w.layer.append(this.panel, this.controls);
    this.group.visible = false;
    w.stage.scene.add(this.group);
  }

  abstract formation(): Formation;

  get time() {
    return this.w.sim.u.uTime.value as number;
  }

  addLabel(label: Label) {
    this.labels.push(label);
    this.w.layer.append(label.el);
    return label;
  }

  enter() {}
  leave() {}
  tick(_dt: number, _t: number) {}
  hover(_x: number, _y: number): string | null {
    return null;
  }
  click(_x: number, _y: number) {}
  key(_e: KeyboardEvent) {
    return false;
  }

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

  place(camera: THREE.Camera) {
    for (const l of this.labels) l.place(camera);
  }
}

// Fades every material in a group toward a share of its own resting opacity, from a share if given.
export function fade(group: THREE.Object3D, to: number, duration: number, delay = 0, done?: () => void, from?: number) {
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

const v = new THREE.Vector3();

// Where a particle's target sits now: orbiting targets (negative size) turn as the GPU turns them.
export function where(f: Formation, i: number, sim: Sim, out = v) {
  out.set(f.x(i), f.y(i), f.z(i));
  if (f.pos[i * 4 + 3] >= 0) return out;
  const a =
    ((sim.u.uTime.value as number) * (sim.u.uSpin.value as number) * 1.8) / (1 + 0.14 * Math.hypot(out.x, out.z));
  const c = Math.cos(a);
  const s = Math.sin(a);
  return out.set(c * out.x - s * out.z, out.y, s * out.x + c * out.z);
}

// The particle nearest a screen point among [from, to), within a radius in pixels, or -1.
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

export const rand = (seed: number) => {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

const ice = new THREE.Color(C.ice);

// Leftover particles as a faint, slowly turning disc of dust, so nothing is ever empty.
export function dust(f: Formation, from: number, seed = 1, radius = 26, thickness = 1.4, alpha = 0.22) {
  const r = rand(seed);
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

// A cluster of particles as a soft ball or a thin shell, for nodes and orbs. Returns the next index.
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
