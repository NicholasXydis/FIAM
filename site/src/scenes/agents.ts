import * as THREE from "three";
import { caption, D, prose } from "../data";
import { Formation } from "../gl/sim";
import { streams } from "../gl/shapes";
import { chip, h, Label, nearest } from "../ui";
import { ball, C, dust, rand, Scene, type World } from "./scene";

const A = D.agents;
const CORE = new THREE.Vector3(0, 0.3, 0);
const tone = (key: string) =>
  key === "advocate" ? C.orange : key === "crowd" ? C.cyan : key === "explainer" ? C.gold : C.purple;
const models = [...new Set(A.map((a) => a.model))].filter((m) => !m.includes(" and "));

export class Agents extends Scene {
  name = "The AI desk";
  summary = "Seven local AI agents read, check and argue. None of them sets a position.";
  private nodes: THREE.Vector3[];
  private flow: THREE.Points<THREE.BufferGeometry, THREE.ShaderMaterial>;
  private card = h("div", {
    class: "glass rounded-2xl px-4 py-3 w-[min(420px,calc(100vw-32px))] flex flex-col gap-2",
  });
  private selected = -1;

  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 1.2, 20], look: [0, 0.3, 0], drift: 0.8, shift: 0.14 };
    this.physics = { stiff: 9, damp: 1.2, flow: 0.3, spin: 0.05, mouse: 1 };
    this.dwell = 13;
    this.nodes = A.map((_, i) => {
      const t = Math.PI / 2 + (i / A.length) * Math.PI * 2;
      return new THREE.Vector3(Math.cos(t) * 7.4, Math.sin(t) * 3.7 + 0.3, Math.sin(t) * -1.2);
    });
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
    A.forEach((a, i) => {
      const at = this.nodes[i].clone().add(new THREE.Vector3(0, -1.05, 0));
      const html = `<b class="text-ink font-medium">${a.name}</b><br><span class="text-ink-3 text-[10px]">${a.model}</span>`;
      this.addLabel(new Label(html, at, "center")).el.style.textAlign = "center";
    });
    this.addLabel(new Label("The book", [0, -1.4, 0], "center", "big"));
    this.panel.append(
      h("p", { class: "eyebrow", "data-rise": true }, "The desk · every model runs on our own machine"),
      h("h2", {
        class: "headline text-[44px] md:text-[56px]",
        "data-rise": true,
        html: `${A.length} AI colleagues. <em>None sets a position.</em>`,
      }),
      h(
        "p",
        { class: "body", "data-rise": true },
        "Around the book sit the agents. They read filings, check the rules, argue against the book and explain it, with company names, tickers and dates hidden wherever memory could cheat. Code checks every number they quote. Click an agent to see what it did.",
      ),
    );
    this.controls.append(this.card);
    this.select(-1);
  }

  formation() {
    const f = new Formation();
    const r = rand(91);
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

  select(i: number) {
    this.selected = i;
    this.flow.material.uniforms.uFocus.value = i < 0 ? -1 : i * 2;
    if (this.active) this.w.sim.update(this.formation());
    this.card.innerHTML = "";
    if (i < 0) {
      this.card.append(
        h("p", { class: "eyebrow" }, "Click an agent"),
        h(
          "p",
          { class: "text-[13px] text-ink-2" },
          `${A.map((a) => a.name).join(" · ")}. They run on ${models.join(" and ")}, all on our own machine.`,
        ),
      );
      return;
    }
    const a = A[i];
    this.card.append(
      h(
        "div",
        { class: "flex items-start justify-between gap-3" },
        h("div", {}, h("p", { class: "eyebrow" }, a.model), h("p", { class: "headline text-[28px]" }, a.name)),
        chip("All agents", () => this.select(-1)),
      ),
      h("p", { class: "text-[14px] text-ink-2" }, prose(a.does)),
      ...a.facts.map(([k, v]) =>
        h(
          "div",
          { class: "flex justify-between gap-4 text-[13px] border-t border-line pt-1.5" },
          h("span", { class: "text-ink-3" }, caption(k)),
          h("b", { class: "figure text-ink font-medium text-right" }, caption(v)),
        ),
      ),
    );
    if (a.key === "explainer") {
      this.card.append(
        h(
          "p",
          { class: "text-[13px] text-ink-2 border-t border-line pt-2" },
          "Its reasons for the September book are in the next scene.",
        ),
        chip("See the September book →", () => this.w.next()),
      );
    }
  }

  enter() {
    for (const l of this.labels) l.shown = true;
  }

  leave() {
    this.selected = -1;
    this.flow.material.uniforms.uFocus.value = -1;
  }

  hover(x: number, y: number) {
    const i = nearest(this.nodes, x, y, this.w.stage.camera, 46);
    if (i >= 0)
      return `<strong>${A[i].name}</strong><br>${prose(A[i].does)}<br><span class="muted">Click for details</span>`;
    if (nearest([CORE], x, y, this.w.stage.camera, 60) < 0) return null;
    return "<strong>The final book</strong><br>The agents inform it. The optimizer alone sets every weight.";
  }

  click(x: number, y: number) {
    const i = nearest(this.nodes, x, y, this.w.stage.camera, 46);
    if (i < 0) return;
    this.select(i === this.selected ? -1 : i);
    this.w.sim.wave({ at: this.nodes[i].clone(), amp: 0.9, speed: 7 });
  }

  tick(_dt: number, t: number) {
    this.flow.material.uniforms.uTime.value = t;
    this.flow.material.uniforms.uScale.value = this.w.stage.pixel;
  }
}
