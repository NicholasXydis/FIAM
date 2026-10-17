import gsap from "gsap";
import * as THREE from "three";
import { at, D, money, num, pct } from "../data";
import { Formation } from "../gl/sim";
import { glow, rim, tube } from "../gl/shapes";
import { chip, h, Label, nearest, slider, swatch } from "../ui";
import { C, dust, rand, Scene, type World } from "./scene";

const BOOKS = D.capacity.books;
const LO = 6;
const HI = Math.log10(5e9);
const X = (capital: number) => -8.5 + ((Math.log10(capital) - LO) / (HI - LO)) * 17;
const Y = (ir: number) => ir * 1.55;
const STYLE: Record<string, { color: number; mark: string; z: number }> = {
  "final v3": { color: C.gold, mark: "var(--m-ours)", z: 1.6 },
  v1: { color: C.cyan, mark: "var(--m-long)", z: 0 },
  v2: { color: C.purple, mark: "var(--m-brand)", z: -1.6 },
  "v2-pass": { color: C.ink, mark: "var(--ink-3)", z: -3.2 },
};
const order = ["final v3", "v1", "v2", "v2-pass"];

// IR at any capital between two tested sizes, on a log scale, as the deck interpolates.
const curve = (rows: (typeof BOOKS)[number]["rows"], n = 90) =>
  Array.from({ length: n }, (_, i) => {
    const cap = 10 ** (LO + ((HI - LO) * i) / (n - 1));
    return new THREE.Vector3(X(cap), Y(at(rows, cap, "ir")), 0);
  });

export class Capacity extends Scene {
  name = "How much money can it run?";
  summary = "Information ratio from $1M to $5B. The final book still pays at the top.";
  private input: HTMLInputElement;
  private size = h("b", { class: "figure text-[24px] text-ink font-medium" });
  private table = h("div", { class: "flex flex-col gap-1.5" });
  private plane: THREE.Mesh<THREE.BoxGeometry, THREE.MeshBasicMaterial>;
  private marks: THREE.Mesh[] = [];
  private dots: { at: THREE.Vector3; label: string; row: (typeof BOOKS)[number]["rows"][number] }[] = [];

