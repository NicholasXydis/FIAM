import gsap from "gsap";
import * as THREE from "three";
import { D, int, num, pct, plus, prose } from "../data";
import { Formation } from "../gl/sim";
import { rim } from "../gl/shapes";
import { Flock } from "../physics/flock";
import { chip, h, Label, nearest, stat, swatch } from "../ui";
import { ball, C, dust, rand, Scene, type World } from "./scene";

const K = D.crowd;
const PERSONA = [0x5cc8e0, 0x7fd1ae, 0xf2c14e, 0xe07a3f, 0xc792ea, 0x8ab4f8];
const RECIPES = [
  { key: "v1", label: "our recipe", color: 0xf2c14e },
  { key: "brief_2026", label: "the 2026 brief", color: 0x8ab4f8 },
  { key: "case_2025", label: "the 2025 case", color: 0xc792ea },
];
const SPACING = 0.86;
const LURE = 3.2;
const hex = (c: number) => `#${c.toString(16).padStart(6, "0")}`;
const title = (s: string) => s[0].toUpperCase() + s.slice(1);
const persona = (i: number) => `${title(K.personas[i].key)}. Their client ${prose(K.personas[i].client)}`;

export class Crowd extends Scene {
  name = "The AI crowd";
  summary = "Sixty AI investors flock to their favourite stocks. Some of them are ours.";
  private flock: Flock;
  private nodes: THREE.Vector3[] = [];
  private liked: number[] = [];
  private chance = new Set<number>();
  private chips: HTMLButtonElement[] = [];
  private about = h("p", { class: "text-[13px] text-ink-2 min-h-[3.2em]" });
  private next = 0;

  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 0.2, 19], look: [0, -0.7, 0], drift: 0.8, shift: 0.12 };
    this.physics = { stiff: 9, damp: 1.2, flow: 0.25, spin: 0.03, mouse: 1 };
    this.dwell = 14;
    const r = rand(11);
    const order = Array.from({ length: 100 }, (_, i) => i).sort(() => r() - 0.5);
    const share = Math.round(K.longs_in_favourites * 100);
    this.liked = order.slice(0, share);
    this.chance = new Set(order.slice(0, 10));
    for (let i = 0; i < 100; i++) {
      this.nodes.push(new THREE.Vector3(((i % 10) - 4.5) * SPACING, (4.5 - Math.floor(i / 10)) * SPACING, 0));
    }
    for (const i of this.chance) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.36, 0.01, 8, 48), rim(C.ink, 0.35, 0.6));
      ring.position.copy(this.nodes[i]);
      this.group.add(ring);
    }
    const herds: number[] = [];
    PERSONA.forEach((_, p) => herds.push(...Array(K.agents / PERSONA.length).fill(p)));
    RECIPES.forEach((_, j) => herds.push(...Array(K.copycats / RECIPES.length).fill(PERSONA.length + j)));
    this.flock = new Flock(
      herds,
      [...PERSONA, ...RECIPES.map((x) => x.color)].map((c) => new THREE.Color(c)),
    );
    this.group.add(this.flock.mesh, this.flock.lines);
    const top = 5.5 * SPACING;
    this.addLabel(
      new Label(`${swatch("var(--gold)")}Crowd favourite · ${share} of 100`, [4.6 * SPACING, top + 0.25, 0], "right"),
    );
    this.addLabel(
      new Label(`${swatch("var(--ink)", true)}Chance would give 10`, [4.6 * SPACING, top - 0.25, 0], "right"),
    );
    this.addLabel(new Label("100 of our longs", [-4.8 * SPACING, top + 0.25, 0], "left"));
    const test = K.copycat_test.brief_2026;
    this.panel.append(
      h(
        "p",
        { class: "eyebrow", "data-rise": true },
        `The AI crowd · ${int(K.picks)} picks · ${K.models.join(" and ")}`,
      ),
      h("h2", {
        class: "headline text-[44px] md:text-[56px]",
        "data-rise": true,
        html: "Who trades <em>against us?</em>",
      }),
      h(
        "p",
        { class: "body", "data-rise": true },
        `The brief warns that AI agents will crowd into the same names, so we built the crowd. ${K.agents} retail AI investors with six personas and ${K.copycats} copycat funds, each handed one paragraph of a strategy, pick from anonymous stock cards with no names or dates. Of every 100 of our longs, ${share} are among their favourites, against 10 by chance. Click a gold stock to lure the whole crowd to it.`,
      ),
      h(
        "div",
        { class: "stats", "data-rise": true },
        stat(pct(K.longs_in_favourites, 0), "of our longs are crowd favourites, against 10% by chance").el,
        stat(`${num(test.longs)}×`, "how often copycats given only the brief buy our longs, against chance").el,
        stat(num(K.effective_voters, 1), `independent votes, all that ${K.agents} AI investors add up to`).el,
        stat(plus(K.crowd_beta), `our returns' loading on the crowd's favourites, t = ${num(K.crowd_t, 1)}`).el,
      ),
    );
    this.chips.push(chip("Everyone", () => this.pickHerd(-1), true));
    K.personas.forEach((p, i) =>
      this.chips.push(chip(`${swatch(hex(PERSONA[i]))}${title(p.key)}`, () => this.pickHerd(i), false)),
    );
    RECIPES.forEach((x, j) => {
      this.chips.push(
        chip(`${swatch(hex(x.color))}Copycats with ${x.label}`, () => this.pickHerd(PERSONA.length + j), false),
      );
    });
    this.controls.append(
      h(
        "div",
        { class: "glass rounded-2xl px-4 py-3 w-[min(460px,calc(100vw-32px))] flex flex-col gap-2" },
        h("div", { class: "flex flex-wrap gap-1.5" }, ...this.chips),
        this.about,
      ),
    );
    this.pickHerd(-1);
  }

  pickHerd(herd: number) {
    this.flock.focus = herd;
    this.chips.forEach((b, i) => b.setAttribute("aria-pressed", String(i === herd + 1)));
    if (herd < 0) {
      this.about.textContent = `Retail agents differ more by what they see than by who they are told to be. Agents shown the same data agree at ${num(K.same_information)}, agents given the same persona at ${num(K.same_persona)}. Asked the same card twice, they answer the same way ${pct(K.rerun_agreement, 0)} of the time.`;
    } else if (herd < PERSONA.length) {
      this.about.textContent = persona(herd);
    } else {
      const x = RECIPES[herd - PERSONA.length];
      const t = K.copycat_test[x.key];
      this.about.textContent = `Copycats handed ${x.label} buy our longs ${num(t.longs)}× and short our shorts ${num(t.shorts)}× as often as chance.`;
    }
  }

  formation() {
    const f = new Formation();
    const r = rand(61);
    const liked = new Set(this.liked);
    let k = 0;
    this.nodes.forEach((n, i) => {
      const fav = liked.has(i);
      k = ball(f, k, 40, n, fav ? 0.3 : 0.2, fav ? 0.42 : 0.28, fav ? C.gold : C.cyan, fav ? 1.1 : 0.45, r);
    });
    dust(f, k, 31, 36, 1.4, 0.13);
    return f;
  }

  // Every herd chases a different favourite, and moves on every few seconds.
  private wander(t: number) {
    this.flock.goals.forEach((g, i) => {
      const node = this.nodes[this.liked[(i * 5 + Math.floor(t / LURE) * 3) % this.liked.length]];
      gsap.to(g, { x: node.x, y: node.y, z: 0.9, duration: 1.2 });
    });
  }

  enter() {
    for (const l of this.labels) l.shown = true;
    this.next = 0;
  }

  tick(dt: number, t: number) {
    if (t > this.next) {
      this.next = t + LURE;
      this.wander(t);
    }
    this.flock.step(dt, t);
  }

  hover(x: number, y: number) {
    const camera = this.w.stage.camera;
    const bird = nearest(
      this.flock.birds.map((b) => b.p),
      x,
      y,
      camera,
      18,
    );
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
    return `<strong>One of our longs</strong><br>${fav ? "A crowd favourite. Click to lure the crowd here" : "Not a crowd favourite"}${ring}`;
  }

  // A click on a favourite pulls every herd to it, the crowding the brief warns about, for a few seconds.
  click(x: number, y: number) {
    const node = nearest(this.nodes, x, y, this.w.stage.camera, 22);
    if (node < 0 || !this.liked.includes(node)) return;
    const at = this.nodes[node];
    for (const g of this.flock.goals) gsap.to(g, { x: at.x, y: at.y, z: 0.9, duration: 0.6 });
    this.next = this.time + 5;
    this.w.sim.wave({ at: at.clone(), amp: 1.2, speed: 8 });
    this.w.sound.tick(0.9, 0.9);
  }
}
