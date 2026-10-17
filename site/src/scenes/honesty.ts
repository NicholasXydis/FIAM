import * as THREE from "three";
import { caption, D, int, num, pct, prose } from "../data";
import { Formation, N } from "../gl/sim";
import { chip, h, Label, screen, stat } from "../ui";
import { C, dust, Scene, type World } from "./scene";

const HN = D.honesty;
const GOLDEN = Math.PI * (3 - Math.sqrt(5));
const DOT = 0.15;
const SHIPPED = HN.families.findIndex((f) => f.verdict.startsWith("Shipped"));
const FILTERS = [
  { name: `All ${int(HN.attempts)}`, keep: () => true },
  { name: `Shippable ${int(HN.eligible)}`, keep: (f: (typeof HN.families)[number]) => f.eligible },
  { name: "Research and controls", keep: (f: (typeof HN.families)[number]) => !f.eligible },
];
const centre = { x: 0, y: 0, front: true };
const rim = { x: 0, y: 0, front: true };
const edge = new THREE.Vector3();

export class Honesty extends Scene {
  name = "Every attempt, counted";
  summary = `All ${int(HN.attempts)} fits we ran before choosing, and the odds that the edge is real.`;
  private centres: THREE.Vector3[] = [];
  private radii: number[] = [];
  private filter = 0;
  private chips: HTMLButtonElement[];

  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 1.2, 22], look: [0.4, 0.6, 0], drift: 0.7, shift: 0.1 };
    this.physics = { stiff: 9, damp: 1.2, flow: 0.22, spin: 0.03, mouse: 1.1 };
    this.dwell = 13;
    const order = HN.families.map((_, i) => i).sort((a, b) => HN.families[b].attempts - HN.families[a].attempts);
    const placed = order.map((i) => ({ i, r: DOT * 0.55 * Math.sqrt(HN.families[i].attempts) + 0.25 }));
    const big = placed[0];
    this.centres[big.i] = new THREE.Vector3(6.2, 0.4, 0);
    const left = -6.6;
    const right = 6.2 - big.r - 0.8;
    let x = left;
    let y = 4.3;
    let row = 0;
    for (const p of placed.slice(1)) {
      if (x + p.r * 2 > right) {
        x = left;
        y -= row + 0.5;
        row = 0;
      }
      this.centres[p.i] = new THREE.Vector3(x + p.r, y - p.r, 0);
      x += p.r * 2 + 0.5;
      row = Math.max(row, p.r * 2);
    }
    placed.forEach((p) => (this.radii[p.i] = p.r));
    const above = (i: number) => this.centres[i].clone().add(new THREE.Vector3(0, this.radii[i] + 0.45, 0));
    this.addLabel(new Label(`Chosen · the twelve-signal score <b class="text-gold">●</b>`, above(SHIPPED), "center"));
    const crown = this.centres[big.i].clone().add(new THREE.Vector3(0, big.r + 0.45, 0));
    this.addLabel(new Label(caption(HN.families[big.i].what), crown, "center"));
    this.panel.append(
      h("p", { class: "eyebrow", "data-rise": true }, "The honest reading"),
      h("h2", {
        class: "headline text-[44px] md:text-[56px]",
        "data-rise": true,
        html: `${int(HN.attempts)} attempts. <em>Every one counted.</em>`,
      }),
      h(
        "p",
        { class: "body", "data-rise": true },
        `Each dot is one fit we ran before choosing, from signal sets and hedges to models and controls. Bright dots are the ${int(HN.eligible)} designs we could have shipped. Adjusted for this many tries, the chance the edge is real is ${pct(HN.dsr_all, 0)}, or ${pct(HN.dsr_eligible, 0)} counting only the shippable ones. Most of the return came in 2021 and 2022, and since 2023 the edge has been flat. Hover a cluster to see what it tried.`,
      ),
      h(
        "div",
        { class: "stats", "data-rise": true },
        stat(pct(HN.dsr_all, 0), `chance the edge is real after all ${int(HN.attempts)} tries`).el,
        stat(num(HN.first_half_ir), "IR in 2021 and 2022").el,
        stat(num(HN.second_half_ir), "IR from 2023 to 2026").el,
        stat(num(HN.check_2016_2020_ir), "IR of the same book from 2016 to 2020").el,
      ),
    );
    this.chips = FILTERS.map((f, i) => chip(f.name, () => this.only(i), i === 0));
    this.controls.append(
      h(
        "div",
        {
          class:
            "glass rounded-2xl px-4 py-3 w-[min(420px,calc(100vw-32px))] flex flex-col gap-2 text-[13px] text-ink-2",
        },
        h("div", { class: "flex flex-wrap gap-1.5" }, ...this.chips),
        h("p", { class: "eyebrow pt-1" }, "Limits"),
        h(
          "p",
          {},
          "A backtest anyone can rerun, not a live record. Costs are modelled, not observed. Much of the return comes from one style, profitability, and a junk rally, when unprofitable stocks fly, is the risk this book fears most.",
        ),
      ),
    );
  }

  formation() {
    const f = new Formation();
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

  only(filter: number) {
    if (filter === this.filter) return;
    this.filter = filter;
    this.chips.forEach((c, i) => c.setAttribute("aria-pressed", String(i === filter)));
    this.w.sim.show(this.formation(), 0.5, 0.8);
    this.w.sound.tick(1, 0.6);
  }

  enter() {
    for (const l of this.labels) l.shown = true;
  }

  leave() {
    this.filter = 0;
    this.chips.forEach((c, i) => c.setAttribute("aria-pressed", String(i === 0)));
  }

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

  hover(x: number, y: number) {
    const i = this.cluster(x, y);
    if (i < 0) return null;
    const f = HN.families[i];
    const kind = f.eligible ? "shippable" : "research or control";
    return `<strong>${caption(f.what)}</strong><br>${int(f.attempts)} attempt${f.attempts > 1 ? "s" : ""} · ${kind}<br><span class="muted">${prose(f.result)}</span><br>Verdict · ${prose(f.verdict)}`;
  }

  click(x: number, y: number) {
    const i = this.cluster(x, y);
    if (i >= 0) this.w.sim.wave({ at: this.centres[i].clone(), amp: 1, speed: 6 });
  }
}
