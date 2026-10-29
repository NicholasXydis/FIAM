import * as THREE from "three";
import { caption, D, monthName, prose } from "../../shared/data";
import { blank } from "../gl/sim";
import { streams } from "../gl/shapes";
import { h } from "../../shared/dom";
import { coarse, corners } from "../layout";
import { asButton, box, chip, fold, Label, nearest } from "../ui";
import { ball, C, dust, header, Scene, type World } from "./scene";
import { seeded } from "../../shared/math";

// A date as day, month and year, as 28 October 2026.
const day = (d: string) => `${+d.slice(8, 10)} ${monthName(d.slice(0, 7))}`;

// The agents' data, and the core where the book sits and threads meet.
const A = D.agents;
const CORE = new THREE.Vector3(0, 0.3, 0);
// Each agent's colour: the advocate orange, crowd cyan, explainer gold.
const tone = (key: string) =>
  key === "advocate" ? C.orange : key === "crowd" ? C.cyan : key === "explainer" ? C.gold : C.purple;

// The AI desk: eight agents around the book, joined by flowing work.
export class Agents extends Scene {
  name = "The AI desk";
  summary = "Eight AI agents read, check and argue. None of them sets a position.";
  private nodes: THREE.Vector3[];
  private flow: THREE.Points<THREE.BufferGeometry, THREE.ShaderMaterial>;
  private card = box("w-[min(420px,calc(100vw-32px))] gap-2");
  private selected = -1;

