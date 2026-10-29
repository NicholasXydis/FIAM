import gsap from "gsap";
import * as THREE from "three";
import { D, monthName, num, pct, plus, signed } from "../../shared/data";
import { clamp } from "../../shared/math";
import { Formation } from "../gl/sim";
import { rim } from "../gl/shapes";
import { h } from "../../shared/dom";
import { corners } from "../layout";
import { box, fill, fold, months, nearest, type Player, stat } from "../ui";
import { C, dust, header, Scene, stats, type World } from "./scene";

// Dots across the floor, along x.
const GX = 64;
// Dots deep into the floor, along z.
const GZ = 40;
// The gap between floor dots, in world units.
const STEP = 0.42;
// The floor's height, below the gyroscope.
const FLOOR = -3.2;
// How far the floor tilts per unit of monthly return.
const TILT = 3.2;

// Gauge: a half dial from -0.5 to +0.5, noise band shaded, a needle.
function dial() {
  const svg = `<svg viewBox="-110 -104 220 122" width="220" height="122" role="img" aria-label="Rolling beta">
    <path d="M -90 0 A 90 90 0 0 1 90 0" fill="none" stroke="rgb(237 233 246 / .16)" stroke-width="10" stroke-linecap="round"/>
    <path class="band" fill="none" stroke="var(--m-long)" stroke-opacity=".45" stroke-width="10"/>
    <line x1="0" y1="0" x2="0" y2="-96" stroke="rgb(237 233 246 / .35)" stroke-width="1" stroke-dasharray="2 3"/>
    <g class="needle"><line x1="0" y1="6" x2="0" y2="-82" stroke="var(--gold)" stroke-width="3" stroke-linecap="round"/><circle r="6" fill="var(--gold)"/></g>
    <text x="-90" y="16" fill="var(--ink-3)" font-size="11" text-anchor="middle" font-family="var(--mono)">−0.5</text>
    <text x="0" y="16" fill="var(--ink-3)" font-size="11" text-anchor="middle" font-family="var(--mono)">0</text>
    <text x="90" y="16" fill="var(--ink-3)" font-size="11" text-anchor="middle" font-family="var(--mono)">+0.5</text>
  </svg>`;
  return h("div", { html: svg });
}

// An SVG arc across the gauge between two betas.
const arc = (a: number, b: number) => {
  // A beta's point on the dial's arc of radius 90.
  const p = (v: number) => {
    const t = Math.PI * (1 - (clamp(v, -0.5, 0.5) + 0.5));
    return `${(Math.cos(t) * 90).toFixed(2)} ${(-Math.sin(t) * 90).toFixed(2)}`;
  };
  return `M ${p(a)} A 90 90 0 0 1 ${p(b)}`;
};

// A gyroscope stays level while each month's market tilts the floor.
export class Neutral extends Scene {
  name = "Neutral to the market";
  summary = "A gyroscope that stays level while the market floor tilts each month.";
  month = 0;
  private f = new Formation();
  private gyro = new THREE.Group();
  private rotor = new THREE.Group();
  private inner = new THREE.Group();
  private tilt = new THREE.Vector2();
  private spin = new THREE.Vector2();
  private target = new THREE.Vector2();
  private floor = 0;
  private input: HTMLInputElement;
  private when = h("b", { class: "figure text-[24px] text-ink font-medium" });
  private moves = h("p", { class: "text-[13px] text-ink-2" });
  private gauge = dial();
  private note = h("p", { class: "text-[12px] text-ink-3 max-w-[240px]" });
  private player: Player;

