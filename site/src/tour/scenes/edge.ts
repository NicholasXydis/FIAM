import gsap from "gsap";
import * as THREE from "three";
import { D, pct, signed } from "../../shared/data";
import { blank } from "../gl/sim";
import { glow } from "../gl/shapes";
import { Pile } from "../physics/pile";
import { h } from "../../shared/dom";
import { corners } from "../layout";
import { asButton, box, fold, Label, rayAt, slider, stat } from "../ui";
import { C, dust, header, Scene, stats, type World } from "./scene";
import { seeded } from "../../shared/math";

// 2022's returns, the 60/40 steps, and a return axis of -25% to +25%.
const E = D.edge;
const Y = E.year_2022;
const STEPS = E.steps;
const LO = -0.25;
const HI = 0.25;
const SPAN = 19;
// The axis' marked returns, from -20% up to zero.
const TICKS = [-0.2, -0.15, -0.1, -0.05, 0];
// A return to x, and the four balls, the fund last and gold.
const X = (v: number) => -SPAN / 2 + ((v - LO) / (HI - LO)) * SPAN;
const ROWS = [
  { label: "S&P 500", value: Y.sp500, kind: "alt", color: C.purple },
  { label: "Bonds (AGG)", value: Y.bonds, kind: "alt", color: C.cyan },
  { label: "60/40", value: Y.sixty_forty, kind: "alt", color: C.ice },
  { label: "Our fund", value: Y.fund, kind: "ours", color: C.gold },
];
const OURS = ROWS.length - 1;
// SE-size screens: too small for ball labels, a 2x2 grid lists them.
const tiny = () => Math.min(innerWidth, innerHeight) < 400 && Math.max(innerWidth, innerHeight) < 700;
// Each ball's label height, so the three close together never overlap.
const LIFT = [1.4, 2.6, 2.0, 1.9];
const COLOR: Record<string, string> = {
  alt: "var(--m-brand)",
  ours: "var(--m-ours)",
};
// The bars' span, and where zero sits across it.
const BAR_LO = -0.25;
const BAR_HI = 0.05;
const at = (v: number) => ((v - BAR_LO) / (BAR_HI - BAR_LO)) * 100;

// The 2022 bars: one per row, each from the zero line.
function bars(point: (row: number) => void) {
  const zero = `position:absolute;top:0;bottom:0;left:${at(0)}%;width:1px;background:rgb(237 233 246 / .28)`;
  const rows = ROWS.map((row, i) => {
    const a = at(Math.min(0, row.value));
    const b = at(Math.max(0, row.value));
    const el = h(
      "div",
      { class: "bar-row", "aria-label": `${row.label}, 2022 ${signed(row.value)}` },
      h("span", { class: row.kind === "ours" ? "text-ink" : "" }, row.label),
      h("b", { class: "figure text-right text-ink font-medium" }, signed(row.value)),
      h(
        "div",
        { class: "track" },
        h("i", {
          "data-bar": true,
          "data-side": row.value < 0 ? "left" : "right",
          style: `left:${a}%;width:${b - a}%;background:${COLOR[row.kind]}`,
        }),
      ),
    );
    // Hover or focus marks a row's ball; leaving clears it.
    el.addEventListener("pointerenter", () => point(i));
    el.addEventListener("pointerleave", () => point(-1));
    el.addEventListener("focus", () => point(i));
    el.addEventListener("blur", () => point(-1));
    return asButton(el, () => point(i));
  });
  return h(
    "div",
    { class: "flex flex-col gap-2" },
    h(
      "div",
      { class: "flex justify-between eyebrow", style: "position:relative" },
      h("span", {}, "2022 · return"),
      h("span", { style: `position:absolute;left:${at(0)}%;transform:translateX(-50%)` }, "0%"),
    ),
    h("div", { class: "flex flex-col gap-2", style: "position:relative" }, h("i", { style: zero }), ...rows),
  );
}

// 2022, when stocks and bonds fell together and the fund did not.
export class Edge extends Scene {
  name = "When stocks and bonds fell";
  summary = "2022, when stocks and bonds fell together. Swap part of a 60/40's bonds for our fund.";
  private pile: Pile;
  private clock = 0;
  private flash: THREE.Mesh<THREE.PlaneGeometry, THREE.ShaderMaterial>;
  private names: Label[] = [];
  private ticks: Label[] = [];
  private bars = h("div", { class: "border-t border-line pt-2" });
  private grid = h("div", { class: "border-t border-line pt-2 flex flex-col gap-1.5" });
  private input: HTMLInputElement;
  private share = h("b", { class: "figure text-[24px] text-ink font-medium" });
  private readout = {
    cagr: stat("", "Return a year"),
    vol: stat("", "Volatility"),
    drawdown: stat("", "Worst fall"),
  };
  private rows = bars((row) => this.point(row));

