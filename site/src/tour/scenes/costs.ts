import gsap from "gsap";
import * as THREE from "three";
import { D, num, pct, signed } from "../../shared/data";
import { clamp, seeded } from "../../shared/math";
import { blank } from "../gl/sim";
import { rim } from "../gl/shapes";
import { Body } from "../physics/bodies";
import { h } from "../../shared/dom";
import { corners } from "../layout";
import { box, count, fold, Label, rayAt, slider, stat, swatch } from "../ui";
import { C, dust, header, Scene, stats, type World } from "./scene";

// The cost data the build writes.
const c = D.costs;
// The return a year above cash before costs.
const GROSS = c.gross - c.cash;
// The return a year above cash after costs.
const NET = c.net - c.cash;
// The hurdle a year above cash, its premium.
const HURDLE = c.hurdle - c.cash;
// The column before costs stands this tall in world units.
const TALL = 7;
// World height for each 1% a year of return.
const K = TALL / (GROSS * 100);
// The blocks' width.
const W = 2.6;
// The slider's top multiple of today's costs.
const MOST = 5;
// The name each booked cost goes by in the list and the tooltips.
const NAMES: Record<string, string> = {
  trading: "Fees, spread and impact",
  borrow: "Borrow fees on shorts",
};
// Stacking order up from the net; the list shows it reversed.
const ORDER = ["borrow", "trading"];
// Return above cash a year with costs at k times today's.
const netAt = (k: number) => GROSS - c.total * k;
// How far that return sits above the hurdle, below it when negative.
const edgeAt = (k: number) => netAt(k) - HURDLE;

// Every cost counted: blocks fall from before costs to after, by k.
export class Costs extends Scene {
  name = "Every cost, counted";
  summary = "The cost blocks break away and fall. Push costs up or down to see how they move the return.";
  private net: THREE.Mesh;
  private blocks: { mesh: THREE.Mesh; body: Body; key: string; home: THREE.Vector3 }[] = [];
  private parts = h("div", { class: "flex flex-col gap-1 text-[13px]" });
  private rows = [...ORDER].reverse().map((key) => ({
    key,
    value: h("b", { class: "figure text-ink font-medium" }),
  }));
  private netLabel: Label;
  private hurdle: THREE.Mesh;
  private input: HTMLInputElement;
  private readout = {
    cost: stat("", "Costs a year"),
    edge: stat("", "Above the hurdle"),
    turnover: stat(pct(c.turnover, 0), "Turnover a year"),
  };
  private multiple = h("b", { class: "figure text-[24px] text-ink font-medium" });
  private k = 1;
  private counting: gsap.core.Tween | null = null;

