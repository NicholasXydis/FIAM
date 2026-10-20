import gsap from "gsap";
import * as THREE from "three";
import { D, num, pct, signed } from "../../shared/data";
import { clamp, mix, seeded } from "../../shared/math";
import { blank } from "../gl/sim";
import { rim } from "../gl/shapes";
import { Body } from "../physics/bodies";
import { h } from "../../shared/dom";
import { corners } from "../layout";
import { box, chip, count, fold, Label, rayAt, slider, stat, swatch } from "../ui";
import { C, dust, header, Scene, stats, type World } from "./scene";

// World height per percent of the fund a year, and the blocks' width.
const K = 0.6;
const W = 2.6;
// The name each cost goes by in the list and the tooltips.
const NAMES: Record<string, string> = {
  commission: "Commissions and fees",
  spread: "Bid-ask spread",
  impact: "Market impact",
  borrow: "Borrow fees on shorts",
  financing: "Financing",
};
// Stacking order up from the net; the list shows it reversed.
const ORDER = ["financing", "borrow", "impact", "spread", "commission"];
// The pack's ladder of cost, edge over hurdle and IR by cost multiple.
const LADDER = D.costs.ladder;

// Ladder at multiple k: cost, edge or IR, linear in k between rungs.
const ladder = (k: number, key: "cost" | "active") => {
  for (let i = 1; i < LADDER.length; i++) {
    if (k <= LADDER[i].multiple || i === LADDER.length - 1) {
      const a = LADDER[i - 1];
      const b = LADDER[i];
      return mix(a[key], b[key], (k - a.multiple) / (b.multiple - a.multiple));
    }
  }
  return LADDER[0][key];
};

