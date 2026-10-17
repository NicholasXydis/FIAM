import gsap from "gsap";
import * as THREE from "three";
import { D, monthName, num, pct, signed } from "../data";
import { Formation } from "../gl/sim";
import { glow, tube } from "../gl/shapes";
import { chip, h, Label, rayAt, stat, swatch } from "../ui";
import { C, dust, rand, Scene, type World } from "./scene";

const R = D.race;
const STEPS = R.book.length;
const X0 = -9.5;
const X1 = 8.2;
const FLOOR = -3.6;
const BACK = -2.6;
const xAt = (i: number) => X0 + ((X1 - X0) * i) / (STEPS - 1);
const yAt = (g: number) => Math.log(g) * 8.5 - 2.2;
const CRASH = D.months.indexOf("2022-09") + 1;
const SERIES = [
  { key: "book", label: "Final book", color: C.gold, mark: "var(--m-ours)", z: 0, radius: 0.075, dust: 3600 },
  { key: "market", label: "S&amp;P 500", color: C.purple, mark: "var(--m-brand)", z: -1.1, radius: 0.045, dust: 2200 },
  {
    key: "hurdle",
    label: "Hurdle, T-bill + 4%",
    color: C.ink,
    mark: "var(--ink-3)",
    z: -2.2,
    radius: 0.035,
    dust: 1000,
  },
] as const;
const YEARS = Object.keys(D.years);
const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
const hit = new THREE.Vector3();

export class Race extends Scene {
  name = "The race";
  summary = `$1 in January 2021 became $${R.book[STEPS - 1].toFixed(2)} after every cost.`;
  private lines: THREE.Mesh<THREE.TubeGeometry, THREE.ShaderMaterial>[] = [];
  private ends: Label[] = [];
  private cross: THREE.Mesh<THREE.BoxGeometry, THREE.MeshBasicMaterial>;
  private ring: THREE.Mesh<THREE.PlaneGeometry, THREE.ShaderMaterial>;
  private chips: HTMLButtonElement[] = [];
  private year = "";
  private fired = false;
  private readout = {
    book: stat("", "Final book"),
    market: stat("", "S&P 500"),
    hurdle: stat("", "Hurdle"),
    active: stat("", "Above the hurdle"),
  };
  private scope = h("p", { class: "eyebrow" });
  private callout: Label;

