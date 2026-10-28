import * as THREE from "three";
import { D, int, prose } from "../../shared/data";
import { blank } from "../gl/sim";
import { h } from "../../shared/dom";
import { corners, portrait } from "../layout";
import { box, chip, fold, Label, legendOf, nearest, stat, swatch } from "../ui";
import { ball, C, dust, header, Scene, stats, type World } from "./scene";
import { seeded } from "../../shared/math";

// The attempts data and the family we shipped.
const HN = D.honesty;
const SHIPPED = HN.families.findIndex((f) => f.verdict.startsWith("Shipped"));
// The chips' filters: every attempt, the strategies, or the research.
const FILTERS = [
  { name: "All", keep: () => true, lines: [0, 1, 2] },
  { name: "Strategies", keep: (f: (typeof HN.families)[number]) => f.eligible, lines: [0, 1] },
  { name: "Research", keep: (f: (typeof HN.families)[number]) => !f.eligible, lines: [2] },
];
// The legend, one line each, its dots in the attempts' own colours.
const LEGEND = [
  `${swatch("var(--gold)")}Gold · the strategy we run`,
  `${swatch("var(--purple)")}Bright · strategies run as the fund`,
  `${swatch("var(--ink-3)")}Faint · ideas and what-ifs`,
];
// A family's name alone: no leading tally, no list after its colon.
const short = (what: string) => prose(what.split(":")[0]!.replace(/^\d+ (.)/, (_, c: string) => c.toUpperCase()));

// One dot per attempt, its family, and whether it is the one chosen.
interface Dot {
  family: number;
  at: THREE.Vector3;
  chosen: boolean;
}

// The attempts on an ellipse, tall when portrait, the chosen central.
function scatter(tall: boolean): Dot[] {
  const [rx, ry] = tall ? [3.4, 6.4] : [7.2, 3.6];
  const r = seeded(43);
  const dots: Dot[] = [];
  HN.families.forEach((fam, i) => {
    for (let j = 0; j < fam.attempts; j++) {
      const chosen = i === SHIPPED && j === 0;
      if (chosen) {
        dots.push({ family: i, at: new THREE.Vector3(0, 0.6, 0.2), chosen });
        continue;
      }
      // Rings out from the centre, each dot on its own golden turn.
      const k = dots.length;
      const a = k * 2.39996 + r() * 0.5;
      const d = 0.35 + 0.65 * Math.sqrt((k + 0.5) / HN.attempts) + (r() - 0.5) * 0.08;
      dots.push({ family: i, at: new THREE.Vector3(Math.cos(a) * d * rx, 0.6 + Math.sin(a) * d * ry, 0), chosen });
    }
  });
  return dots;
}

// Every attempt counted: a dot each, the chosen one gold in the middle.
export class Honesty extends Scene {
  name = "Every attempt, counted";
  summary = `All ${int(HN.attempts)} attempts, the failed ideas and the what-ifs included.`;
  private dots = scatter(false);
  private tall = false;
  private filter = 0;
  private chips: HTMLButtonElement[];
  private chosen = new Label(`Chosen <b class="text-gold">●</b>`, [0, 1.35, 0.2], "center");
  private legend = legendOf(LEGEND);

  // Sets the panel, the short tiles and the filter chips.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 1.2, 22], look: [0.4, 0.6, 0], drift: 0.7, shift: 0.1 };
    this.physics = { stiff: 9, damp: 1.2, flow: 0.22, spin: 0.03, mouse: 1.1 };
    this.dwell = 13;
    this.addLabel(this.chosen);
    this.panel.append(
      ...header(
        "Every attempt, <em>counted</em>",
        "Each dot is one thing we tried, from signal ideas to fund settings. Eight new ideas failed their tests. Only the gold dot became the fund.",
      ),
      // Short tiles: tried and chosen, ideas dropped, rule breaks.
      stats(
        stat(int(HN.attempts), "Tried, 1 chosen").el,
        stat(int(HN.ideas - HN.ideas_passed), "Ideas dropped").el,
        stat(int(D.headline.breaches), "Rule breaks").el,
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

  // Scatters wide or tall, and fits every dot with room for the label.
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
      Math.max(...ys) + 0.8,
      0,
    );
  }

  // Each attempt a dot, the chosen one a gold heart, the rest by kind.
  formation() {
    if (this.tall !== portrait()) this.lay(portrait());
    const f = blank();
    const keep = FILTERS[this.filter]!.keep;
    const r = seeded(19);
    let k = 0;
    // Each attempt a soft orb, the chosen one larger with a gold core.
    for (const d of this.dots) {
      const fam = HN.families[d.family]!;
      const on = keep(fam) ? 1 : 0.12;
      if (d.chosen) {
        f.put(k++, d.at.x, d.at.y, d.at.z, 1.4, C.gold, 2.2);
        k = ball(f, k, 220, d.at, 0.42, 0.3, C.gold, 1.3, r);
      } else if (fam.eligible) k = ball(f, k, 70, d.at, 0.24, 0.3, C.purple, 1.25 * on, r);
      else k = ball(f, k, 50, d.at, 0.2, 0.26, C.ice, 0.6 * on, r);
    }
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

  // Shows the label over the chosen dot.
  override enter() {
    this.showLabels();
  }

  // Shows every attempt again on the way out.
  override leave() {
    this.filter = 0;
    this.chips.forEach((c, i) => c.setAttribute("aria-pressed", String(i === 0)));
    this.lightLegend();
  }

  // Names the attempt under the pointer and what its family found.
  override hover(x: number, y: number) {
    const i = nearest(
      this.dots.map((d) => d.at),
      x,
      y,
      this.w.stage.camera,
      18,
    );
    if (i < 0) return null;
    const f = HN.families[this.dots[i]!.family]!;
    return `<strong>${short(f.what)}</strong><br>${int(f.attempts)} ${f.attempts > 1 ? "tries" : "try"} · ${prose(f.verdict)}`;
  }

  // Ripples the clicked attempt.
  override click(x: number, y: number) {
    const i = nearest(
      this.dots.map((d) => d.at),
      x,
      y,
      this.w.stage.camera,
      18,
    );
    if (i >= 0) this.w.sim.wave({ at: this.dots[i]!.at.clone(), amp: 1, speed: 6 });
  }
}