  // Stacks the cost blocks on the gold net, up to the gross return.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [6, 5.5, 17.5], look: [0.8, 3.2, 0], drift: 0.6, shift: 0.17 };
    this.physics = { stiff: 9, damp: 1.2, flow: 0.2, spin: 0.03, mouse: 0.8 };
    this.dwell = 13;
    this.net = new THREE.Mesh(new THREE.BoxGeometry(W, 1, W), rim(C.gold, 0.7, 0.05));
    this.group.add(this.net);
    this.netLabel = this.addLabel(new Label("", [W / 2 + 0.4, 0, 0], "left", "big"));
    let y = NET * 100 * K;
    // Each cost stacks on the last; hits over 2.5 make a tick.
    for (const key of ORDER) {
      const height = c.parts[key]! * 100 * K;
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
    // The hurdle, its premium a year above cash, as a bar at its height.
    this.hurdle = new THREE.Mesh(
      new THREE.BoxGeometry(11, 0.025, 0.025),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(C.ink).multiplyScalar(1.4),
        transparent: true,
        opacity: 0.7,
      }),
    );
    const bar = HURDLE * 100 * K;
    this.hurdle.position.set(-2.4, bar, W / 2 + 0.2);
    this.group.add(this.hurdle);
    // On small screens the hurdle's label breaks clear of the stack.
    const above = `${pct(HURDLE, 0)} a year above cash`;
    this.addLabel(new Label(`Hurdle · ${above}`, [-7.8, bar + 0.4, W / 2 + 0.2], "left")).small = {
      html: `Hurdle<br>${above}`,
      at: new THREE.Vector3(-7.8, bar + 0.75, W / 2 + 0.2),
    };
    this.panel.append(
      ...header(
        "Every cost, <em>counted</em>",
        `Returns above cash, after fees, spread, impact and borrow. Before costs the fund ${GROSS >= HURDLE ? "met" : "fell short of"} the hurdle. Drag to scale every cost.`,
      ),
      stats(...Object.values(this.readout).map((s) => s.el)),
    );
    // One row per block, its name and its cost a year at this multiple.
    for (const { key, value } of this.rows) {
      this.parts.append(
        h(
          "div",
          { class: "flex justify-between gap-3 border-t border-line pt-1" },
          h("span", { class: "text-ink-2", html: `${swatch("var(--m-short)")}${NAMES[key]}` }),
          value,
        ),
      );
    }
    // Dragging scales costs 0× to 5× and finishes the fall at once.
    this.input = slider("cost-multiple", "Costs multiple", 0, MOST, 0.01, 1);
    this.input.addEventListener("input", () => {
      this.timeline?.progress(1);
      this.scale(+this.input.value);
    });
    this.controls.append(
      box(
        "w-[min(420px,calc(100vw-32px))] gap-1",
        h(
          "div",
          { class: "flex items-center justify-between gap-3" },
          h(
            "span",
            { class: "flex items-baseline gap-2" },
            this.multiple,
            h("span", { class: "eyebrow" }, "today's costs"),
          ),
        ),
        this.input,
        h("div", { class: "flex justify-between eyebrow" }, h("span", {}, "0×"), h("span", {}, `${MOST}×`)),
        this.parts,
      ),
    );
    // Small screens: each cost folds away, the slider's ends drop.
    const glass = this.controls.firstElementChild as HTMLElement;
    const head = glass.firstElementChild as HTMLElement;
    head.firstElementChild?.classList.add("whole");
    fold(glass, head, [this.parts], "Each cost");
    this.parts.previousElementSibling?.classList.add("ends");
    this.frame = corners(-7.9, 0, -1.3, 6.6, TALL + 1.4, 1.3);
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
    // Gold dots along the four sides of the stack's square base.
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

  // Scales costs by k and recounts; the net goes orange below the hurdle.
  scale(k: number) {
    this.k = k;
    this.counting?.kill();
    this.input.value = String(k);
    this.input.style.setProperty("--fill", `${(k / MOST) * 100}%`);
    const net = netAt(k);
    const height = Math.max(0.02, net * 100 * K);
    this.net.scale.y = height;
    this.net.position.y = Math.max(0.01, height / 2);
    // Blocks that have fallen grow with the multiple, up to three times.
    for (const b of this.blocks) if (b.body.asleep) b.mesh.scale.setScalar(clamp(0.6 + 0.4 * k, 1, 3));
    this.netLabel.at.set(W / 2 + 0.4, height, 0);
    this.netLabel.set(`${pct(net)} net`);
    this.multiple.textContent = `${num(k, 2)}×`;
    this.readout.cost.value.textContent = pct(c.total * k, 2);
    for (const row of this.rows) row.value.textContent = pct(c.parts[row.key]! * k, 2);
    const edge = edgeAt(k);
    this.readout.edge.value.textContent = signed(Math.abs(edge) < 0.0005 ? 0 : edge);
    (this.net.material as THREE.ShaderMaterial).uniforms.uColor.value.setHex(edge >= 0 ? C.gold : C.orange);
  }

  // Restacks the blocks, then knocks them off top first, 0.55 s apart.
  override enter() {
    this.showLabels();
    // Every block goes back to its place on the stack, at rest.
    for (const b of this.blocks) {
      b.mesh.position.copy(b.home);
      b.mesh.quaternion.identity();
      b.mesh.scale.setScalar(1);
      b.body.asleep = true;
    }
    this.k = 1;
    this.scale(1);
    const state = { v: GROSS };
    this.netLabel.set(`${pct(GROSS)} before costs`);
    this.timeline = gsap.timeline({ delay: 1.6 });
    // Each block is pushed off in turn, alternating left and right.
    [...this.blocks].reverse().forEach((b, i) => {
      this.timeline!.call(
        () => {
          const dir = i % 2 ? 1 : -1;
          b.body.push(
            new THREE.Vector3(1.3 + i * 0.42, 3.2 + i * 0.3, dir * (1.1 + i * 0.35) - 0.8),
            new THREE.Vector3(1.4 * dir, 0.6, -2.4),
          );
          this.w.sim.wave({ at: b.mesh.position.clone(), amp: 0.5, speed: 6 });
        },
        [],
        i * 0.55,
      );
    });
    // Meanwhile the net label counts down from before costs to net.
    this.timeline.to(
      state,
      {
        v: NET,
        duration: this.blocks.length * 0.55,
        ease: "none",
        onUpdate: () => this.netLabel.set(`${pct(state.v)} ${state.v > NET + 0.0001 ? "left" : "net"}`),
      },
      0,
    );
    // Counts to the same figure the slider shows at today's costs.
    this.counting = count(this.readout.cost.value, c.total, (x) => pct(x, 2), 1.4, 1.6);
  }

  // Stops any ease of the multiple on the way out.
  override leave() {
    gsap.killTweensOf(this);
  }

  // The cost block the pointer's ray hits first, if any.
  private blockAt(x: number, y: number) {
    const hit = rayAt(x, y, this.w.stage.camera).intersectObjects(this.blocks.map((b) => b.mesh))[0];
    return hit ? this.blocks.find((b) => b.mesh === hit.object) : undefined;
  }

  // Names the block under the pointer and its cost at this multiple.
  override hover(x: number, y: number) {
    const b = this.blockAt(x, y);
    if (!b) return null;
    return `<strong>${NAMES[b.key]}</strong><br>${pct(c.parts[b.key]! * this.k, 2)} of the fund a year<br><span class="muted">Click to kick it</span>`;
  }

  // Kicks the clicked block up and sideways, finishing the fall first.
  override click(x: number, y: number) {
    const b = this.blockAt(x, y);
    if (!b) return;
    this.timeline?.progress(1);
    const side = Math.random() < 0.5 ? -1 : 1;
    b.body.push(
      new THREE.Vector3(side * 1.5, 6 + Math.random() * 2, (Math.random() - 0.5) * 2),
      new THREE.Vector3(3 * side, 2, -3),
    );
    this.w.sound.tick(0.9, 0.8);
  }

  // Steps every block's physics; resting ones cost nothing.
  override tick(dt: number) {
    for (const b of this.blocks) b.body.step(dt);
  }
}