  constructor(w: World) {
    super(w);
    this.shot = { eye: [2, 1.4, 24.5], look: [-0.4, -0.2, -1], drift: 0.6, shift: 0.1 };
    this.physics = { stiff: 8, damp: 1.25, flow: 0.18, spin: 0.02, mouse: 0.7 };
    this.dwell = 13;
    for (const s of SERIES) {
      const pts = R[s.key].map((g, i) => new THREE.Vector3(xAt(i), yAt(g), s.z));
      const line = tube(pts, s.color, s.radius, s.key === "book" ? 1.6 : 1, s.key === "hurdle");
      this.lines.push(line);
      this.group.add(line);
      const end = R[s.key][STEPS - 1];
      const text = `${swatch(s.mark)}${s.label} <b class="text-ink">$${end.toFixed(2)}</b>`;
      this.ends.push(this.addLabel(new Label(text, [X1 + 0.35, yAt(end), s.z], "left")));
    }
    for (const g of [1, 1.5, 2, 2.5]) this.addLabel(new Label(`$${g.toFixed(2)}`, [X0 - 0.3, yAt(g), BACK], "right"));
    for (const y of YEARS)
      this.addLabel(new Label(y, [xAt(D.months.indexOf(`${y}-01`)) + 0.15, FLOOR + 0.35, BACK], "left"));
    this.cross = new THREE.Mesh(
      new THREE.BoxGeometry(0.02, 10.5, 0.02),
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0 }),
    );
    this.cross.userData.keep = true;
    this.ring = glow(C.orange, 6, 0);
    this.ring.userData.keep = true;
    this.group.add(this.cross, this.ring);
    const crash = D.years["2022"];
    this.callout = this.addLabel(
      new Label(
        `<span class="text-orange">2022</span> · S&amp;P 500 <b class="text-ink">${signed(crash.market)}</b> · Final book <b class="text-ink">${signed(crash.strategy)}</b>`,
        [xAt(CRASH), yAt(R.book[CRASH]) + 2.3, 0],
        "center",
      ),
    );
    const head = D.headline;
    this.panel.append(
      h("p", { class: "eyebrow", "data-rise": true }, `Growth of $1 · ${D.window} · after every cost`),
      h("h2", {
        class: "headline text-[44px] md:text-[56px]",
        "data-rise": true,
        html: `$1 became <em>$${R.book[STEPS - 1].toFixed(2)}</em>`,
      }),
      h(
        "p",
        { class: "body", "data-rise": true },
        `A dollar in the final book from January 2021, after every modelled cost, next to the S&P 500 and the hurdle the brief sets. The information ratio is ${num(head.ir)} and alpha is ${pct(head.alpha)} a year with a t of ${num(head.alpha_t)}. Hover the chart to read any month.`,
      ),
      this.scope,
      h("div", { class: "stats", "data-rise": true }, ...Object.values(this.readout).map((s) => s.el)),
    );
    this.chips.push(chip("All years", () => this.focus(""), true));
    for (const y of YEARS) this.chips.push(chip(y, () => this.focus(y), false));
    this.controls.append(
      h(
        "div",
        { class: "flex flex-wrap justify-end gap-2" },
        ...this.chips,
        chip("Draw again", () => this.draw()),
      ),
    );
    this.focus("", false);
  }

  formation() {
    const f = new Formation();
    const r = rand(31);
    let k = 0;
    const tint = new THREE.Color();
    for (const s of SERIES) {
      const g = R[s.key];
      const spread = s.key === "book" ? 0.22 : 0.16;
      tint.setHex(s.color);
      for (let j = 0; j < s.dust; j++, k++) {
        const t = r() * (STEPS - 1);
        const i = Math.floor(t);
        const y = yAt(g[i] + (g[Math.min(i + 1, STEPS - 1)] - g[i]) * (t - i));
        const gx = (r() + r() + r() - 1.5) * spread;
        const gy = (r() + r() + r() - 1.5) * spread;
        f.put(k, xAt(t), y + gy, s.z + gx, 0.22 + r() * 0.25, tint, s.key === "book" ? 0.55 : 0.35);
      }
    }
    for (let gx = 0; gx <= 38; gx++) {
      for (let gz = 0; gz <= 14; gz++, k++) {
        const on = gx % 2 === 0 || gz % 2 === 0;
        f.put(k, X0 + gx * 0.5, FLOOR, -5 + gz * 0.5, on ? 0.22 : 0, C.dust, 0.35);
      }
    }
    for (const y of YEARS) {
      const x = xAt(D.months.indexOf(`${y}-01`));
      for (let j = 0; j < 60; j++, k++) f.put(k, x, FLOOR + j * 0.16, BACK, 0.16, C.dust, 0.22);
    }
    for (const g of [1, 1.5, 2, 2.5]) {
      for (let j = 0; j < 190; j++, k++) f.put(k, X0 + j * 0.1, yAt(g), BACK, j % 2 ? 0 : 0.14, C.dust, 0.28);
    }
    dust(f, k, 13, 36, 1.4, 0.12);
    return f;
  }

  focus(year: string, move = true) {
    this.year = year;
    this.chips.forEach((b) => b.setAttribute("aria-pressed", String(b.textContent === (year || "All years"))));
    if (!year) {
      this.scope.textContent = `Whole period, ${D.months.length} months`;
      this.readout.book.value.textContent = `$${R.book[STEPS - 1].toFixed(2)}`;
      this.readout.market.value.textContent = `$${R.market[STEPS - 1].toFixed(2)}`;
      this.readout.hurdle.value.textContent = `$${R.hurdle[STEPS - 1].toFixed(2)}`;
      this.readout.active.value.textContent = `${signed(D.costs.ladder[0].active)} a year`;
      if (move) this.w.stage.frame(this.shot);
      return;
    }
    const y = D.years[year];
    this.scope.textContent = `${year}${y.months < 12 ? `, first ${y.months} months` : ""}, total return`;
    this.readout.book.value.textContent = signed(y.strategy);
    this.readout.market.value.textContent = signed(y.market);
    this.readout.hurdle.value.textContent = signed(y.benchmark);
    this.readout.active.value.textContent = signed(y.active);
    const a = D.months.indexOf(`${year}-01`);
    const b = Math.min(STEPS - 1, a + y.months);
    const cx = (xAt(a) + xAt(b)) / 2;
    const cy = (yAt(R.book[a]) + yAt(R.book[b]) + yAt(R.market[a]) + yAt(R.market[b])) / 4;
    if (move) this.w.stage.frame({ eye: [cx + 1.5, cy + 1.2, 9.5], look: [cx, cy, -1], drift: 0.3, shift: 0.1 });
    this.w.sound.tick(1.1, 0.6);
  }

  // Draws the three lines on from January 2021, with a shockwave when the market breaks in 2022.
  draw() {
    this.fired = false;
    this.callout.shown = false;
    for (const l of this.ends) l.shown = false;
    this.timeline?.kill();
    const progress = { p: 0 };
    const crash = CRASH / (STEPS - 1);
    this.timeline = gsap.timeline({ delay: 0.5 });
    this.timeline.to(progress, {
      p: 1,
      duration: 5.2,
      ease: "power1.inOut",
      onUpdate: () => {
        for (const line of this.lines) line.material.uniforms.uProgress.value = progress.p;
        if (!this.fired && progress.p >= crash) this.shock();
      },
      onComplete: () => this.ends.forEach((l) => (l.shown = true)),
    });
  }

  shock() {
    this.fired = true;
    const at = new THREE.Vector3(xAt(CRASH), yAt(R.market[CRASH]), -1.1);
    this.w.sim.wave({ at, amp: 1.6, speed: 7 });
    this.w.sound.tick(0.5, 1);
    this.ring.position.copy(at);
    gsap.fromTo(this.ring.scale, { x: 0.2, y: 0.2 }, { x: 2.4, y: 2.4, duration: 1.6, ease: "expo.out" });
    gsap.fromTo(this.ring.material.uniforms.uOpacity, { value: 2 }, { value: 0, duration: 1.8, ease: "power2.out" });
    this.callout.shown = true;
  }

  enter() {
    for (const l of this.labels) l.shown = !this.ends.includes(l) && l !== this.callout;
    this.draw();
  }

  leave() {
    for (const line of this.lines) line.material.uniforms.uProgress.value = 0;
    this.cross.material.opacity = 0;
    if (this.year) this.focus("", false);
  }

  hover(x: number, y: number) {
    const ray = rayAt(x, y, this.w.stage.camera).ray;
    const inside = ray.intersectPlane(plane, hit) && hit.x >= X0 && hit.x <= X1 && hit.y >= FLOOR - 1 && hit.y <= 7;
    if (!inside) {
      this.cross.material.opacity = 0;
      return null;
    }
    const i = Math.max(1, Math.round(((hit.x - X0) / (X1 - X0)) * (STEPS - 1)));
    this.cross.position.set(xAt(i), FLOOR + 5.25, -1);
    this.cross.material.opacity = 0.35;
    return `<strong>${monthName(D.months[i - 1])}</strong> <span class="muted">growth of $1</span><br>
      ${swatch("var(--m-ours)")}Final book <strong>$${R.book[i].toFixed(2)}</strong> <span class="muted">${signed(R.book_monthly[i - 1])} that month</span><br>
      ${swatch("var(--m-brand)")}S&amp;P 500 <strong>$${R.market[i].toFixed(2)}</strong> <span class="muted">${signed(R.market_monthly[i - 1])}</span><br>
      ${swatch("var(--ink-3)")}Hurdle <strong>$${R.hurdle[i].toFixed(2)}</strong>`;
  }
}
