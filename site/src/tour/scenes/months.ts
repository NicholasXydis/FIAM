import * as THREE from "three";
import { D, monthName, signed } from "../../shared/data";
import { blank } from "../gl/sim";
import { h } from "../../shared/dom";
import { corners, portrait } from "../layout";
import { box, chip, fold, legendOf, nearest, stat, swatch } from "../ui";
import { ball, C, dust, header, Scene, stats, type World } from "./scene";
import { seeded } from "../../shared/math";

// The fund's return in each month, and the months they belong to.
const RETURNS = D.race.book_monthly;
const MONTHS = D.months;
// The headline's month counts and its best and worst stretches.
const HEAD = D.headline;
// The chips' filters: every month, the months up, or the months down.
const FILTERS = [
  { name: "All", keep: () => true, lines: [0, 1] },
  { name: "Up months", keep: (r: number) => r > 0, lines: [0] },
  { name: "Down months", keep: (r: number) => r <= 0, lines: [1] },
];
// The legend, one line each, its dots in the months' own colours.
const LEGEND = [
  `${swatch("var(--gold)")}Gold · a month the fund rose`,
  `${swatch("var(--ink-3)")}Faint · a month it fell`,
];

// One dot per month: where it sits and that month's return.
interface Dot {
  at: THREE.Vector3;
  ret: number;
}

// The months on an ellipse, tall if portrait, the first in the middle.
function scatter(tall: boolean): Dot[] {
  const [rx, ry] = tall ? [3.4, 6.4] : [7.2, 3.6];
  const r = seeded(43);
  // Rings out from the centre in date order, each dot on a golden turn.
  return RETURNS.map((ret, k) => {
    const a = k * 2.39996 + r() * 0.5;
    const d = 0.12 + 0.88 * Math.sqrt((k + 0.5) / RETURNS.length) + (r() - 0.5) * 0.08;
    return { at: new THREE.Vector3(Math.cos(a) * d * rx, 0.6 + Math.sin(a) * d * ry, 0), ret };
  });
}

// Every month counted: a dot each, gold when the fund rose.
export class Months extends Scene {
  name = "Every month, counted";
  summary = `Every month of the fund, ${monthName(MONTHS[0]!)} to ${monthName(MONTHS[MONTHS.length - 1]!)}, up or down.`;
  private dots = scatter(false);
  private tall = false;
  private filter = 0;
  private chips: HTMLButtonElement[];
  private legend = legendOf(LEGEND);

  // Sets the panel, the four tiles and the filter chips.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 1.2, 22], look: [0.4, 0.6, 0], drift: 0.7, shift: 0.1 };
    this.physics = { stiff: 9, damp: 1.2, flow: 0.22, spin: 0.03, mouse: 1.1 };
    this.dwell = 13;
    this.panel.append(
      ...header(
        "Every month, <em>counted</em>",
        `Each dot is one month of the fund, ${monthName(MONTHS[0]!)} to ${monthName(MONTHS[MONTHS.length - 1]!)}. Gold months rose and faint months fell. Pick a dot to see its return.`,
      ),
      // Tiles: months up, the best and worst month, the worst 12 months.
      stats(
        stat(`${HEAD.months_up} of ${RETURNS.length}`, "Months up").el,
        stat(signed(HEAD.best_month.value), "Best month").el,
        stat(signed(HEAD.worst_month.value), "Worst month").el,
        stat(signed(HEAD.worst_12.value), "Worst 12 months").el,
      ),
    );
    this.chips = FILTERS.map((f, i) => chip(f.name, () => this.only(i), i === 0));
    this.controls.append(
      box(
        "w-[min(420px,calc(100vw-32px))] gap-2 text-[13px] text-ink-2",
        h("div", { class: "flex flex-wrap gap-1.5" }, ...this.chips),
        this.legend.el,
      ),
    );
    // Small screens: the filter chips scroll, the legend folds behind Key.
    const glass = this.controls.firstElementChild as HTMLElement;
    const filters = glass.firstElementChild as HTMLElement;
    filters.classList.add("row");
    fold(glass, filters, [glass.lastElementChild!], "Key");
    this.lay(false);
  }

  // Scatters wide or tall, and fits every dot with a little room.
  private lay(tall: boolean) {
    this.tall = tall;
    this.dots = scatter(tall);
    const xs = this.dots.map((d) => d.at.x);
    const ys = this.dots.map((d) => d.at.y);
    this.frame = corners(
      Math.min(...xs) - 0.4,
      Math.min(...ys) - 0.4,
      0,
      Math.max(...xs) + 0.4,
      Math.max(...ys) + 0.6,
      0,
    );
  }

  // Each month a soft orb, gold if the fund rose and faint if it fell.
  formation() {
    if (this.tall !== portrait()) this.lay(portrait());
    const f = blank();
    const keep = FILTERS[this.filter]!.keep;
    const r = seeded(19);
    let k = 0;
    // Up months are larger gold orbs, down months small and dim.
    for (const d of this.dots) {
      const on = keep(d.ret) ? 1 : 0.12;
      if (d.ret > 0) k = ball(f, k, 90, d.at, 0.28, 0.3, C.gold, 1.2 * on, r);
      else k = ball(f, k, 50, d.at, 0.2, 0.26, C.ice, 0.6 * on, r);
    }
    dust(f, k, 43, 36, 1.4, 0.12);
    return f;
  }

  // Shows only the months up, the months down, or all.
  only(filter: number) {
    if (filter === this.filter) return;
    this.filter = filter;
    this.chips.forEach((c, i) => c.setAttribute("aria-pressed", String(i === filter)));
    this.lightLegend();
    this.w.sim.show(this.formation(), 0.5, 0.8);
    this.w.sound.tick(1, 0.6);
  }

  // Brightens the legend lines the filter shows; the rest fade.
  private lightLegend() {
    this.legend.light(FILTERS[this.filter]?.lines ?? []);
  }

  // Shows every month again on the way out.
  override leave() {
    this.filter = 0;
    this.chips.forEach((c, i) => c.setAttribute("aria-pressed", String(i === 0)));
    this.lightLegend();
  }

  // The month dot nearest the pointer, within 18 px, or -1.
  private at(x: number, y: number) {
    return nearest(
      this.dots.map((d) => d.at),
      x,
      y,
      this.w.stage.camera,
      18,
    );
  }

  // Names the month under the pointer and the fund's return in it.
  override hover(x: number, y: number) {
    const i = this.at(x, y);
    if (i < 0) return null;
    return `<strong>${monthName(MONTHS[i]!)}</strong><br>${signed(this.dots[i]!.ret)} that month`;
  }

  // Ripples the month picked.
  override click(x: number, y: number) {
    const i = this.at(x, y);
    if (i >= 0) this.w.sim.wave({ at: this.dots[i]!.at.clone(), amp: 1, speed: 6 });
  }
}
