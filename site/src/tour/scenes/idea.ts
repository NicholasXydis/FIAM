import gsap from "gsap";
import * as THREE from "three";
import { D, int } from "../../shared/data";
import { blank } from "../gl/sim";
import { streams } from "../gl/shapes";
import { h } from "../../shared/dom";
import { corners } from "../layout";
import { box, chip, count, Label, nearest, stat } from "../ui";
import { ball, C, dust, header, Scene, stats, type World } from "./scene";
import { GOLDEN, seeded } from "../../shared/math";

// An orb's colour: gold for our signals, cyan for the organisers'.
const hue = (i: number) => (D.signals[i]!.family === "ours" ? C.gold : C.cyan);
// How many signals feed the two LASSO models.
const INPUTS = D.signals.reduce((n, s) => n + s.count, 0);
// How many of those signals are the organisers' characteristics.
const THEIRS = D.signals.reduce((n, s) => n + (s.family === "ours" ? 0 : s.count), 0);
// The journey's counts for the chosen month.
const J = D.journey;
// Dots per input orb.
const ORB = 220;
// The height of the arc of input orbs.
const ARC_Y = 5.4;
// The funnel's steps: second of the replay, caption and chip.
const STEPS = [
  { at: 0, caption: `${int(J.stocks)} US stocks`, chip: "All stocks" },
  { at: 1.9, caption: `${int(J.tradeable)} we can trade`, chip: "Tradeable" },
  { at: 3.7, caption: `${INPUTS} signals and a LightGBM forecast`, chip: "Scored" },
  { at: 5.4, caption: "Ranked, worst to best", chip: "Ranked" },
  { at: 7.3, caption: `${J.longs} long, ${J.shorts} short`, chip: "Chosen" },
  { at: 9.4, caption: "Beta near zero", chip: "Balanced" },
];

// The signals: how a real month's stocks become longs and shorts.
export class Idea extends Scene {
  name = `${INPUTS} signals, one ranking`;
  summary = `How ${int(J.tradeable)} stocks become ${J.longs + J.shorts} positions in one real month of the final book.`;
  private step = 0;
  private orbs: THREE.Vector3[] = [];
  private order: Int32Array;
  private seed: Float32Array;
  private flow: THREE.Points<THREE.BufferGeometry, THREE.ShaderMaterial>;
  private stats = {
    stocks: stat("", `US stocks in ${J.month}`),
    tradeable: stat("", "Big enough to trade"),
    longs: stat("", "Held long"),
    shorts: stat("", "Held short"),
  };
  private caption = h("p", { class: "headline text-[28px] text-ink min-h-[1.2em]" });
  private chips: HTMLButtonElement[];
  private beam: THREE.Mesh<THREE.BoxGeometry, THREE.MeshBasicMaterial>;