  // Builds the gyroscope: gold hoop, purple gimbal, spoked rotor, axle.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 6.8, 15.5], look: [0, -1.2, 0], drift: 0.7, shift: 0.17 };
    this.physics = { stiff: 10, damp: 1.1, flow: 0.15, spin: 0.02, mouse: 0.8 };
    this.dwell = 15;
    // A torus with a glowing rim, for the gyroscope's hoops.
    const ring = (radius: number, tube: number, color: number, opacity: number) =>
      new THREE.Mesh(new THREE.TorusGeometry(radius, tube, 20, 120), rim(color, opacity, 0.25));
    const outer = ring(2.5, 0.05, C.gold, 0.75);
    const gimbal = ring(2.15, 0.04, C.purple, 0.7);
    gimbal.rotation.y = Math.PI / 2;
    this.inner.add(gimbal);
    const disc = new THREE.Mesh(new THREE.CylinderGeometry(1.55, 1.55, 0.16, 96, 1, true), rim(C.ice, 0.55, 0.06));
    const face = new THREE.Mesh(new THREE.CircleGeometry(1.55, 96), rim(C.purple, 0.18, 0.2));
    face.rotation.x = -Math.PI / 2;
    this.rotor.add(disc, face);
    // Twelve thin spokes, spaced evenly round the rotor.
    for (let i = 0; i < 12; i++) {
      const spoke = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.02, 0.03), rim(C.ice, 0.45, 0.5));
      spoke.position.set(Math.cos((i / 12) * Math.PI * 2) * 0.76, 0.09, Math.sin((i / 12) * Math.PI * 2) * 0.76);
      spoke.rotation.y = -(i / 12) * Math.PI * 2;
      this.rotor.add(spoke);
    }
    const axle = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 5.2, 12), rim(C.gold, 0.7, 0.5));
    this.inner.add(this.rotor, axle);
    this.gyro.add(outer, this.inner);
    this.gyro.position.y = 0.5;
    this.group.add(this.gyro);

    const head = D.headline;
    // The months the S&P 500 fell, and in how many the book still rose.
    const down = D.race.market_monthly.flatMap((m, i) => (m < 0 ? [D.race.book_monthly[i] ?? 0] : []));
    const gained = down.filter((b) => b > 0).length;
    this.panel.append(
      ...header(
        "The market tilts, <em>we stay level</em>",
        `The optimizer holds beta near zero. Downside capture ${signed(head.down_capture, 0)}, upside ${signed(head.up_capture, 0)}. The floor tilts with the S&P 500, the gyroscope with our beta.`,
      ),
      stats(
        stat(plus(head.beta), "Monthly beta").el,
        stat(`${gained} of ${down.length}`, "Down months gained").el,
        // The share of the book's monthly moves the S&P 500 explains.
        stat(pct(head.correlation ** 2), "Explained by S&P").el,
      ),
    );
    const picker = months("beta-month", 0.7, this);
    this.player = picker.player;
    this.input = picker.input;
    this.controls.append(
      box(
        "w-[min(420px,calc(100vw-32px))] gap-2",
        h("div", { class: "flex items-center justify-between gap-3" }, this.when, this.player.button),
        this.moves,
        this.input,
        h("div", { class: "flex items-center gap-4" }, this.gauge, this.note),
      ),
    );
    // Small screens: the gauge and its note fold behind a Gauge chip.
    const glass = this.controls.firstElementChild as HTMLElement;
    fold(glass, glass.firstElementChild as HTMLElement, [glass.lastElementChild!], "Gauge");
    this.frame = corners(-4.6, -3.4, -3, 4.6, 3.4, 3);
    this.zoomCap = 1.4;
  }

  // Floor tilted by the month's return, cyan if up and orange if down.
  formation() {
    const f = this.f;
    const a = this.floor;
    const c = Math.cos(a);
    const s = Math.sin(a);
    const color = new THREE.Color();
    const toward = new THREE.Color(a < 0 ? C.orange : C.cyan);
    const lean = Math.min(1, Math.abs(a) * 3) * 0.75;
    let k = 0;
    // A 64 by 40 grid of dots, tilted by the month's return.
    for (let i = 0; i < GX; i++) {
      // Walk one row from front to back.
      for (let j = 0; j < GZ; j++, k++) {
        const x = (i - (GX - 1) / 2) * STEP;
        const z = (j - (GZ - 1) / 2) * STEP;
        const edge = Math.max(Math.abs(x) / ((GX * STEP) / 2), Math.abs(z) / ((GZ * STEP) / 2));
        color.setHex(C.ice).lerp(toward, lean);
        const line = i % 8 === 0 || j % 8 === 0;
        f.put(k, x * c, FLOOR + x * s, z, line ? 0.36 : 0.26, color, (line ? 0.75 : 0.42) + edge * 0.35);
      }
    }
    // The floor is rewritten in place, so dust is laid only the first time.
    if (!f.col[(k + 2) * 4 + 3]) dust(f, k, 17, 34, 1.4, 0.12);
    return f;
  }

  // Shows a month: the floor's tilt, the beta and the gauge.
  set(month: number, move = true) {
    this.month = month;
    this.input.value = String(month);
    fill(this.input);
    const m = D.months[month];
    const market = D.race.market_monthly[month];
    this.floor = clamp(market * TILT, -0.42, 0.42);
    const rolling = D.beta.rolling[m];
    const beta = rolling ? rolling[0] : (D.beta.since[m] ?? 0);
    this.target.set(this.floor * beta, 0);
    this.spin.y += this.floor * 0.6;
    if (move) this.w.sim.update(this.formation());
    this.when.textContent = monthName(m, true);
    this.moves.innerHTML = `S&amp;P 500 <b class="text-ink figure">${signed(market)}</b> · Final book <b class="text-ink figure">${signed(D.race.book_monthly[month])}</b>`;
    const needle = this.gauge.querySelector(".needle") as SVGGElement;
    gsap.to(needle, { rotation: clamp(beta, -0.5, 0.5) * 180, svgOrigin: "0 0", duration: 0.6, ease: "back.out(2)" });
    const band = this.gauge.querySelector(".band") as SVGPathElement;
    // The noise band once a 12-month beta exists, else the beta so far.
    if (rolling) {
      band.setAttribute("d", arc(-rolling[1], rolling[1]));
      this.note.innerHTML = `Rolling 12-month beta <b class="text-ink figure">${plus(beta)}</b>. The shaded arc is how far a truly zero-beta book with our risk could stray by chance, ±${num(rolling[1])}.`;
    } else {
      band.setAttribute("d", "");
      this.note.innerHTML = `Beta since ${monthName(D.months[0]!)} <b class="text-ink figure">${plus(beta, 3)}</b>. The 12-month measured beta starts in ${monthName(Object.keys(D.beta.rolling)[0], true)}.`;
    }
  }

  // Plays the months 1.6 s after arriving, if still on the first month.
  override enter() {
    this.set(this.month, false);
    gsap.delayedCall(1.6, () => this.active && this.month === 0 && this.player.start());
  }

  // Stops playing on the way out.
  override leave() {
    this.player.stop();
  }

  // Space plays or pauses.
  override key(e: KeyboardEvent) {
    return this.player.key(e);
  }

  // Invites a push on the gyroscope.
  override hover(x: number, y: number) {
    if (nearest([this.gyro.position], x, y, this.w.stage.camera, 120) < 0) return null;
    return "<strong>Give it a push</strong><br>Click the gyroscope and watch the spin right it";
  }

  // A click knocks it sideways; the spin makes that a wobble that dies.
  override click(x: number, y: number) {
    if (nearest([this.gyro.position], x, y, this.w.stage.camera, 120) < 0) return;
    this.spin.x += (Math.random() < 0.5 ? -1 : 1) * 2.4;
    this.spin.y += 1.6;
    this.w.sound.tick(0.6, 0.9);
  }

  // Spring 26 to its lean, damping 2.6, and spin 7 turning it sideways.
  override tick(dt: number) {
    const k = 26;
    const c = 2.6;
    const omega = 7;
    const ax = -k * (this.tilt.x - this.target.x) - c * this.spin.x - omega * this.spin.y;
    const ay = -k * (this.tilt.y - this.target.y) - c * this.spin.y + omega * this.spin.x;
    this.spin.x += ax * dt;
    this.spin.y += ay * dt;
    this.tilt.x += this.spin.x * dt;
    this.tilt.y += this.spin.y * dt;
    this.gyro.rotation.z = this.tilt.x;
    this.gyro.rotation.x = this.tilt.y;
    this.rotor.rotation.y += dt * 14;
    this.inner.rotation.y += dt * 0.25;
  }
}
