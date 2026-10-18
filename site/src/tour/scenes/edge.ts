import gsap from "gsap";
import * as THREE from "three";
import { D, int, num } from "../../shared/data";
import { blank } from "../gl/sim";
import { glow } from "../gl/shapes";
import { Pile } from "../physics/pile";
import { h } from "../../shared/dom";
import { chip, count, Label, rayAt } from "../ui";
import { C, dust, header, Scene, type World } from "./scene";
import { seeded } from "../../shared/math";

// Edge data, the IR axis from -3.8 to 1.5 over 19 units, 0.05 IR bins.
const E = D.edge;
const LO = -3.8;
const HI = 1.5;
const SPAN = 19;
const BIN = 0.05;
// IR to x, a ball's diameter, the final book's index, and bar colours.
const X = (ir: number) => -SPAN / 2 + ((ir - LO) / (HI - LO)) * SPAN;
const DIAM = (BIN / (HI - LO)) * SPAN;
const OURS = E.irs.length;
const COLOR: Record<string, string> = {
  null: "var(--ink-3)",
  alt: "var(--m-brand)",
  live: "var(--m-long)",
  ours: "var(--m-ours)",
};

// Benchmark bars on one IR axis, -2.4 to 1.2, zero marked, all from 0.
function ladder() {
  const lo = -2.4;
  const hi = 1.2;
  const at = (v: number) => ((v - lo) / (hi - lo)) * 100;
  return h(
    "div",
    { class: "glass rounded-2xl px-4 py-3 w-[min(420px,calc(100vw-32px))] flex flex-col gap-2" },
    h("p", { class: "eyebrow" }, "Every benchmark · same money · IR"),
    ...E.ladder.map((row) => {
      const a = at(Math.min(0, row.ir));
      const b = at(Math.max(0, row.ir));
      return h(
        "div",
        { class: "bar-row" },
        h("span", { class: row.kind === "ours" ? "text-ink" : "" }, row.label),
        h("b", { class: "figure text-right text-ink font-medium" }, num(row.ir)),
        h(
          "div",
          { class: "track" },
          h("i", { style: `left:${at(0) - 0.25}%;width:0.5%;background:rgb(237 233 246 / .35)` }),
          h("i", { "data-bar": true, style: `left:${a}%;width:${b - a}%;background:${COLOR[row.kind]}` }),
        ),
      );
    }),
  );
}

// Is it luck: a thousand random books pile up and ours lands alone.
export class Edge extends Scene {
  name = "Is it luck?";
  summary = `${int(E.draws)} random books fall into a pile. The final book lands alone.`;
  private pile: Pile;
  private clock = 0;
  private ours: Label;
  private best: Label;
  private flash: THREE.Mesh<THREE.PlaneGeometry, THREE.ShaderMaterial>;
  private beaten = h("b", { class: "figure" }, "0");
  private bars = ladder();

