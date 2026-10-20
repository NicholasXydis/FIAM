import * as THREE from "three";
import { D, int, pct, prose } from "../../shared/data";
import { blank, N } from "../gl/sim";
import { h } from "../../shared/dom";
import { corners, portrait } from "../layout";
import { box, chip, fold, Label, legendOf, screen, stat, swatch } from "../ui";
import { C, dust, header, Scene, stats, type World } from "./scene";
import { GOLDEN } from "../../shared/math";

// The attempts data, the dot spacing, and the family we shipped.
const HN = D.honesty;
const DOT = 0.15;
const SHIPPED = HN.families.findIndex((f) => f.verdict.startsWith("Shipped"));
// The families biggest first, each with its cluster's radius.
const PLACED = HN.families
  .map((_, i) => i)
  .sort((a, b) => HN.families[b].attempts - HN.families[a].attempts)
  .map((i) => ({ i, r: DOT * 0.55 * Math.sqrt(HN.families[i].attempts) + 0.25 }));
const BIG = PLACED[0]!.i;
// The chips' filters: every attempt, the shippable, or the rest.
const FILTERS = [
  { name: "All", keep: () => true, lines: [0, 1, 2] },
  { name: "Shippable", keep: (f: (typeof HN.families)[number]) => f.eligible, lines: [0, 1] },
  { name: "Research", keep: (f: (typeof HN.families)[number]) => !f.eligible, lines: [2] },
];
// The legend, one line each, its dots in the clusters' own colours.
const LEGEND = [
  `${swatch("var(--gold)")}Gold · the design we chose`,
  `${swatch("var(--purple)")}Bright · designs good enough to ship`,
  `${swatch("var(--ink-3)")}Faint · research runs and checks`,
];
// A family's name alone: no leading tally, no list after its colon.
const short = (what: string) => prose(what.split(":")[0]!.replace(/^\d+ (.)/, (_, c: string) => c.toUpperCase()));
// Reused points for measuring each cluster's size on screen.
const centre = { x: 0, y: 0, front: true };
const rim = { x: 0, y: 0, front: true };
const edge = new THREE.Vector3();

// Every attempt counted: a cluster per family, odds the edge is real.
export class Honesty extends Scene {
  name = "Every attempt, counted";
  summary = `All ${int(HN.attempts)} ideas we tested before choosing, and the odds that the edge is real.`;
  private centres: THREE.Vector3[] = [];
  private radii: number[] = [];
  private filter = 0;
  private chips: HTMLButtonElement[];
  // Labels over the chosen family and the largest, and the packing used.
  private chosen = new Label(`Chosen <b class="text-gold">●</b>`, [0, 0, 0], "center");
  private crown = new Label(short(HN.families[BIG].what), [0, 0, 0], "center");
  private tall = false;
  private legend = legendOf(LEGEND);

