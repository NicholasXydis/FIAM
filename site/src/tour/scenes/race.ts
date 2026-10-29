import gsap from "gsap";
import * as THREE from "three";
import { D, monthName, num, pct, signed, yearIndex } from "../../shared/data";
import { blank } from "../gl/sim";
import { glow, tube } from "../gl/shapes";
import { h } from "../../shared/dom";
import { corners, small } from "../layout";
import { chip, Label, rayAt, stat, swatch } from "../ui";
import { C, dust, header, Scene, stats, type World } from "./scene";
import { clamp, seeded } from "../../shared/math";

// The race data the build writes.
const R = D.race;
// Card captions for the whole run's returns and risk.
const WHOLE = ["Sharpe ratio", "Months up", "Worst fall", "Worst 12 months"];
// Card captions for one year's returns.
const YEAR = ["Final book", "S&P 500", "Hurdle", "Above the hurdle"];
// How many points each line has, the start and each month end.
const STEPS = R.book.length;
// The chart's left end in world units.
const X0 = -9.5;
// The chart's right end in world units.
const X1 = 8.2;
// The floor's height under the chart.
const FLOOR = -3.6;
// The back wall's depth, where the axis marks sit.
const BACK = -2.6;
// A month's index to its x across the chart.
const xAt = (i: number) => X0 + ((X1 - X0) * i) / (STEPS - 1);
// Growth of $1 to a height, on a log scale.
const yAt = (g: number) => Math.log(g) * 8.5 - 2.2;
// The point just after September 2022, the crash month.
const CRASH = D.months.indexOf("2022-09") + 1;
// Each line: its key, label, colour, mark, depth, width and dust.
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
// Each line's end height.
const ENDS = SERIES.map((s) => yAt(R[s.key][STEPS - 1]!));
// The gap close end labels keep between them, in world units.
const GAP = 0.7;
// The book's and hurdle's end labels part when the two ends sit close.
const part = (i: number) => {
  const [book, , hurdle] = ENDS as [number, number, number];
  const short = GAP - Math.abs(book - hurdle);
  if (short <= 0 || i === 1) return 0;
  const higher = i === 0 ? book >= hurdle : hurdle > book;
  return ((higher ? 1 : -1) * short) / 2;
};
// The years, one chip each.
const YEARS = Object.keys(D.years);
// The flat plane the hover reads months on.
const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
// Where the pointer's ray meets that plane.
const hit = new THREE.Vector3();
// A camera for working out the lens shift at this size.
const probe = new THREE.PerspectiveCamera(42, 1, 0.1, 200);
// A point projected through that camera.
const spot = new THREE.Vector3();
// Pixels kept clear at the right for the scene dots.
const RIGHT = 60;
// Pixels kept clear at the left for the dollar marks.
const LEFT = 70;

// The race: $1 in the book against market and hurdle, month by month.
export class Race extends Scene {
  name = "The race";
  summary = `$1 became $${R.book[STEPS - 1].toFixed(2)} after every cost, ${pct(D.headline.cagr)} a year, behind the hurdle.`;
  private lines: THREE.Mesh<THREE.TubeGeometry, THREE.ShaderMaterial>[] = [];
  private ends: Label[] = [];
  private cross: THREE.Mesh<THREE.BoxGeometry, THREE.MeshBasicMaterial>;
  private ring: THREE.Mesh<THREE.PlaneGeometry, THREE.ShaderMaterial>;
  private chips: HTMLButtonElement[] = [];
  private year = "";
  private fired = false;
  private cards = YEAR.map((caption) => stat("", caption));