  // Lines the orbs up by family on a shallow arc, with flows down.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 1.6, 24], look: [0, 1.2, 0], drift: 0.7, shift: 0.07 };
    this.physics = { stiff: 8, damp: 1.2, flow: 0.3, spin: 0.03, mouse: 1 };
    this.stagger = 0.9;
    this.dwell = 13;
    // Orbs 1.45 apart, 0.65 more between families, each family labelled.
    const xs: number[] = [];
    let x = 0;
    // Each family's orbs in a row, then a gap and its label.
    for (const fam of Object.keys(D.families)) {
      const members = D.signals.filter((s) => s.family === fam);
      const from = xs.length;
      members.forEach(() => xs.push((x += 1.45)));
      const mid = (xs[from] + xs[xs.length - 1]) / 2;
      this.addLabel(new Label(D.families[fam], [mid, ARC_Y + 1.25, 0], "center")).el.classList.add("text-ink");
      x += 0.65;
    }
    const centre = (xs[0] + xs[xs.length - 1]) / 2;
    for (const l of this.labels) l.at.x -= centre;
    this.orbs = xs.map(
      (v, i) => new THREE.Vector3(v - centre, ARC_Y - Math.cos(((i + 0.5) / xs.length - 0.5) * Math.PI) * 0.2, 0),
    );
    // A seeded shuffle ranks the stocks; each gets four random numbers.
    const r = seeded(21);
    this.order = new Int32Array(J.stocks);
    Array.from({ length: J.stocks }, (_, i) => i)
      .sort(() => r() - 0.5)
      .forEach((v, i) => (this.order[v] = i));
    this.seed = new Float32Array(J.stocks * 4).map(() => r());
    // Each orb streams 70 dots down to the stocks, gold if it is ours.
    this.flow = streams(
      this.orbs.map((o, i) => ({
        a: o,
        b: new THREE.Vector3(o.x * 0.25, -0.6, 0),
        c: new THREE.Vector3(o.x * 0.75, 1.6, 1.2),
        color: hue(i),
        count: 70,
      })),
      0.16,
    );
    this.group.add(this.flow);
    // The gold beam that shows the balanced book at the last step.
    this.beam = new THREE.Mesh(
      new THREE.BoxGeometry(14, 0.05, 0.05),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(C.gold).multiplyScalar(2.2),
        transparent: true,
        opacity: 0,
      }),
    );
    this.beam.position.set(0, 1.0, 0);
    this.beam.userData.keep = true;
    this.group.add(this.beam);
    this.panel.append(
      ...header(
        `${INPUTS} signals, <em>one ranking</em>`,
        `The organisers' ${THEIRS} characteristics and ${INPUTS - THEIRS} of ours, one a LightGBM earnings forecast, feed two LASSO models. E-LASSO blends them into one ranking.`,
      ),
      stats(...Object.values(this.stats).map((s) => s.el)),
    );
    this.chips = STEPS.map((s, i) => chip(`${i + 1} ${s.chip}`, () => this.jump(i), false));
    this.controls.append(
      box(
        "w-[min(440px,calc(100vw-32px))] gap-3",
        h(
          "div",
          { class: "flex items-center justify-between gap-4" },
          this.caption,
          chip("Replay", () => this.play()),
        ),
        h("div", { class: "flex flex-wrap gap-1.5" }, ...this.chips),
      ),
    );
    // Small screens fit the arc, the step chips scroll in one row.
    this.chips[0].parentElement!.classList.add("row");
    this.frame = corners(-10, -3.4, 0, 10, 6.4, 0);
    this.zoomCap = 1.2;
  }

  // The particles at the current funnel step.
  formation() {
    return this.build(this.step);
  }

  // Step 0 cloud, 1 tradeable kept, 2 scored, 3 ranked, 4 longs, shorts.
  build(step: number) {
    const f = blank();
    const tint = new THREE.Color();
    const lo = new THREE.Color(C.orange);
    const mid = new THREE.Color(C.dim);
    const hi = new THREE.Color(C.cyan);
    const tradeable = J.tradeable;
    // Place each stock for the step, from the cloud to the book.
    for (let i = 0; i < J.stocks; i++) {
      const s = this.seed.subarray(i * 4, i * 4 + 4);
      const a = s[0] * Math.PI * 2;
      const rad = Math.sqrt(s[1]);
      let x = Math.cos(a) * rad * 9.5;
      let y = Math.sin(a) * rad * 3.2 - 0.2;
      let z = (s[2] - 0.5) * 5;
      const rank = this.order[i];
      const kept = rank < tradeable;
      const score = kept ? rank / (tradeable - 1) : 0.5;
      let size = 0.34;
      let alpha = 0.7;
      tint.set(C.ice);
      // Step 1 fades the untradeable and pushes them out and back.
      if (step >= 1 && !kept) {
        alpha = 0.08;
        x *= 1.35;
        z -= 4;
      }
      // Step 2 colours each kept stock orange to cyan by its score.
      if (step >= 2 && kept) {
        if (score < 0.5) tint.copy(lo).lerp(mid, score * 2);
        else tint.copy(mid).lerp(hi, score * 2 - 1);
      }
      // Step 3 lines the kept stocks up worst to best along x.
      if (step >= 3 && kept) {
        x = -9 + score * 18;
        y = -0.6 + (s[3] - 0.5) * 0.7;
        z = (s[2] - 0.5) * 1.4;
      }
      // Step 4 spirals the longs right and the shorts left, dims the rest.
      if (step >= 4 && kept) {
        const long = rank >= tradeable - J.longs;
        const short = rank < J.shorts;
        // Longs and shorts gather in two golden spirals.
        if (long || short) {
          const k = long ? tradeable - 1 - rank : rank;
          const d = 0.2 * Math.sqrt(k + 0.5);
          x = (long ? 5.6 : -5.6) + Math.cos(k * GOLDEN) * d;
          y = 2.6 + Math.sin(k * GOLDEN) * d * 0.55;
          z = Math.sin(k * GOLDEN) * d * 0.4;
          tint.setHex(long ? C.cyan : C.orange);
          size = 0.6;
          alpha = 1.3;
        } else alpha = 0.18;
      }
      f.put(i, x, y, z, size, tint, alpha);
    }
    // The input orbs, lit once the stocks are scored.
    let k = J.stocks;
    const r = seeded(5);
    const on = step >= 2 ? 1 : 0.35;
    // Draw each input orb as a cluster of soft balls.
    this.orbs.forEach((o, i) => {
      const accent = hue(i);
      // Five balls per orb, the first in the orb's accent colour.
      for (let j = 0; j < 5; j++)
        k = ball(f, k, ORB / 5, o, 0.42, 0.3 + r() * 0.25, j === 0 ? accent : C.purple, on * (0.6 + r() * 0.6), r);
    });
    dust(f, k, 9, 34, 1.4, 0.13);
    return f;
  }

  // Shows step n: particles, caption, counts, flows and beam.
  set(step: number, move = true) {
    this.step = step;
    if (move) this.w.sim.show(this.build(step), 0.8, 1.1);
    gsap.fromTo(this.caption, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.5 });
    this.caption.textContent = STEPS[step].caption;
    this.chips.forEach((c, i) => c.setAttribute("aria-pressed", String(i === step)));
    if (step === 0) count(this.stats.stocks.value, J.stocks, int, 1.2);
    if (step === 1) count(this.stats.tradeable.value, J.tradeable, int, 1.2);
    // The longs and shorts count up together at step 4.
    if (step === 4) {
      count(this.stats.longs.value, J.longs, int, 1.2);
      count(this.stats.shorts.value, J.shorts, int, 1.2);
    }
    gsap.to(this.flow.material.uniforms.uOpacity, {
      value: step >= 2 && step < 4 ? 1 : step >= 4 ? 0.25 : 0,
      duration: 0.8,
    });
    gsap.to(this.beam.material, { opacity: step >= 5 ? 1 : 0, duration: 0.8 });
    gsap.to(this.beam.scale, { x: step >= 5 ? 1 : 0.01, duration: 1.2, ease: "expo.out" });
    if (step > 0) this.w.sound.tick(0.8 + step * 0.1, 0.7);
  }

  // Plays every step; when fresh the first keeps the particles in place.
  play(fresh = false) {
    this.timeline?.kill();
    for (const s of Object.values(this.stats)) s.value.textContent = "0";
    this.timeline = gsap.timeline();
    STEPS.forEach((s, i) => this.timeline!.call(() => this.set(i, i > 0 || !fresh), [], s.at));
  }

  // Goes straight to one step, with the counts it has reached.
  jump(step: number) {
    this.timeline?.kill();
    this.timeline = null;
    this.stats.stocks.value.textContent = int(J.stocks);
    this.stats.tradeable.value.textContent = step >= 1 ? int(J.tradeable) : "0";
    this.stats.longs.value.textContent = step >= 4 ? int(J.longs) : "0";
    this.stats.shorts.value.textContent = step >= 4 ? int(J.shorts) : "0";
    this.set(step);
  }

  // Starts the funnel from the top.
  override enter() {
    this.showLabels();
    this.flow.material.uniforms.uOpacity.value = 0;
    this.beam.scale.x = 0.01;
    this.play(true);
  }

  // Rewinds the funnel on the way out.
  override leave() {
    this.step = 0;
  }

  // Names the input under the pointer and lights its flow.
  override hover(x: number, y: number) {
    const i = nearest(this.orbs, x, y, this.w.stage.camera, 30);
    this.flow.material.uniforms.uFocus.value = i;
    if (i < 0) return null;
    const s = D.signals[i];
    const feeds = s.count > 1 ? "Each feeds" : "It feeds";
    // The earnings forecast names the model that makes it.
    const made =
      s.family === "ours" && /earnings/i.test(s.label) ? "A LightGBM model, refit once a year, forecasts it. " : "";
    return `<strong>${s.label}</strong><br><span class="muted">${D.families[s.family]}</span><br>${made}${feeds} the two LASSO models, refit each month on past data only.`;
  }

  // Moves the flow along its threads and sizes its dots to the screen.
  override tick(_dt: number, t: number) {
    this.flow.material.uniforms.uTime.value = t;
    this.flow.material.uniforms.uScale.value = this.w.stage.pixel;
  }
}