  // Packs the families biggest first, the largest alone at the right.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 1.2, 22], look: [0.4, 0.6, 0], drift: 0.7, shift: 0.1 };
    this.physics = { stiff: 9, damp: 1.2, flow: 0.22, spin: 0.03, mouse: 1.1 };
    this.dwell = 13;
    this.addLabel(this.chosen);
    this.addLabel(this.crown);
    this.pack(false);
    this.panel.append(
      ...header(
        "Every attempt, <em>counted</em>",
        "Each dot is one idea we tested before choosing. The bright ones could have shipped, and our odds count every one of them.",
      ),
      // Tried, good enough to ship, and the chance the edge holds there.
      stats(
        stat(int(HN.attempts), "Research runs").el,
        stat(int(HN.eligible), "Could have shipped").el,
        stat(pct(HN.dsr_eligible, 0), "Edge is real").el,
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
  }

  // Packs families in rows, the largest at the right or, if tall, below.
  private pack(tall: boolean) {
    this.tall = tall;
    const big = PLACED[0]!;
    const left = tall ? -4.4 : -6.6;
    const right = tall ? 4.4 : 6.2 - big.r - 0.8;
    const rows: { i: number; r: number; x: number }[][] = [[]];
    let x = left;
    let y = 4.3;
    let row = 0;
    // The rest fill rows from the left, wrapping before the big one.
    for (const p of PLACED.slice(1)) {
      if (x + p.r * 2 > right) {
        x = left;
        y -= row + 0.5;
        row = 0;
        rows.push([]);
      }
      this.centres[p.i] = new THREE.Vector3(x + p.r, y - p.r, 0);
      rows[rows.length - 1]!.push({ ...p, x: x + p.r * 2 });
      x += p.r * 2 + 0.5;
      row = Math.max(row, p.r * 2);
    }
    this.centres[big.i] = tall ? new THREE.Vector3(0, y - row - 0.9 - big.r, 0) : new THREE.Vector3(6.2, 0.4, 0);
    // Tall rows shift so each is centred on the big one.
    for (const r of tall ? rows : []) for (const p of r) this.centres[p.i]!.x -= (r.at(-1)!.x - left) / 2 + left;
    for (const p of PLACED) this.radii[p.i] = p.r;
    // Labels sit 0.45 above the chosen cluster and the largest one.
    this.chosen.at.copy(this.centres[SHIPPED]!).y += this.radii[SHIPPED]! + 0.45;
    this.crown.at.copy(this.centres[big.i]!).y += big.r + 0.45;
    // Small screens fit every cluster, with room for the labels on top.
    const xs = PLACED.flatMap((p) => [this.centres[p.i]!.x - p.r, this.centres[p.i]!.x + p.r]);
    const ys = PLACED.flatMap((p) => [this.centres[p.i]!.y - p.r, this.centres[p.i]!.y + p.r]);
    this.frame = corners(Math.min(...xs), Math.min(...ys), 0, Math.max(...xs), Math.max(...ys) + 0.8, 0);
  }

  // Each family a golden-angle spiral; the shipped one has a gold heart.
  formation() {
    if (this.tall !== portrait()) this.pack(portrait());
    const f = blank();
    const keep = FILTERS[this.filter].keep;
    const tint = new THREE.Color();
    let k = 0;
    HN.families.forEach((fam, i) => {
      const c = this.centres[i];
      const on = keep(fam) ? 1 : 0.12;
      tint.setHex(fam.eligible ? C.purple : C.ice);
      for (let j = 0; j < fam.attempts && k < N; j++, k++) {
        const d = DOT * 0.55 * Math.sqrt(j + 0.5);
        const a = j * GOLDEN;
        if (i === SHIPPED && j === 0) f.put(k, c.x, c.y, c.z + 0.2, 1.4, C.gold, 2.2);
        else {
          const z = c.z + Math.sin(j * 1.3) * 0.06;
          f.put(
            k,
            c.x + Math.cos(a) * d,
            c.y + Math.sin(a) * d,
            z,
            fam.eligible ? 0.5 : 0.36,
            tint,
            (fam.eligible ? 1.25 : 0.6) * on,
          );
        }
      }
    });
    dust(f, k, 43, 36, 1.4, 0.12);
    return f;
  }

  // Shows only one kind of attempt, or all.
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

  // Shows the labels over the chosen family and the largest.
  override enter() {
    this.showLabels();
  }

  // Shows every attempt again on the way out.
  override leave() {
    this.filter = 0;
    this.chips.forEach((c, i) => c.setAttribute("aria-pressed", String(i === 0)));
    this.lightLegend();
  }

  // The cluster whose screen circle, plus 6 px, holds the pointer, or -1.
  private cluster(x: number, y: number) {
    const camera = this.w.stage.camera;
    let best = -1;
    HN.families.forEach((_, i) => {
      screen(this.centres[i], camera, centre);
      screen(edge.copy(this.centres[i]).setX(this.centres[i].x + this.radii[i]), camera, rim);
      const r = Math.abs(rim.x - centre.x) + 6;
      if ((centre.x - x) ** 2 + (centre.y - y) ** 2 < r * r) best = i;
    });
    return best;
  }

  // Names the cluster under the pointer and what it found.
  override hover(x: number, y: number) {
    const i = this.cluster(x, y);
    if (i < 0) return null;
    const f = HN.families[i];
    return `<strong>${short(f.what)}</strong><br>${int(f.attempts)} ${f.attempts > 1 ? "tries" : "try"} · ${prose(f.verdict)}`;
  }

  // Ripples the clicked cluster.
  override click(x: number, y: number) {
    const i = this.cluster(x, y);
    if (i >= 0) this.w.sim.wave({ at: this.centres[i].clone(), amp: 1, speed: 6 });
  }
}
