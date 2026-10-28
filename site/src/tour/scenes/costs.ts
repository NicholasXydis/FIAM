import gsap from "gsap";
import * as THREE from "three";
import { D, pct } from "../../shared/data";
import { seeded } from "../../shared/math";
import { blank } from "../gl/sim";
import { rim } from "../gl/shapes";
import { Body } from "../physics/bodies";
import { h } from "../../shared/dom";
import { corners } from "../layout";
import { box, count, rayAt, stat, swatch } from "../ui";
import { C, dust, header, Scene, stats, type World } from "./scene";

// The tower's full height, split by each cost's share, and its width.
const TOWER = 6.4;
const W = 2.6;
// The name each booked cost goes by in the list and the tooltips.
const NAMES: Record<string, string> = {
  trading: "Fees, spread and impact",
  borrow: "Borrow fees on shorts",
};
// Stacking order up from the floor; the list shows it reversed.
const ORDER = ["borrow", "trading"];

// Every cost counted: the booked blocks stack, then break and fall.
export class Costs extends Scene {
  name = "Every cost, counted";
  summary = "Every cost the fund paid, stacked by its share of the total.";
  private blocks: { mesh: THREE.Mesh; body: Body; key: string; home: THREE.Vector3 }[] = [];
  private parts = h("div", { class: "flex flex-col gap-1 text-[13px]" });
  private readout = {
    cost: stat("", "Costs a year"),
    turnover: stat(`${Math.round(D.costs.turnover * 100)}%`, "Turnover a year"),
  };
  private counting: gsap.core.Tween | null = null;

  // Stacks the booked cost blocks from the floor up.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [6, 5.5, 17.5], look: [0.8, 3.2, 0], drift: 0.6, shift: 0.17 };
    this.physics = { stiff: 9, damp: 1.2, flow: 0.2, spin: 0.03, mouse: 0.8 };
    this.dwell = 13;
    const c = D.costs;
    let y = 0;
    // Each cost stacks on the last; hits over 2.5 make a tick.
    for (const key of ORDER) {
      const height = (c.parts[key]! / c.total) * TOWER;
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(W - 0.06, Math.max(0.04, height - 0.05), W - 0.06),
        rim(C.orange, 0.7, 0.05),
      );
      const home = new THREE.Vector3(0, y + height / 2, 0);
      mesh.position.copy(home);
      const body = new Body(mesh, new THREE.Vector3(W - 0.06, Math.max(0.04, height - 0.05), W - 0.06), 0);
      body.onHit = (impact) => impact > 2.5 && this.w.sound.tick(0.45 + Math.random() * 0.2, Math.min(1, impact / 8));
      mesh.userData.key = key;
      this.blocks.push({ mesh, body, key, home });
      this.group.add(mesh);
      y += height;
    }
    this.panel.append(
      ...header(
        "Every cost, <em>counted</em>",
        `Every trade pays fees, spread and market impact, and every short pays borrow. We booked them all, ${pct(c.total, 1)} of the fund a year. Tap a block to see each one.`,
      ),
      stats(...Object.values(this.readout).map((s) => s.el)),
    );
    // One row per block, its name and its booked size a year.
    for (const [i, key] of [...ORDER].reverse().entries()) {
      this.parts.append(
        h(
          "div",
          { class: `flex justify-between gap-3${i ? " border-t border-line pt-1" : ""}` },
          h("span", { class: "text-ink-2", html: `${swatch("var(--m-short)")}${NAMES[key]}` }),
          h("b", { class: "figure text-ink font-medium" }, pct(c.parts[key]!, 2)),
        ),
      );
    }
    this.controls.append(box("w-[min(420px,calc(100vw-32px))] gap-1", this.parts));
    this.frame = corners(-7.9, 0, -1.3, 6.6, 8.8, 1.3);
    this.zoomCap = 1.4;
  }

  // A dusty floor round the stack and gold dots tracing its square base.
  formation() {
    const f = blank();
    const r = seeded(8);
    let k = 0;
    for (let i = 0; i < 2600; i++, k++) {
      const a = r() * Math.PI * 2;
      const d = 3 + Math.pow(r(), 0.6) * 9;
      f.put(k, Math.cos(a) * d, -0.02, Math.sin(a) * d, 0.2 + r() * 0.15, C.dust, 0.3 * (1 - d / 13));
    }
    for (let i = 0; i < 900; i++, k++) {
      const t = r();
      const side = Math.floor(r() * 4);
      const along = (t - 0.5) * W;
      const x = side < 2 ? along : (side === 2 ? -1 : 1) * W * 0.5;
      const z = side >= 2 ? along : (side === 0 ? -1 : 1) * W * 0.5;
      f.put(k, x, 0.01, z, 0.24, C.gold, 0.6);
    }
    dust(f, k, 19, 34, 1.6, 0.12);
    return f;
  }

  // Drops the blocks onto the stack one by one, where they stay.
  override enter() {
    this.showLabels();
    this.counting?.kill();
    this.timeline = gsap.timeline({ delay: 0.6 });
    for (const [i, b] of this.blocks.entries()) {
      b.mesh.quaternion.identity();
      b.mesh.scale.setScalar(1);
      b.body.asleep = true;
      b.mesh.position.set(b.home.x, b.home.y + 5 + i * 1.5, b.home.z);
      this.timeline.to(b.mesh.position, { y: b.home.y, duration: 0.9, ease: "bounce.out" }, i * 0.45);
    }
    // Counts the booked costs a year up as the blocks land.
    this.counting = count(this.readout.cost.value, D.costs.total, (x) => pct(x, 2), 1.4, 1.6);
  }

  // The cost block the pointer's ray hits first, if any.
  private blockAt(x: number, y: number) {
    const hit = rayAt(x, y, this.w.stage.camera).intersectObjects(this.blocks.map((b) => b.mesh))[0];
    return hit ? this.blocks.find((b) => b.mesh === hit.object) : undefined;
  }

  // Names the block under the pointer and its booked cost.
  override hover(x: number, y: number) {
    const b = this.blockAt(x, y);
    if (!b) return null;
    return `<strong>${NAMES[b.key]}</strong><br>${pct(D.costs.parts[b.key]!, 2)} of the fund a year`;
  }

  // Nudges the tapped block up and back down, the stack stays whole.
  override click(x: number, y: number) {
    const b = this.blockAt(x, y);
    if (!b) return;
    this.timeline?.progress(1);
    gsap.fromTo(b.mesh.position, { y: b.home.y + 0.35 }, { y: b.home.y, duration: 0.5, ease: "bounce.out" });
    this.w.sound.tick(0.9, 0.5);
  }

  // Steps every block's physics; resting ones cost nothing.
  override tick(dt: number) {
    for (const b of this.blocks) b.body.step(dt);
  }
}