  // Drops each ball onto its 2022 return, the fund last at 2.4 s.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [1.2, 3.2, 18.5], look: [0.6, 0.5, 0], drift: 0.5, shift: 0.12 };
    this.physics = { stiff: 9, damp: 1.25, flow: 0.18, spin: 0.02, mouse: 0.7 };
    this.dwell = 13;
    const rests = ROWS.map((row, i) => new THREE.Vector3(X(row.value), i === OURS ? 0.42 : 0.32, 0));
    const starts = ROWS.map((_, i) => 0.6 + i * 0.6);
    const colors = ROWS.map((row) => new THREE.Color(row.color).multiplyScalar(row.kind === "ours" ? 1.6 : 0.9));
    const radii = ROWS.map((_, i) => (i === OURS ? 0.42 : 0.32));
    this.pile = new Pile(rests, radii, starts, colors);
    this.pile.onLand = (i) => {
      if (i === OURS) this.landed();
      else this.w.sound.tick(1.2 + i * 0.2, 0.4);
    };
    this.flash = glow(C.gold, 7, 0);
    this.flash.userData.keep = true;
    this.flash.position.copy(rests[OURS]!);
    this.group.add(this.pile.mesh, this.flash);
    for (const v of TICKS) {
      // Zero sits below the glow; small screens skip the odd ticks.
      const tick = this.addLabel(new Label(v === 0 ? "0%" : pct(v, 0), [X(v), v === 0 ? -1.5 : -0.55, 1.2], "center"));
      this.ticks.push(tick);
      tick.moves = false;
      if (v === -0.15 || v === -0.05) tick.small = { html: "" };
      if (v === 0) tick.small = { at: new THREE.Vector3(X(v), -1.7, 1.2) };
    }
    // Each ball's name and 2022 return, staggered so close ones read.
    ROWS.forEach((row, i) => {
      const html =
        row.kind === "ours"
          ? `${row.label} <b class="text-gold">${signed(row.value)}</b>`
          : `${row.label} <b class="text-ink">${signed(row.value)}</b>`;
      const label = new Label(html, [X(row.value), LIFT[i]!, 0], "center", row.kind === "ours" ? "big" : undefined);
      // On small screens the fund's name rises clear of the others.
      if (row.kind === "ours") label.small = { at: new THREE.Vector3(X(row.value), 3.4, 0) };
      this.names.push(this.addLabel(label));
    });
    this.panel.append(
      ...header(
        "Stocks and bonds fell, <em>not us</em>",
        "2021 to 2026, when bonds had their worst years in decades. Swap part of a 60/40's bonds for our fund and see what changes.",
      ),
      stats(...Object.values(this.readout).map((s) => s.el)),
    );
    // The slider moves 0 to 20 points of the portfolio from bonds to us.
    const last = STEPS[STEPS.length - 1]!.fund;
    this.input = slider("bond-swap", "Fund share of the portfolio", 0, last, 1, 0);
    this.input.addEventListener("input", () => this.set(+this.input.value));
    // The slider comes first, so it shows on a phone held sideways.
    const ends = h("div", { class: "flex justify-between eyebrow" }, h("span", {}, "0%"), h("span", {}, `${last}%`));
    const glass = box(
      "w-[min(420px,calc(100vw-32px))] gap-2",
      h(
        "div",
        { class: "flex items-baseline justify-between gap-3" },
        this.share,
        h("span", { class: "eyebrow" }, "moved from bonds to us"),
      ),
      this.input,
      ends,
      this.grid,
      this.bars,
      h(
        "p",
        { class: "text-[11px] text-ink-3" },
        "2021 to 2026, monthly. Data from SPY, AGG and FRED. S&P 500 without dividends.",
      ),
    );
    this.controls.append(glass);
    this.bars.append(this.rows);
    // SE-size screens: the four 2022 returns as a grid, the fund first.
    const order = [OURS, ...ROWS.keys()].filter((i, j, all) => all.indexOf(i) === j);
    this.grid.append(
      h("p", { class: "eyebrow" }, "2022 · return"),
      h(
        "div",
        {
          class: "grid grid-cols-2 gap-x-4 gap-y-1 text-[13px]",
          title: "2021 to 2026, monthly. Data from SPY, AGG and FRED.",
        },
        ...order.map((i) => {
          const row = ROWS[i]!;
          return h(
            "div",
            { class: "flex justify-between gap-2" },
            h("span", { class: row.kind === "ours" ? "text-ink" : "text-ink-2" }, row.label),
            h(
              "b",
              { class: `figure font-medium ${row.kind === "ours" ? "text-gold" : "text-ink"}` },
              signed(row.value),
            ),
          );
        }),
      ),
    );
    // Small screens: all but the fund's bar and the slider fold away.
    const more = h("div", { class: "small-only justify-end" });
    this.rows.append(more);
    const rows = [...this.rows.querySelectorAll(".bar-row")];
    fold(glass, more, [...rows.slice(0, OURS), glass.lastElementChild!], "Show all");
    ends.classList.add("ends");
    this.fit();
    addEventListener("resize", () => this.active && this.fit());
    this.set(0);
    this.frame = corners(-9.6, -2, -1.2, 9.6, 3.9, 1.2);
    this.zoomCap = 1.4;
  }

  // The return axis with ticks, a cyan post at zero and a dusty floor.
  formation() {
    const f = blank();
    let k = 0;
    for (let i = 0; i <= 380; i++, k++) f.put(k, -SPAN / 2 + (i / 380) * SPAN, 0, 1.2, 0.2, C.ink, 0.5);
    for (const v of TICKS) {
      for (let j = 0; j < 14; j++, k++) f.put(k, X(v), -0.05 - j * 0.02, 1.2, 0.2, C.ink, 0.6);
    }
    for (let j = 0; j < 160; j++, k++) f.put(k, X(0), j * 0.05, 0, 0.18, C.cyan, 0.45);
    const r = seeded(77);
    for (let i = 0; i < 3000; i++, k++) {
      const z = (r() - 0.5) * 9;
      f.put(k, (r() - 0.5) * SPAN * 1.3, -0.06, z, 0.18 + r() * 0.12, C.dust, 0.28 * (1 - Math.abs(z) / 5));
    }
    dust(f, k, 23, 36, 1.4, 0.12);
    return f;
  }

  // Shows the 60/40 with n points of its bonds in the fund.
  set(n: number) {
    const step = STEPS.find((x) => x.fund === n) ?? STEPS[0]!;
    this.input.value = String(n);
    this.share.textContent = `${n}%`;
    this.readout.cagr.value.textContent = pct(step.cagr);
    this.readout.vol.value.textContent = pct(step.vol);
    this.readout.drawdown.value.textContent = pct(step.drawdown);
  }

  // Flashes and ripples where the fund lands, and shows the names.
  landed() {
    this.w.sim.wave({ at: new THREE.Vector3(X(Y.fund), 0.4, 0), amp: 2, speed: 9 });
    this.w.sound.tick(0.5, 1);
    gsap.fromTo(this.flash.scale, { x: 0.3, y: 0.3 }, { x: 1.4, y: 1.4, duration: 1.2, ease: "expo.out" });
    gsap.fromTo(this.flash.material.uniforms.uOpacity, { value: 1.4 }, { value: 0.3, duration: 2, ease: "power2.out" });
    // On SE-size screens only the fund keeps its name over its ball.
    this.names.forEach((l, i) => (l.shown = i === OURS || !tiny()));
  }

  // The grid or the bars, ball names and ticks, for the screen's size.
  fit() {
    const t = tiny();
    this.grid.hidden = !t;
    this.bars.hidden = t;
    this.ticks.forEach((l) => (l.shown = !t));
    if (t) this.names.forEach((l, i) => i !== OURS && (l.shown = false));
  }

  // Lifts every ball back into the sky and lets them fall again.
  drop() {
    this.clock = 0;
    this.pile.reset();
    for (const l of this.names) l.hide();
    this.flash.material.uniforms.uOpacity.value = 0;
  }

  // Drops the balls, fills the bars and starts the slider at zero.
  override enter() {
    this.drop();
    for (const l of this.labels) l.shown = !this.names.includes(l);
    this.fit();
    const bars = this.rows.querySelectorAll<HTMLElement>("[data-bar]");
    // Each bar grows out of the zero line, left or right.
    gsap.fromTo(
      bars,
      { scaleX: 0 },
      {
        scaleX: 1,
        transformOrigin: (_: number, el: HTMLElement) =>
          el.dataset["side"] === "left" ? "right center" : "left center",
        duration: 1,
        stagger: 0.12,
        delay: 0.8,
        ease: "expo.out",
      },
    );
  }

  // Bounces the ball of a hovered or pressed row.
  point(row: number) {
    if (row < 0) return;
    this.pile.bounce(row, row === OURS ? 9 : 6);
    this.w.sound.tick(row === OURS ? 0.7 : 1.4, 0.4);
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

  // Names the ball under the pointer and its 2022 return.
  override hover(x: number, y: number) {
    const i = this.ballAt(x, y);
    if (i < 0) return null;
    const row = ROWS[i]!;
    return `<strong>${row.label}</strong><br>2022 return <strong>${signed(row.value)}</strong>`;
  }

  // Bounces the clicked ball, the fund higher.
  override click(x: number, y: number) {
    const i = this.ballAt(x, y);
    if (i >= 0) this.point(i);
  }
}
