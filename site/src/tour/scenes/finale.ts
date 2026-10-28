import gsap from "gsap";
import * as THREE from "three";
import CODE, { MARK } from "virtual:qr";
import { blank, N } from "../gl/sim";
import { h } from "../../shared/dom";
import { corners } from "../layout";
import { chip, screen } from "../ui";
import { C, dust, header, Scene, type World } from "./scene";
import { seeded } from "../../shared/math";

// Code size in world units, modules a side, and an odd logo, 20% wide.
const SIZE = 8;
const M = CODE.length;
const LOGO = Math.round(M * 0.2) | 1;
// Whether a module is dark, in the logo, or in an eye.
const dark = (x: number, y: number) => +CODE[y][x] % 2 === 1;
const inLogo = (x: number, y: number) => Math.abs(x - (M - 1) / 2) <= LOGO / 2 && Math.abs(y - (M - 1) / 2) <= LOGO / 2;
const isEye = (x: number, y: number) => +CODE[y][x] >= 2;

// Printable SVG: purple dots and eyes on light card, our mark centred.
function svg() {
  const q = 4;
  const total = M + q * 2;
  const dots: string[] = [];
  // One round dot per dark module, skipping the eyes and the logo.
  for (let y = 0; y < M; y++) {
    for (let x = 0; x < M; x++) {
      if (!dark(x, y) || isEye(x, y) || inLogo(x, y)) continue;
      dots.push(`<circle cx="${x + q + 0.5}" cy="${y + q + 0.5}" r="0.46"/>`);
    }
  }
  // Each eye: a rounded 6-module square around a 3-module gradient core.
  const eye = (x: number, y: number) =>
    `<rect x="${x + q + 0.5}" y="${y + q + 0.5}" width="6" height="6" rx="1.9" fill="none" stroke="#1b1240" stroke-width="1"/>` +
    `<rect x="${x + q + 2}" y="${y + q + 2}" width="3" height="3" rx="0.9" fill="url(#eye)"/>`;
  const c = total / 2;
  const r = LOGO / 2 + 0.2;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${total} ${total}" shape-rendering="geometricPrecision">
  <defs>
    <linearGradient id="dot" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2a1660"/><stop offset="1" stop-color="#45207f"/></linearGradient>
    <linearGradient id="eye" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6d4fd8"/><stop offset="1" stop-color="#2a1660"/></linearGradient>
  </defs>
  <rect width="${total}" height="${total}" rx="${q * 0.8}" fill="#f5f2fc"/>
  <g fill="url(#dot)">${dots.join("")}</g>
  ${eye(0, 0)}${eye(M - 7, 0)}${eye(0, M - 7)}
  <circle cx="${c}" cy="${c}" r="${r}" fill="#1b1240"/>
  <circle cx="${c}" cy="${c}" r="${r - 0.35}" fill="none" stroke="#f2c14e" stroke-width="0.18"/>
  <svg x="${c - r * 0.8}" y="${c - r * 0.8}" width="${r * 1.6}" height="${r * 1.6}" viewBox="0 0 512 512">${MARK}</svg>
</svg>`;
}

// Downloads a blob through a temporary link, freed after a second.
function save(name: string, blob: Blob) {
  const a = h("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(a.href);
    a.remove();
  }, 1000);
}

// Reused screen spots for the card's corners, read every frame.
const topLeft = { x: 0, y: 0, front: true };
const bottomRight = { x: 0, y: 0, front: true };

// Thank you: every particle flies into the QR code, which can be saved.
export class Finale extends Scene {
  name = "Thank you";
  summary = "Every particle flies into a QR code that opens our source code on GitHub.";
  private card = h("div", { class: "absolute pointer-events-none", style: "opacity:0", "aria-hidden": "true" });
  private corners = [new THREE.Vector3(-SIZE / 2, SIZE / 2 + 0.6, 0), new THREE.Vector3(SIZE / 2, -SIZE / 2 + 0.6, 0)];
  private box = "";
  private printed = true;
  private toggle: HTMLButtonElement;

  // Prepends the printed card to the page layer and builds the panel.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 0.6, 17.5], look: [0, 0.6, 0], drift: 0.35, shift: 0.15 };
    this.physics = { stiff: 13, damp: 0.75, flow: 0.12, spin: 0.05, mouse: 1.2 };
    this.stagger = 1.8;
    this.duration = 1.6;
    this.dwell = 12;
    this.card.innerHTML = svg();
    (this.card.firstElementChild as SVGElement).setAttribute("width", "100%");
    (this.card.firstElementChild as SVGElement).setAttribute("height", "100%");
    this.w.layer.prepend(this.card);
    this.panel.append(
      ...header(
        "Thank <em>you</em>",
        "Machine learning ranks the stocks, code enforces every rule and AI checks but never trades. Scan for our source code on GitHub.",
      ),
    );
    this.toggle = chip("Show the particles", () => this.print(!this.printed));
    this.controls.append(
      h(
        "div",
        { class: "flex flex-wrap justify-end gap-2" },
        this.toggle,
        chip("Save QR", () => this.png()),
        chip("Start again", () => this.w.go(0)),
      ),
    );
    // Small screens fit the code, the frame its corners and the title.
    this.frame = corners(-4.6, -4, 0, 4.6, 5.2, 0);
    this.zoomCap = 1.35;
  }

  // Fades the printed code in over the particles, or out to show them.
  print(on: boolean, delay = 0) {
    this.printed = on;
    this.toggle.textContent = on ? "Show the particles" : "Show the printed code";
    gsap.killTweensOf(this.card);
    gsap.to(this.card, { opacity: on ? 1 : 0, duration: on ? 1.4 : 0.5, delay, ease: "power2.inOut" });
  }

  // Saves the code as a 2048 px PNG, drawn from the SVG on a canvas.
  png() {
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 2048;
      canvas.getContext("2d")!.drawImage(image, 0, 0, 2048, 2048);
      canvas.toBlob((blob) => blob && save("quarcc-purple-fiam-qr.png", blob), "image/png");
    };
    image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg())}`;
  }

  // Nine dots per dark module, gold eyes, a gold circle round the logo.
  formation() {
    const f = blank();
    const r = seeded(71);
    const cell = SIZE / M;
    const a = new THREE.Color(C.purple);
    const b = new THREE.Color(C.cyan);
    const tint = new THREE.Color();
    let k = 0;
    const per = 9;
    for (let y = 0; y < M; y++) {
      for (let x = 0; x < M; x++) {
        if (!dark(x, y) || inLogo(x, y)) continue;
        const cx = -SIZE / 2 + (x + 0.5) * cell;
        const cy = SIZE / 2 - (y + 0.5) * cell + 0.6;
        const eye = isEye(x, y);
        tint.copy(a).lerp(b, (x + y) / (2 * M));
        for (let j = 0; j < per && k < N; j++, k++) {
          const t = (j / per) * Math.PI * 2;
          const d = j === 0 ? 0 : cell * 0.28;
          f.put(
            k,
            cx + Math.cos(t) * d,
            cy + Math.sin(t) * d,
            (r() - 0.5) * 0.05,
            eye ? 0.36 : 0.3,
            eye ? C.gold : tint,
            eye ? 1.2 : 0.95,
          );
        }
      }
    }
    for (let i = 0; i < 1400 && k < N; i++, k++) {
      const t = (i / 1400) * Math.PI * 2;
      const rr = (LOGO / 2) * cell * (0.75 + 0.25 * r());
      f.put(k, Math.cos(t) * rr * 0.9, Math.sin(t) * rr * 0.9 + 0.6, 0, 0.22, C.gold, 0.5);
    }
    dust(f, k, 47, 34, 1.6, 0.14);
    return f;
  }

  // Fades the printed card in 3.4 s after arrival, once particles land.
  override enter() {
    this.card.style.opacity = "0";
    this.print(true, 3.4);
  }

  // Fades the card on the way out.
  override leave() {
    gsap.killTweensOf(this.card);
    gsap.to(this.card, { opacity: 0, duration: 0.4 });
  }

  // Invites a click over the code.
  override hover(x: number, y: number) {
    return this.inside(x, y) ? "<strong>Click to scatter it</strong><br>The particles find their way back" : null;
  }

  // A click scatters the particles; springs pull them back into the code.
  override click(x: number, y: number) {
    if (!this.inside(x, y)) return;
    this.w.sim.wave({ at: new THREE.Vector3(0, 0.6, 0), amp: 3, speed: 10 });
    this.w.sim.show(this.formation(), 1.2, 1.2);
    this.w.sound.tick(0.5, 1);
    if (!this.printed) return;
    gsap.killTweensOf(this.card);
    gsap
      .timeline()
      .to(this.card, { opacity: 0, duration: 0.3, ease: "power2.in" })
      .to(this.card, { opacity: 1, duration: 1.2, ease: "power2.inOut" }, "+=2.6");
  }

  // Whether a point is over the card.
  private inside(x: number, y: number) {
    const r = this.card.getBoundingClientRect();
    return x > r.left && x < r.right && y > r.top && y < r.bottom;
  }

  // Fits the card to the code's corners plus the 4-module quiet zone.
  override place(camera: THREE.Camera) {
    super.place(camera);
    const { x: x0, y: y0 } = screen(this.corners[0], camera, topLeft);
    const { x: x1, y: y1 } = screen(this.corners[1], camera, bottomRight);
    const pad = 4 / M;
    const box = `${(x0 - (x1 - x0) * pad).toFixed(1)},${(y0 - (y1 - y0) * pad).toFixed(1)},${((x1 - x0) * (1 + pad * 2)).toFixed(1)},${((y1 - y0) * (1 + pad * 2)).toFixed(1)}`;
    if (box === this.box) return;
    this.box = box;
    const [left, top, width, height] = box.split(",");
    Object.assign(this.card.style, { left: `${left}px`, top: `${top}px`, width: `${width}px`, height: `${height}px` });
  }
}