  // Seats agents on a tilted ellipse, top first, threaded to the core.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 1.2, 20], look: [0, 0.3, 0], drift: 0.8, shift: 0.14 };
    this.physics = { stiff: 9, damp: 1.2, flow: 0.3, spin: 0.05, mouse: 1 };
    this.dwell = 13;
    this.nodes = A.map((_, i) => {
      const t = Math.PI / 2 + (i / A.length) * Math.PI * 2;
      return new THREE.Vector3(Math.cos(t) * 7.4, Math.sin(t) * 3.7 + 0.3, Math.sin(t) * -1.2);
    });
    // Each agent sends 90 dots in its colour and gets 26 gold ones back.
    this.flow = streams(
      A.flatMap((a, i) => {
        const p = this.nodes[i];
        const out = {
          a: p,
          b: CORE,
          c: p
            .clone()
            .multiplyScalar(0.45)
            .add(new THREE.Vector3(0, 1.6, 1.4)),
          color: tone(a.key),
          count: 90,
        };
        const back = {
          a: CORE,
          b: p,
          c: p
            .clone()
            .multiplyScalar(0.5)
            .add(new THREE.Vector3(0, -1.4, -1)),
          color: C.gold,
          count: 26,
        };
        return [out, back];
      }),
      0.2,
    );
    this.group.add(this.flow);
    // Name and model labels sit just under each agent's node.
    A.forEach((a, i) => {
      const at = this.nodes[i].clone().add(new THREE.Vector3(0, -1.05, 0));
      const html = `<b class="text-ink font-medium">${a.name}</b><br><span class="text-ink-3 text-[11px]">${a.model}</span>`;
      const label = this.addLabel(new Label(html, at, "center")).el;
      label.style.textAlign = "center";
      // Each name is a button too, so the keyboard can open its card.
      asButton(label, () => this.select(i === this.selected ? -1 : i)).setAttribute(
        "aria-label",
        `${a.name}, ${a.model}`,
      );
    });
    this.addLabel(new Label("The book", [0, -1.4, 0], "center", "big"));
    this.panel.append(
      ...header(
        `${A.length} AI colleagues, <em>none trade</em>`,
        "They work on our own machines. Each one reads or checks the final book, and none sets a trade.",
      ),
    );
    this.controls.append(this.card);
    this.select(-1);
    // Small screens: names only, the model and facts wait in the card.
    for (const [i, l] of this.labels.slice(0, A.length).entries())
      l.small = { html: `<b class="text-ink font-medium">${A[i].name}</b>` };
    this.frame = corners(-7.9, -4.6, -1.2, 7.9, 4.4, 1.2);
  }

  // Gold core of 8 soft balls; agent shells dim when another is picked.
  formation() {
    const f = blank();
    const r = seeded(91);
    const gold = new THREE.Color(C.gold);
    const ink = new THREE.Color(C.ink);
    let k = 0;
    for (let j = 0; j < 8; j++)
      k = ball(f, k, 325, CORE, 1.25, 0.3 + r() * 0.2, gold.clone().lerp(ink, j / 24), 0.8, r);
    this.nodes.forEach((n, i) => {
      const on = this.selected < 0 || this.selected === i ? 0.95 : 0.3;
      k = ball(f, k, 115, n, 0.55, 0.26, tone(A[i].key), on, r, true);
      k = ball(f, k, 345, n, 0.55, 0.26, C.ice, on, r, true);
    });
    dust(f, k, 37, 36, 1.4, 0.13);
    return f;
  }

  // Focuses agent i, or none at -1, and fills the card with what it does.
  select(i: number) {
    this.selected = i;
    this.flow.material.uniforms.uFocus.value = i < 0 ? -1 : i * 2;
    if (this.active) this.w.sim.update(this.formation());
    this.card.innerHTML = "";
    // With none picked, the card asks for a click.
    if (i < 0) {
      this.card.append(
        h("p", { class: "eyebrow" }, coarse() ? "Tap an agent" : "Click an agent"),
        h("p", { class: "text-[13px] text-ink-2" }, "See what it did, and how its work was checked."),
      );
      return;
    }
    const a = A[i];
    const head = h(
      "div",
      { class: "flex items-start justify-between gap-3" },
      h("div", {}, h("p", { class: "eyebrow" }, a.model), h("p", { class: "headline text-[28px]" }, a.name)),
      chip("All agents", () => this.select(-1)),
    );
    // What it found on the final book, the date and its key number.
    const found = [
      h("p", { class: "text-[13px] text-ink border-t border-line pt-1.5" }, prose(a.finding)),
      h(
        "div",
        { class: "flex justify-between gap-4 text-[13px]" },
        h("span", { class: "text-ink-3" }, `On ${day(a.date)}`),
        h("b", { class: "figure text-ink font-medium text-right" }, caption(a.number)),
      ),
    ];
    this.card.append(head, h("p", { class: "text-[14px] text-ink-2" }, prose(a.does)), ...found);
    // Small screens fold the facts behind a Details chip.
    this.card.classList.remove("open");
    fold(this.card, head, [...this.card.children].slice(2), "Details");
  }

  // Shows the agents' labels and the book's.
  override enter() {
    this.showLabels();
  }

  // Clears the focus on the way out.
  override leave() {
    this.selected = -1;
    this.flow.material.uniforms.uFocus.value = -1;
  }

  // Names the agent within 46 px of the pointer, or the book at the core.
  override hover(x: number, y: number) {
    const i = nearest(this.nodes, x, y, this.w.stage.camera, 46);
    if (i >= 0)
      return `<strong>${A[i].name}</strong><br>${prose(A[i].does)}<br><span class="muted">Click for details</span>`;
    if (nearest([CORE], x, y, this.w.stage.camera, 60) < 0) return null;
    return "<strong>The final book</strong><br>The agents question and explain it. The optimizer alone sets every weight.";
  }

  // Focuses the clicked agent and ripples it; a second click clears it.
  override click(x: number, y: number) {
    const i = nearest(this.nodes, x, y, this.w.stage.camera, 46);
    if (i < 0) return;
    this.select(i === this.selected ? -1 : i);
    this.w.sim.wave({ at: this.nodes[i].clone(), amp: 0.9, speed: 7 });
  }

  // Moves the flow along its threads and sizes its dots to the screen.
  override tick(_dt: number, t: number) {
    this.flow.material.uniforms.uTime.value = t;
    this.flow.material.uniforms.uScale.value = this.w.stage.pixel;
  }
}
