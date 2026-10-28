import gsap from "gsap";
import * as THREE from "three";
import { D, pct, signed } from "../../shared/data";
import { blank } from "../gl/sim";
import { glow, rim, tube } from "../gl/shapes";
import { h } from "../../shared/dom";
import { corners } from "../layout";
import { box, chip, Label, nearest, slider, swatch } from "../ui";
import { C, dust, header, Scene, type World } from "./scene";
import { clamp, mix, seeded } from "../../shared/math";

// The crises in date order, and the chart's x from first to last.
const CRISES = D.crises;
const LAST = CRISES.length - 1;
// Crisis index to x, a move to y, and each series' colour, mark, depth.
const X = (i: number) => -8.5 + (i / LAST) * 17;
const Y = (move: number) => move * 7;
const STYLE: Record<Series, { color: number; mark: string; z: number; label: string }> = {
  book: { color: C.gold, mark: "var(--m-ours)", z: 1.6, label: "Final book" },
  market: { color: C.purple, mark: "var(--m-brand)", z: 0, label: "US market" },
};
// The series drawn, listed and labelled, the final book first.
type Series = "book" | "market";
const order: Series[] = ["book", "market"];

// A series' move at any point between crises, linear between them.
const at = (key: Series, x: number) => {
  const i = Math.min(LAST - 1, Math.max(0, Math.floor(x)));
  return mix(CRISES[i]![key], CRISES[i + 1]![key], clamp(x - i, 0, 1));
};

// The moves from the first crisis to the last, as a line of points.
const curve = (key: Series, n = 90) =>
  Array.from({ length: n }, (_, i) => {
    const x = (LAST * i) / (n - 1);
    return new THREE.Vector3(X(x), Y(at(key, x)), 0);
  });

// The crises replayed: the final book against the market in each.
export class Capacity extends Scene {
  name = "Crises, replayed";
  summary = `The final book against the market in ${CRISES.length} replayed crises. It barely moved.`;
  private input: HTMLInputElement;
  private size = h("b", { class: "figure text-[24px] text-ink font-medium" });
  private table = h("div", { class: "flex flex-col gap-1.5" });
  private crisis = h("span", { class: "text-ink" });
  private rows = order.map((key) => ({ key, move: h("b", { class: "text-ink font-medium" }) }));
  private plane: THREE.Mesh<THREE.BoxGeometry, THREE.MeshBasicMaterial>;
  private marks: THREE.Mesh[] = [];
  private dots: { at: THREE.Vector3; key: Series; crisis: number }[] = [];

