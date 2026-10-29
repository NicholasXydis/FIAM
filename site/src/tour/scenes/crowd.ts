import gsap from "gsap";
import * as THREE from "three";
import { D, num, ordinal, prose } from "../../shared/data";
import { blank } from "../gl/sim";
import { rim } from "../gl/shapes";
import { Flock } from "../physics/flock";
import { h } from "../../shared/dom";
import { corners } from "../layout";
import { box, chip, fold, legendOf, nearest, stat, swatch } from "../ui";
import { ball, C, dust, header, Scene, stats, type World } from "./scene";
import { seeded } from "../../shared/math";

// The crowd's numbers from the build.
const K = D.crowd;
// The six personas' colours, one per herd.
const PERSONA = [0x5cc8e0, 0x7fd1ae, C.gold, 0xe07a3f, 0xc792ea, 0x8ab4f8];
// What the copycat funds are handed, three recipes, and their colours.
const RECIPES = [
  { label: "our research recipe", color: C.gold },
  { label: "the 2026 brief", color: 0x8ab4f8 },
  { label: "the 2025 case", color: 0xc792ea },
];
// A colour as CSS hex, for the legend's dots.
const hex = (c: number) => `#${c.toString(16).padStart(6, "0")}`;
// A string with its first letter made a capital.
const title = (s: string) => s[0].toUpperCase() + s.slice(1);
// A persona's line for its agents' hover, as one sentence.
const persona = (i: number) => title(prose(K.personas[i].client.replace(/:\s/, ", ")));
// Spacing of the 10 by 10 stock cards.
const SPACING = 0.86;
// Seconds each lure lasts before the herds move on.
const LURE = 3.2;

// The crowd scene: agents flock to the crowd's favourite cards.
export class Crowd extends Scene {
  name = "The AI crowd";
  summary = `Sixty AI traders flock to their favourite stocks, yet our crowd beta is only ${num(K.beta)}.`;
  private flock: Flock;
  private nodes: THREE.Vector3[] = [];
  private liked: number[] = [];
  private chance = new Set<number>();
  private chips: HTMLButtonElement[] = [];
  private groups: { label: string; herds: number[]; lines: number[] }[] = [];
  private legend: ReturnType<typeof legendOf>;
  private next = 0;
  // The tour's clock as tick last saw it, so a lure times itself by it.
  private now = 0;