  // Rests each ball by its IR bin, random ones from 0.6 s, ours at 5.4 s.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [1.2, 3.2, 18.5], look: [0.6, 0.5, 0], drift: 0.5, shift: 0.12 };
    this.physics = { stiff: 9, damp: 1.25, flow: 0.18, spin: 0.02, mouse: 0.7 };
    this.dwell = 13;
    const r = seeded(42);
    const starts = E.irs.map((_, i) => 0.6 + (i / E.irs.length) * 3.6 + r() * 0.25);
    const heights = new Map<string, number>();
    const rests = new Array<THREE.Vector3>(E.irs.length);
    // In drop order, each ball sits atop its bin in one of two rows.
    for (const i of E.irs.map((_, i) => i).sort((a, b) => starts[a] - starts[b])) {
      const column = Math.floor(E.irs[i] / BIN);
      const row = i % 2;
      const key = `${column}:${row}`;
      const level = heights.get(key) ?? 0;
      heights.set(key, level + 1);
      rests[i] = new THREE.Vector3(
        X((column + 0.5) * BIN),
        DIAM / 2 + level * DIAM * 0.98,
        row ? DIAM * 0.5 : -DIAM * 0.5,
      );
    }
    const ice = new THREE.Color(C.ice);
    const lilac = new THREE.Color(C.purple);
    const colors = E.irs.map(() =>
      ice
        .clone()
        .lerp(lilac, r() * 0.7)
        .multiplyScalar(0.9),
    );
    // The final book, last and gold, is a bigger ball of radius 0.42.
    rests.push(new THREE.Vector3(X(E.final), 0.42, 0));
    starts.push(5.4);
    colors.push(new THREE.Color(C.gold).multiplyScalar(1.6));
    const radii = [...E.irs.map(() => DIAM * 0.49), 0.42];
    this.pile = new Pile(rests, radii, starts, colors);
    this.pile.onLand = (i) => {
      if (i === OURS) this.landed();
      else this.w.sound.tick(1.4 + Math.random() * 0.8, 0.12);
    };
    this.flash = glow(C.gold, 7, 0);
    this.flash.userData.keep = true;
    this.flash.position.copy(rests[OURS]);
    this.group.add(this.pile.mesh, this.flash);
    for (const v of [-3, -2, -1, 0, 1]) {
      this.addLabel(new Label(v === 0 ? "0 · the hurdle" : num(v, 0), [X(v), -0.55, 1.2], "center"));
    }
    this.ours = this.addLabel(
      new Label(`Final book <b class="text-gold">${num(E.final)}</b>`, [X(E.final), 1.9, 0], "center", "big"),
    );
    this.best = this.addLabel(new Label(`Best random book ${num(E.best)}`, [X(E.best), 2.4, 0], "center"));
    this.panel.append(
      ...header(
        `Is it luck? · ${int(E.draws)} random books`,
        `${int(E.draws)} random books. <em>None comes close.</em>`,
        `Random long-short books from the 500 largest stocks, each with our number of positions, our gross, our holding time and our costs. They average an IR of ${num(E.mean)} and the best reaches ${num(E.best)}. The final book makes ${num(E.final)}. Hover a ball for its book, or click one to make it jump.`,
      ),
      h(
        "p",
        { class: "headline text-[30px]", "data-rise": true },
        this.beaten,
        h("span", { class: "text-ink-3" }, ` of ${int(E.draws)} beaten`),
      ),
    );
    this.controls.append(
      this.bars,
      chip("Drop them again", () => this.drop()),
    );
  }

  // The IR axis with ticks, a cyan post at zero and a dusty floor.
  formation() {
    const f = blank();
    let k = 0;
    const r = seeded(77);
    for (let i = 0; i <= 380; i++, k++) f.put(k, -SPAN / 2 + (i / 380) * SPAN, 0, 1.2, 0.2, C.ink, 0.5);
    for (const v of [-3, -2, -1, 0, 1]) {
      for (let j = 0; j < 14; j++, k++) f.put(k, X(v), -0.05 - j * 0.02, 1.2, 0.2, C.ink, 0.6);
    }
    for (let j = 0; j < 160; j++, k++) f.put(k, X(0), j * 0.05, 0, 0.18, C.cyan, 0.45);
    for (let i = 0; i < 3000; i++, k++) {
      const z = (r() - 0.5) * 9;
      f.put(k, (r() - 0.5) * SPAN * 1.3, -0.06, z, 0.18 + r() * 0.12, C.dust, 0.28 * (1 - Math.abs(z) / 5));
    }
    dust(f, k, 23, 36, 1.4, 0.12);
    return f;
  }

  // Flashes and ripples where ours lands, and counts up the beaten.
  landed() {
    this.w.sim.wave({ at: new THREE.Vector3(X(E.final), 0.4, 0), amp: 2, speed: 9 });
    this.w.sound.tick(0.5, 1);
    gsap.fromTo(this.flash.scale, { x: 0.3, y: 0.3 }, { x: 1.4, y: 1.4, duration: 1.2, ease: "expo.out" });
    gsap.fromTo(this.flash.material.uniforms.uOpacity, { value: 1.4 }, { value: 0.3, duration: 2, ease: "power2.out" });
    this.ours.shown = true;
    this.best.shown = true;
    count(this.beaten, E.beaten, int, 1.4);
  }

  // Lifts every ball back into the sky and lets them fall again.
  drop() {
    this.clock = 0;
    this.pile.reset();
    this.beaten.textContent = "0";
    this.ours.hide();
    this.best.hide();
    this.flash.material.uniforms.uOpacity.value = 0;
  }

  // Drops the pile and fills the benchmark bars.
  override enter() {
    this.drop();
    for (const l of this.labels) l.shown = l !== this.ours && l !== this.best;
    const bars = this.bars.querySelectorAll<HTMLElement>("[data-bar]");
    gsap.fromTo(
      bars,
      { scaleX: 0 },
      { scaleX: 1, transformOrigin: "left center", duration: 1, stagger: 0.12, delay: 0.8, ease: "expo.out" },
    );
  }

  // Steps the falling balls on the scene's own clock, reset at each drop.
  override tick(dt: number) {
    this.clock += dt;
    this.pile.step(dt, this.clock);
  }

  // Index of the ball the pointer's ray hits, or -1.
  private ballAt(x: number, y: number) {
    return rayAt(x, y, this.w.stage.camera).intersectObject(this.pile.mesh)[0]?.instanceId ?? -1;
  }

  // Names the ball under the pointer.
  override hover(x: number, y: number) {
    const i = this.ballAt(x, y);
    if (i < 0) return null;
    if (i === OURS)
      return `<strong>Final book</strong><br>Information ratio <strong>${num(E.final)}</strong> after costs`;
    return `<strong>Random book ${i + 1}</strong><br>Information ratio <strong>${num(E.irs[i])}</strong> after costs`;
  }

  // Bounces the clicked ball, the final book higher.
  override click(x: number, y: number) {
    const i = this.ballAt(x, y);
    if (i < 0) return;
    this.pile.bounce(i, i === OURS ? 9 : 6);
    this.w.sound.tick(i === OURS ? 0.7 : 1.6, 0.6);
  }
}