  // Builds each series' curve, a dot per crisis, labels and controls.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [2.5, 2.2, 23.5], look: [0.4, -1.9, -0.8], drift: 0.6, shift: 0.02 };
    this.physics = { stiff: 8, damp: 1.25, flow: 0.15, spin: 0.02, mouse: 0.7 };
    this.dwell = 13;
    for (const key of order) {
      const s = STYLE[key];
      const line = tube(
        curve(key).map((p) => p.setZ(s.z)),
        s.color,
        key === "book" ? 0.07 : 0.045,
        key === "book" ? 1.6 : 1,
        false,
      );
      this.group.add(line);
      CRISES.forEach((c, i) => {
        const dot = new THREE.Mesh(
          new THREE.SphereGeometry(key === "book" ? 0.16 : 0.11, 16, 12),
          rim(s.color, 1.4, 0.8),
        );
        dot.position.set(X(i), Y(c[key]), s.z);
        this.dots.push({ at: dot.position, key, crisis: i });
        this.group.add(dot);
      });
      const end = CRISES[LAST]!;
      // On small screens the table names the series, so ends show the move.
      this.addLabel(
        new Label(
          `${swatch(s.mark)}${s.label} <b class="text-ink">${signed(end[key])}</b>`,
          [X(LAST) + 0.4, Y(end[key]) + (key === "book" ? -0.15 : 0.3), s.z],
          "left",
        ),
      ).small = { html: `${swatch(s.mark)}<b class="text-ink">${signed(end[key])}</b>` };
    }
    // Year labels along the top, at every fifth crisis and the last.
    for (const i of [0, 5, 10, LAST])
      this.addLabel(new Label(CRISES[i]!.first.slice(0, 4), [X(i), Y(0.33) + 0.4, -0.8], "center")).moves = false;
    // On small screens the zero line's label sits under its line, inside.
    this.addLabel(new Label("No move", [-8.7, 0.1, 2.4], "right")).small = {
      at: new THREE.Vector3(-8.4, -0.55, 2.4),
      align: "left",
    };
    // A post at the slider's crisis and a glow on each curve there.
    this.plane = new THREE.Mesh(
      new THREE.BoxGeometry(0.025, 7.4, 0.025),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(C.ink).multiplyScalar(1.3),
        transparent: true,
        opacity: 0.45,
      }),
    );
    this.group.add(this.plane);
    for (const key of order) {
      const mark = glow(STYLE[key].color, key === "book" ? 1.5 : 1.1, 1.2);
      mark.userData.key = key;
      this.marks.push(mark);
      this.group.add(mark);
    }
    const worst = CRISES.reduce((a, b) => (b.book < a.book ? b : a));
    this.panel.append(
      ...header(
        `${CRISES.length} crises, <em>barely moved</em>`,
        `Today's book replayed through every crisis since 2000. Its worst was ${signed(worst.book)} in ${worst.name}, when the US market moved ${signed(worst.market, 0)}. Drag to pick one.`,
      ),
    );
    // The slider runs across the crises and snaps to the nearest one.
    this.input = slider("crisis", "Crisis", 0, LAST, 1, 0);
    this.input.addEventListener("input", () => {
      this.timeline?.kill();
      this.set(+this.input.value);
    });
    this.controls.append(
      box(
        "w-[min(420px,calc(100vw-32px))] gap-2",
        h(
          "div",
          { class: "flex items-center justify-between gap-3" },
          this.size,
          chip(`Play all ${CRISES.length}`, () => this.sweep()),
        ),
        this.input,
        this.table,
      ),
    );
    // The crisis' name, then one row per series with its move there.
    this.table.append(h("div", { class: "flex items-center justify-between gap-3 text-[13px]" }, this.crisis));
    for (const { key, move } of this.rows) {
      this.table.append(
        h(
          "div",
          { class: "flex items-center justify-between gap-3 text-[13px]" },
          h("span", {
            class: key === "book" ? "text-ink" : "text-ink-2",
            html: `${swatch(STYLE[key].mark)}${STYLE[key].label}`,
          }),
          h("span", { class: "figure text-ink-2" }, move),
        ),
      );
    }
    this.set(0);
    // Small screens fit the curves and their floor into the band.
    this.frame = corners(-8.6, -5, -3.2, 8.6, 3, 1.6);
  }

  // A curtain under each curve, densest at the line, over a lattice at 0.
  formation() {
    const f = blank();
    const r = seeded(55);
    let k = 0;
    const tint = new THREE.Color();
    for (const key of order) {
      const s = STYLE[key];
      const n = key === "book" ? 3200 : 1700;
      for (let i = 0; i < n; i++, k++) {
        const x = LAST * r();
        const top = Y(at(key, x));
        const v = Math.pow(r(), 1.8);
        tint.setHex(s.color);
        f.put(
          k,
          X(x),
          top * (1 - v),
          s.z + (r() - 0.5) * 0.25,
          0.2 + r() * 0.18,
          tint,
          (key === "book" ? 0.5 : 0.3) * (1 - v * 0.7),
        );
      }
    }
    // The floor at no move, dots shown only on every 5th and 4th line.
    for (let gx = 0; gx <= 85; gx++) {
      for (let gz = 0; gz <= 14; gz++, k++) {
        const on = gx % 5 === 0 || gz % 4 === 0;
        f.put(k, -8.5 + gx * 0.2, 0, -4.4 + gz * 0.5, on ? 0.18 : 0, C.dust, 0.4);
      }
    }
    dust(f, k, 29, 36, 1.4, 0.12);
    return f;
  }

  // Moves slider, post, glows and readout rows to a point between crises.
  set(x: number) {
    const i = Math.round(x);
    this.input.value = String(i);
    this.input.style.setProperty("--fill", `${(x / LAST) * 100}%`);
    this.size.textContent = CRISES[i]!.first.slice(0, 4);
    this.crisis.textContent = CRISES[i]!.name;
    this.plane.position.set(X(x), Y(-0.15), 0);
    for (const mark of this.marks) {
      const key = mark.userData.key as Series;
      mark.position.set(X(x), Y(at(key, x)), STYLE[key].z);
    }
    for (const row of this.rows) row.move.textContent = signed(CRISES[i]![row.key]);
  }

  // Sweeps the first crisis to the last over 5 s, each read in turn.
  sweep() {
    this.timeline?.kill();
    const state = { x: 0 };
    this.timeline = gsap
      .timeline()
      .to(state, { x: LAST, duration: 5, ease: "power1.inOut", onUpdate: () => this.set(state.x) });
  }

  // Reads the crisis within 16 px: its name, dates and both moves.
  override hover(x: number, y: number) {
    const i = nearest(
      this.dots.map((d) => d.at),
      x,
      y,
      this.w.stage.camera,
      16,
    );
    if (i < 0) return null;
    const c = CRISES[this.dots[i]!.crisis]!;
    return `<strong>${c.name}</strong><br>${c.first} to ${c.last}<br>Final book <strong>${signed(c.book)}</strong> · market ${signed(c.market)}<br><span class="muted">${pct(c.coverage, 0)} of today's book traded then</span>`;
  }

  // Shows the labels and sweeps the crises 1.6 s after arriving.
  override enter() {
    this.showLabels();
    gsap.delayedCall(1.6, () => this.active && this.sweep());
  }
}