  constructor(w: World) {
    super(w);
    this.shot = { eye: [2.5, 2.2, 23.5], look: [0.4, -1.9, -0.8], drift: 0.6, shift: 0.02 };
    this.physics = { stiff: 8, damp: 1.25, flow: 0.15, spin: 0.02, mouse: 0.7 };
    this.dwell = 13;
    for (const key of order) {
      const book = BOOKS.find((b) => b.key === key)!;
      const s = STYLE[key];
      const line = tube(
        curve(book.rows).map((p) => p.setZ(s.z)),
        s.color,
        key === "final v3" ? 0.07 : 0.045,
        key === "final v3" ? 1.6 : 1,
        key === "v2-pass",
      );
      this.group.add(line);
      for (const row of book.rows) {
        const dot = new THREE.Mesh(
          new THREE.SphereGeometry(key === "final v3" ? 0.16 : 0.11, 16, 12),
          rim(s.color, 1.4, 0.8),
        );
        dot.position.set(X(row.capital), Y(row.ir), s.z);
        this.dots.push({ at: dot.position, label: book.label, row });
        this.group.add(dot);
      }
      const end = book.rows[book.rows.length - 1];
      this.addLabel(
        new Label(
          `${swatch(s.mark)}${book.label} <b class="text-ink">${num(end.ir)}</b>`,
          [X(end.capital) + 0.4, Y(end.ir) + (key === "v2" ? 0.45 : key === "final v3" ? -0.15 : 0), s.z],
          "left",
        ),
      );
    }
    for (const c of [1e6, 1e7, 1e8, 1e9, 5e9])
      this.addLabel(new Label(money(c), [X(c), Y(1.25) + 0.5, -0.8], "center"));
    this.addLabel(new Label("IR 0 · the hurdle", [-8.7, 0.1, 2.4], "right"));
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
      const mark = glow(STYLE[key].color, key === "final v3" ? 1.5 : 1.1, 1.2);
      mark.userData.key = key;
      this.marks.push(mark);
      this.group.add(mark);
    }
    const v1 = BOOKS.find((b) => b.key === "v1")!;
    const final = BOOKS.find((b) => b.key === "final v3")!;
    const last = final.rows[final.rows.length - 1];
    this.panel.append(
      h("p", { class: "eyebrow", "data-rise": true }, "How much money can it run?"),
      h("h2", {
        class: "headline text-[44px] md:text-[56px]",
        "data-rise": true,
        html: `Still paying <em>at ${money(last.capital)}</em>`,
      }),
      h(
        "p",
        { class: "body", "data-rise": true },
        `Bigger funds pay more to trade. Our first book earns the most dollars near ${money(v1.peak)} and stops beating the hurdle near ${money(+v1.break_even)}. The final book slows its trading as the fund grows, and at ${money(last.capital)} it still makes an IR of ${num(last.ir)}, about ${money(last.dollars)} a year above cash. Dots mark the sizes we ran, and the lines join them on a log scale.`,
      ),
    );
    this.input = slider("capital", "Fund size", LO, HI, 0.001, 7);
    this.input.addEventListener("input", () => {
      this.timeline?.kill();
      this.set(10 ** (HI - +this.input.value < 0.004 ? HI : +this.input.value));
    });
    this.controls.append(
      h(
        "div",
        { class: "glass rounded-2xl px-4 py-3 w-[min(420px,calc(100vw-32px))] flex flex-col gap-2" },
        h(
          "div",
          { class: "flex items-center justify-between gap-3" },
          this.size,
          chip("Sweep $1M to $5B", () => this.sweep()),
        ),
        this.input,
        this.table,
      ),
    );
    this.set(1e7);
  }

  formation() {
    const f = new Formation();
    const r = rand(55);
    let k = 0;
    const tint = new THREE.Color();
    for (const key of order) {
      const book = BOOKS.find((b) => b.key === key)!;
      const s = STYLE[key];
      const n = key === "final v3" ? 3200 : 1700;
      for (let i = 0; i < n; i++, k++) {
        const cap = 10 ** (LO + (HI - LO) * r());
        const top = Y(at(book.rows, cap, "ir"));
        const v = Math.pow(r(), 1.8);
        tint.setHex(s.color);
        f.put(
          k,
          X(cap),
          top * (1 - v),
          s.z + (r() - 0.5) * 0.25,
          0.2 + r() * 0.18,
          tint,
          (key === "final v3" ? 0.5 : 0.3) * (1 - v * 0.7),
        );
      }
    }
    for (let gx = 0; gx <= 85; gx++) {
      for (let gz = 0; gz <= 14; gz++, k++) {
        const on = gx % 5 === 0 || gz % 4 === 0;
        f.put(k, -8.5 + gx * 0.2, 0, -4.4 + gz * 0.5, on ? 0.18 : 0, C.dust, 0.4);
      }
    }
    dust(f, k, 29, 36, 1.4, 0.12);
    return f;
  }

  set(capital: number) {
    this.input.value = String(Math.log10(capital));
    this.input.style.setProperty("--fill", `${((Math.log10(capital) - LO) / (HI - LO)) * 100}%`);
    this.size.textContent = money(capital);
    this.plane.position.set(X(capital), Y(-0.4), 0);
    for (const mark of this.marks) {
      const book = BOOKS.find((b) => b.key === mark.userData.key)!;
      mark.position.set(X(capital), Y(at(book.rows, capital, "ir")), STYLE[mark.userData.key].z);
    }
    this.table.innerHTML = "";
    for (const key of order) {
      const book = BOOKS.find((b) => b.key === key)!;
      const ir = at(book.rows, capital, "ir");
      const dollars = at(book.rows, capital, "dollars");
      this.table.append(
        h(
          "div",
          { class: "flex items-center justify-between gap-3 text-[13px]" },
          h("span", {
            class: key === "final v3" ? "text-ink" : "text-ink-2",
            html: `${swatch(STYLE[key].mark)}${book.label}`,
          }),
          h(
            "span",
            { class: "figure text-ink-2" },
            h("b", { class: "text-ink font-medium" }, `IR ${num(ir)}`),
            ` · ${dollars < 0 ? "−" : ""}${money(Math.abs(dollars))}/yr`,
          ),
        ),
      );
    }
  }

  // Runs the fund size from the smallest to the largest tested, so every curve can be read in turn.
  sweep() {
    this.timeline?.kill();
    const state = { x: LO };
    this.timeline = gsap
      .timeline()
      .to(state, { x: HI, duration: 5, ease: "power1.inOut", onUpdate: () => this.set(10 ** state.x) });
  }

  hover(x: number, y: number) {
    const i = nearest(
      this.dots.map((d) => d.at),
      x,
      y,
      this.w.stage.camera,
      16,
    );
    if (i < 0) return null;
    const { label, row } = this.dots[i];
    const dollars = `${row.dollars < 0 ? "−" : ""}${money(Math.abs(row.dollars))}`;
    return `<strong>${label} at ${money(row.capital)}</strong><br>IR <strong>${num(row.ir)}</strong> · ${pct(row.net)} a year above cash<br>${dollars} a year · costs ${pct(row.cost, 2)}`;
  }

  enter() {
    for (const l of this.labels) l.shown = true;
    gsap.delayedCall(1.6, () => this.active && this.sweep());
  }
}