  // Builds the three lines, axis labels, crosshair and the 2022 glow.
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
      const at = yAt(end) + part(this.ends.length);
      this.ends.push(this.addLabel(new Label(text, [X1 + 0.35, at, s.z], "left")));
    }
    for (const g of [1, 1.5, 2, 2.5])
      this.addLabel(new Label(`$${g.toFixed(2)}`, [X0 - 0.3, yAt(g), BACK], "right")).moves = false;
    for (const y of YEARS)
      this.addLabel(new Label(y, [xAt(yearIndex(y)) + 0.15, FLOOR + 0.35, BACK], "left")).moves = false;
    this.cross = new THREE.Mesh(
      new THREE.BoxGeometry(0.02, 10.5, 0.02),
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0 }),
    );
    this.cross.userData.keep = true;
    this.ring = glow(C.orange, 6, 0);
    this.ring.userData.keep = true;
    this.group.add(this.cross, this.ring);
    this.panel.append(
      ...header(
        `$1 became <em>$${R.book[STEPS - 1].toFixed(2)}</em>`,
        `After every cost that is ${signed(D.headline.cumulative)} in all, ${pct(D.headline.cagr)} a year. The hurdle, cash plus 4%, finished ahead at $${R.hurdle[STEPS - 1].toFixed(2)}. Pick a year to see its returns.`,
      ),
      stats(...this.cards.map((s) => s.el)),
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
    // The lens shift follows the window, so the end labels stay on screen.
    this.shot.shift = this.lens();
    addEventListener("resize", () => {
      this.shot.shift = this.lens();
      if (this.active && !this.year && !small()) this.w.stage.frame(this.shot, true);
    });
    // Small screens: values at the line ends, a key line names them.
    this.ends.forEach((l, i) => {
      const s = SERIES[i];
      l.small = { html: `${swatch(s.mark)}<b class="text-ink">$${R[s.key][STEPS - 1].toFixed(2)}</b>` };
      l.prio = 1;
    });
    (this.controls.firstElementChild as HTMLElement).classList.add("row");
    const key = SERIES.map((s) => `<span>${swatch(s.mark)}${s.label.split(",")[0]}</span>`).join("");
    this.controls.append(h("p", { class: "small-only eyebrow gap-3", html: key }));
    this.frame = corners(-9.8, -3.9, -2.6, 8.4, 5.4, 0);
  }

  // Dust along each line, a dotted floor, year posts and dollar rules.
  formation() {
    const f = blank();
    const r = seeded(31);
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
      const x = xAt(yearIndex(y));
      for (let j = 0; j < 60; j++, k++) f.put(k, x, FLOOR + j * 0.16, BACK, 0.16, C.dust, 0.22);
    }
    for (const g of [1, 1.5, 2, 2.5]) {
      for (let j = 0; j < 190; j++, k++) f.put(k, X0 + j * 0.1, yAt(g), BACK, j % 2 ? 0 : 0.14, C.dust, 0.28);
    }
    dust(f, k, 13, 36, 1.4, 0.12);
    return f;
  }

  // Zooms the camera to one year and its returns, or back to all of them.
  focus(year: string, move = true) {
    this.year = year;
    this.chips.forEach((b) => b.setAttribute("aria-pressed", String(b.textContent === (year || "All years"))));
    if (!year) {
      const head = D.headline;
      const up = head.months_up / D.months.length;
      this.write([num(head.sharpe), pct(up, 0), pct(head.drawdown), signed(head.worst_12.value)], WHOLE);
      if (move) this.w.stage.frame(this.shot);
      return;
    }
    // One year: its returns, and a close shot centred on its stretch.
    const y = D.years[year];
    // A part year says so on its first card, as 2026 has only some months.
    const captions = y.months < 12 ? [`Final book, ${y.months} months`, ...YEAR.slice(1)] : YEAR;
    this.write([signed(y.strategy), signed(y.market), signed(y.benchmark), signed(y.active)], captions);
    const a = yearIndex(year);
    const b = Math.min(STEPS - 1, a + y.months);
    const cx = (xAt(a) + xAt(b)) / 2;
    const cy = (yAt(R.book[a]) + yAt(R.book[b]) + yAt(R.market[a]) + yAt(R.market[b])) / 4;
    if (move) this.w.stage.frame({ eye: [cx + 1.5, cy + 1.2, 9.5], look: [cx, cy, -1], drift: 0.3, shift: 0.1 });
    this.w.sound.tick(1.1, 0.6);
  }

  // The lens shift that keeps the end labels and the axis on screen.
  private lens() {
    const W = innerWidth;
    const [eye, look] = [this.shot.eye, this.shot.look];
    probe.aspect = W / innerHeight;
    probe.position.set(...eye);
    probe.lookAt(...look);
    probe.updateProjectionMatrix();
    probe.updateMatrixWorld(true);
    // A world point's distance from the left edge as a share of width.
    const across = (x: number, y: number, z: number) => 0.5 + 0.5 * spot.set(x, y, z).project(probe).x;
    const widest = Math.max(230, ...this.ends.map((l) => l.el.offsetWidth));
    // The rightmost end label start, and the leftmost axis mark.
    const right = Math.max(...SERIES.map((s, i) => across(X1 + 0.35, ENDS[i]!, s.z)));
    const left = across(X0 - 0.3, yAt(1), BACK);
    const most = (W - RIGHT - widest) / W - right;
    const least = LEFT / W - left;
    // Too narrow for both, it splits the difference between the two.
    const want = most >= least ? Math.min(0.1, most) : (most + least) / 2;
    return clamp(want, -0.2, 0.1);
  }

  // Writes each card's value over its caption.
  private write(values: string[], captions: string[]) {
    this.cards.forEach((card, i) => {
      card.value.textContent = values[i] ?? "";
      card.caption.textContent = captions[i] ?? "";
    });
  }

  // Draws the lines from January 2021, a shockwave at the 2022 crash.
  draw() {
    this.fired = false;
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

  // Ripples the chart at the 2022 crash.
  shock() {
    this.fired = true;
    const at = new THREE.Vector3(xAt(CRASH), yAt(R.market[CRASH]), -1.1);
    this.w.sim.wave({ at, amp: 1.6, speed: 7 });
    this.w.sound.tick(0.5, 1);
    this.ring.position.copy(at);
    gsap.fromTo(this.ring.scale, { x: 0.2, y: 0.2 }, { x: 2.4, y: 2.4, duration: 1.6, ease: "expo.out" });
    gsap.fromTo(this.ring.material.uniforms.uOpacity, { value: 2 }, { value: 0, duration: 1.8, ease: "power2.out" });
  }

  // Shows axis labels, holds the end labels, and draws.
  override enter() {
    for (const l of this.labels) l.shown = !this.ends.includes(l);
    this.draw();
  }

  // Resets lines, crosshair and year zoom on the way out.
  override leave() {
    for (const line of this.lines) line.material.uniforms.uProgress.value = 0;
    this.cross.material.opacity = 0;
    if (this.year) this.focus("", false);
  }

  // Reads the month under the pointer and moves the crosshair to it.
  override hover(x: number, y: number) {
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