// What trading costs: five blocks fall from gross to net, scaled by k.
export class Costs extends Scene {
  name = "What trading costs";
  summary = "Five cost blocks break away and fall. Push costs up until the edge is gone.";
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
    even: stat(`${num(D.costs.break_even_multiple, 1)}×`, "Break-even costs"),
  };
  private multiple = h("b", { class: "figure text-[24px] text-ink font-medium" });
  private k = 1;
  private counting: gsap.core.Tween | null = null;

  // Stacks the five cost blocks on the gold net, up to gross.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [6, 5.5, 17.5], look: [0.8, 3.2, 0], drift: 0.6, shift: 0.17 };
    this.physics = { stiff: 9, damp: 1.2, flow: 0.2, spin: 0.03, mouse: 0.8 };
    this.dwell = 13;
    const c = D.costs;
    this.net = new THREE.Mesh(new THREE.BoxGeometry(W, 1, W), rim(C.gold, 0.7, 0.05));
    this.group.add(this.net);
    this.netLabel = this.addLabel(new Label("", [W / 2 + 0.4, 0, 0], "left", "big"));
    let y = c.net * 100 * K;
    // Each cost stacks on the last; hits over 2.5 make a tick.
    for (const key of ORDER) {
      const height = c.parts[key] * 100 * K;
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
    // The hurdle, 4% a year above cash, as a bar at its height.
    this.hurdle = new THREE.Mesh(
      new THREE.BoxGeometry(11, 0.025, 0.025),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(C.ink).multiplyScalar(1.4),
        transparent: true,
        opacity: 0.7,
      }),
    );
    this.hurdle.position.set(-2.4, 4 * K, W / 2 + 0.2);
    this.group.add(this.hurdle);
    // On small screens the hurdle's label breaks clear of the stack.
    this.addLabel(new Label("Hurdle · 4% a year above cash", [-7.8, 4 * K + 0.4, W / 2 + 0.2], "left")).small = {
      html: "Hurdle<br>4% a year above cash",
      at: new THREE.Vector3(-7.8, 4 * K + 0.75, W / 2 + 0.2),
    };
    this.panel.append(
      ...header(
        `${pct(c.gross)} gross, <em>${pct(c.net)} net</em>`,
        "Commissions, half the real spread, market impact, borrow fees and financing. Drag the slider to see how far costs can rise before the edge is gone.",
      ),
      stats(...Object.values(this.readout).map((s) => s.el)),
    );
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
    // Dragging scales costs 1× to 5× and finishes the fall at once.
    this.input = slider("cost-multiple", "Costs multiple", 1, 5, 0.01, 1);
    this.input.addEventListener("input", () => {
      this.timeline?.progress(1);
      this.scale(+this.input.value);
    });
    // Eases the multiple to break-even, where the edge is gone.
    const even = chip("Show break-even", () =>
      gsap.to(this, {
        k: c.break_even_multiple,
        duration: 1.2,
        ease: "power2.inOut",
        onUpdate: () => this.scale(this.k),
      }),
    );
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
          even,
        ),
        this.input,
        h("div", { class: "flex justify-between eyebrow" }, h("span", {}, "1×"), h("span", {}, "5×")),
        this.parts,
      ),
    );
    // Small screens: each cost folds away, the 1× to 5× ends drop.
    const glass = this.controls.firstElementChild as HTMLElement;
    const head = glass.firstElementChild as HTMLElement;
    head.firstElementChild?.classList.add("whole");
    fold(glass, head, [this.parts], "Each cost");
    this.parts.previousElementSibling?.classList.add("ends");
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

  // Scales costs by k and recounts; the net goes orange when edge < 0.
  scale(k: number) {
    this.k = k;
    this.counting?.kill();
    const c = D.costs;
    this.input.value = String(k);
    this.input.style.setProperty("--fill", `${((k - 1) / 4) * 100}%`);
    const net = c.gross - c.total * k;
    const height = Math.max(0.02, net * 100 * K);
    this.net.scale.y = height;
    this.net.position.y = Math.max(0.01, height / 2);
    for (const b of this.blocks) if (b.body.asleep) b.mesh.scale.setScalar(clamp(0.6 + 0.4 * k, 1, 3));
    this.netLabel.at.set(W / 2 + 0.4, height, 0);
    this.netLabel.set(`${pct(net)} net`);
    this.multiple.textContent = `${num(k, 2)}×`;
    this.readout.cost.value.textContent = pct(ladder(k, "cost"), 2);
    for (const row of this.rows) row.value.textContent = pct(c.parts[row.key] * k, 2);
    const edge = ladder(k, "active");
    this.readout.edge.value.textContent = signed(Math.abs(edge) < 0.0005 ? 0 : edge);
    (this.net.material as THREE.ShaderMaterial).uniforms.uColor.value.setHex(edge >= 0 ? C.gold : C.orange);
  }

  // Restacks the blocks, then knocks them off top first, 0.55 s apart.
  override enter() {
    this.showLabels();
    for (const b of this.blocks) {
      b.mesh.position.copy(b.home);
      b.mesh.quaternion.identity();
      b.mesh.scale.setScalar(1);
      b.body.asleep = true;
    }
    this.k = 1;
    this.scale(1);
    const c = D.costs;
    const state = { v: c.gross };
    this.netLabel.set(`${pct(c.gross)} gross`);
    this.timeline = gsap.timeline({ delay: 1.6 });
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
    // Meanwhile the net label counts down from gross to net.
    this.timeline.to(
      state,
      {
        v: c.net,
        duration: this.blocks.length * 0.55,
        ease: "none",
        onUpdate: () => this.netLabel.set(`${pct(state.v)} ${state.v > c.net + 0.0001 ? "left" : "net"}`),
      },
      0,
    );
    // Counts to the same figure the slider shows at today's costs.
    this.counting = count(this.readout.cost.value, ladder(1, "cost"), (x) => pct(x, 2), 1.4, 1.6);
  }

  // Stops any break-even ease of the multiple on the way out.
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
    return `<strong>${NAMES[b.key]}</strong><br>${pct(D.costs.parts[b.key] * this.k, 2)} of the fund a year<br><span class="muted">Click to kick it</span>`;
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