  // Lays out 100 cards, marks 10 chance picks, and forms the herds.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 0.2, 19], look: [0, -0.7, 0], drift: 0.8, shift: 0.12 };
    this.physics = { stiff: 9, damp: 1.2, flow: 0.25, spin: 0.03, mouse: 1 };
    this.dwell = 14;
    const r = seeded(11);
    // A seeded shuffle picks the favourites and the 10 chance would.
    const order = Array.from({ length: 100 }, (_, i) => i).sort(() => r() - 0.5);
    const share = K.favourites_pct;
    this.liked = order.slice(0, share);
    this.chance = new Set(order.slice(0, 10));
    // Lay the 100 cards out on a 10 by 10 grid.
    for (let i = 0; i < 100; i++) {
      this.nodes.push(new THREE.Vector3(((i % 10) - 4.5) * SPACING, (4.5 - Math.floor(i / 10)) * SPACING, 0));
    }
    // A faint torus marks each of the 10 chance picks.
    for (const i of this.chance) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.36, 0.01, 8, 48), rim(C.ink, 0.35, 0.6));
      ring.position.copy(this.nodes[i]);
      this.group.add(ring);
    }
    // Persona herds split the agents evenly, recipe herds the copycats.
    const herds: number[] = [];
    PERSONA.forEach((_, p) => herds.push(...Array(K.agents / PERSONA.length).fill(p)));
    RECIPES.forEach((_, j) => herds.push(...Array(K.copycats / RECIPES.length).fill(PERSONA.length + j)));
    this.flock = new Flock(
      herds,
      [...PERSONA, ...RECIPES.map((x) => x.color)].map((c) => new THREE.Color(c)),
    );
    this.group.add(this.flock.mesh, this.flock.lines);
    this.panel.append(
      ...header(
        "How AI <em>crowds</em>",
        `AI traders may crowd the same stocks, so we built ${K.agents + K.copycats} that pick from nameless cards. Our longs average their ${ordinal(K.long_pct)} percentile, shorts the ${ordinal(K.short_pct)}.`,
      ),
      stats(
        stat(num(K.beta), "Beta to the crowd").el,
        stat(`${K.agents} AIs`, `Think like ${Math.round(K.effective_voters)}`).el,
        stat(`${num(K.sell_10bn_pct, 2)}%`, "If the crowd sells $10bn").el,
      ),
    );
    // A colour wheel of several colours, for a group's legend dot.
    const mix = (colors: number[]) => `conic-gradient(${colors.map(hex).join(", ")})`;
    // The legend, one line each, its dots in the agents' own colours.
    this.legend = legendOf([
      `${swatch(mix(PERSONA))}AI investors · ${K.agents}, in ${K.personas.length} styles, herding LSV ${num(K.lsv, 3)}`,
      `${swatch(mix(RECIPES.map((x) => x.color)))}AI copycats · ${K.copycats}, handed ${RECIPES.length} recipes`,
      `${swatch("var(--gold)")}Gold balls · the crowd's favourites`,
      `${swatch("var(--ink)", true)}Rings · the 10 chance would pick`,
    ]);
    // Three buttons: everyone, the investor agents and the copycats.
    this.groups = [
      { label: "Everyone", herds: [], lines: [0, 1, 2, 3] },
      { label: "AI investors", herds: PERSONA.map((_, i) => i), lines: [0] },
      { label: "AI copycats", herds: RECIPES.map((_, j) => PERSONA.length + j), lines: [1] },
    ];
    this.chips = this.groups.map((g, i) => chip(g.label, () => this.pick(i), i === 0));
    this.controls.append(
      box(
        "w-[min(460px,calc(100vw-32px))] gap-2",
        h("div", { class: "flex flex-wrap gap-1.5" }, ...this.chips),
        this.legend.el,
      ),
    );
    this.pick(0);
    // Small screens: the group chips scroll, the legend folds behind Key.
    const glass = this.controls.firstElementChild as HTMLElement;
    const row = glass.firstElementChild as HTMLElement;
    row.classList.add("row");
    fold(glass, row, [glass.lastElementChild!], "Key");
    this.frame = corners(-4.4, -4.4, 0, 4.4, 4.4, 0.9);
    this.zoomCap = 1.35;
  }

  // Lights one group of agents and its legend line; the rest dim.
  pick(group: number) {
    const g = this.groups[group];
    if (!g) return;
    this.flock.focus = g.herds;
    this.chips.forEach((b, i) => b.setAttribute("aria-pressed", String(i === group)));
    this.legend.light(g.lines);
  }

  // The 10 by 10 cards as balls, favourites bigger, brighter and gold.
  formation() {
    const f = blank();
    const r = seeded(61);
    const liked = new Set(this.liked);
    let k = 0;
    // Favourites are big, bright and gold; the rest small and cyan.
    this.nodes.forEach((n, i) => {
      const fav = liked.has(i);
      k = ball(f, k, 40, n, fav ? 0.3 : 0.2, fav ? 0.42 : 0.28, fav ? C.gold : C.cyan, fav ? 1.1 : 0.45, r);
    });
    dust(f, k, 31, 36, 1.4, 0.13);
    return f;
  }

  // Each herd chases a different favourite, moving on every few seconds.
  private wander(t: number) {
    this.flock.goals.forEach((g, i) => {
      const node = this.nodes[this.liked[(i * 5 + Math.floor(t / LURE) * 3) % this.liked.length]];
      gsap.to(g, { x: node.x, y: node.y, z: 0.9, duration: 1.2 });
    });
  }

  // Shows the labels and starts the lures.
  override enter() {
    this.showLabels();
    this.next = 0;
  }

  // Moves the lure every few seconds and the flock every frame.
  override tick(dt: number, t: number) {
    this.now = t;
    // Once a lure's time is up, send every herd to a new card.
    if (t > this.next) {
      this.next = t + LURE;
      this.wander(t);
    }
    this.flock.step(dt, t);
  }

  // Names the agent within 18 px, or else the stock within 22 px.
  override hover(x: number, y: number) {
    const camera = this.w.stage.camera;
    const bird = nearest(
      this.flock.birds.map((b) => b.p),
      x,
      y,
      camera,
      18,
    );
    // An agent: say which persona or recipe its herd follows.
    if (bird >= 0) {
      const herd = this.flock.birds[bird].herd;
      if (herd < PERSONA.length) return `<strong>Retail AI investor</strong><br>${persona(herd)}`;
      return `<strong>Copycat fund</strong><br>Handed ${RECIPES[herd - PERSONA.length].label}`;
    }
    const node = nearest(this.nodes, x, y, camera, 22);
    if (node < 0) return null;
    const fav = this.liked.includes(node);
    const ring = this.chance.has(node)
      ? '<br><span class="muted">The ring marks one of the 10 chance would pick</span>'
      : "";
    return `<strong>A stock card</strong><br>${fav ? "A crowd favourite. Click to lure the crowd here" : "Not a crowd favourite"}${ring}`;
  }

  // A click lures all herds to a favourite for 5 s, the brief's crowding.
  override click(x: number, y: number) {
    const node = nearest(this.nodes, x, y, this.w.stage.camera, 22);
    if (node < 0 || !this.liked.includes(node)) return;
    const at = this.nodes[node];
    for (const g of this.flock.goals) gsap.to(g, { x: at.x, y: at.y, z: 0.9, duration: 0.6 });
    this.next = this.now + 5;
    this.w.sim.wave({ at: at.clone(), amp: 1.2, speed: 8 });
    this.w.sound.tick(0.9, 0.9);
  }
}
