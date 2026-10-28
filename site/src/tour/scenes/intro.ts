import * as THREE from "three";
import { corners } from "../layout";
import { D, num, pct } from "../../shared/data";
import { blank, N } from "../gl/sim";
import { h } from "../../shared/dom";
import { stat } from "../ui";
import { C, dust, Scene, stats, type World } from "./scene";
import { seeded } from "../../shared/math";

// One line of the title, drawn in particles.
interface Line {
  text: string;
  font: string;
  y: number;
  spacing?: number;
}

// Points in canvas text, every step px, scaled to width world units.
function sample(lines: Line[], width: number, step: number) {
  const W = 1800;
  const H = 820;
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const g = canvas.getContext("2d", { willReadFrequently: true })!;
  g.fillStyle = "#fff";
  g.textAlign = "center";
  g.textBaseline = "middle";
  for (const line of lines) {
    g.font = line.font;
    g.letterSpacing = `${line.spacing ?? 0}px`;
    g.fillText(line.text, W / 2, line.y);
  }
  const data = g.getImageData(0, 0, W, H).data;
  const split = (lines[0].y + lines[1].y) / 2;
  const scale = width / W;
  const out: { x: number; y: number; line: number; u: number }[] = [];
  // Keeps pixels over 140 alpha, tagged by line and by x across, 0 to 1.
  for (let y = 0; y < H; y += step) {
    for (let x = 0; x < W; x += step) {
      if (data[(y * W + x) * 4 + 3] > 140) {
        out.push({ x: (x - W / 2) * scale, y: (H / 2 - y) * scale, line: y < split ? 0 : 1, u: x / W });
      }
    }
  }
  return out;
}

// The opening: the name in particles and the three key numbers.
export class Intro extends Scene {
  name = "QUARCC Purple · FIAM";
  summary = "Who we are and the three ideas that matter.";
  private points: ReturnType<typeof sample> = [];

  // Sets a slower gather and the panel with the three headline ideas.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 0.4, 27], look: [0, 0.6, 0], drift: 0.6, shift: 0 };
    this.physics = { stiff: 11, damp: 1.1, flow: 0.35, spin: 0.03, mouse: 1.6 };
    this.stagger = 2.2;
    this.duration = 1.8;
    this.dwell = 9;
    const head = D.headline;
    this.panel.append(
      h(
        "p",
        { class: "body", "data-rise": true },
        "Ten published signals and machine learning pick US stocks, code keeps the book market neutral and an AI crowd shows who crowds our trades.",
      ),
      stats(
        stat(num(head.beta), "Beta, market neutral").el,
        stat(pct(head.vol), "Volatility").el,
        stat(pct(head.drawdown), "Max drawdown").el,
      ),
    );
    this.controls.append(
      h("p", { class: "eyebrow hint" }, "Press → to begin, or P for the guided tour"),
      h("p", { class: "eyebrow touch-hint" }, "Swipe or tap › to begin"),
    );
    // Small screens fit the title and its dust into their band.
    this.frame = corners(-11, -2.7, 0, 11, 5, 0);
    this.zoomCap = 1.2;
  }

  // Up to 12500 title points in purple and gold, then dust and far stars.
  formation() {
    const f = blank();
    // Samples the title once; later visits reuse the points.
    if (!this.points.length) {
      this.points = sample(
        [
          { text: "QUARCC Purple", font: "italic 300px 'Instrument Serif'", y: 250 },
          { text: "FIAM", font: "600 330px 'Geist'", y: 580, spacing: 60 },
        ],
        24,
        3,
      );
    }
    const r = seeded(7);
    const pts = [...this.points].sort(() => r() - 0.5).slice(0, 12500);
    const purple = new THREE.Color(C.purple);
    const ice = new THREE.Color(C.ice);
    const gold = new THREE.Color(C.gold);
    const ink = new THREE.Color(C.ink);
    const tint = new THREE.Color();
    pts.forEach((p, i) => {
      if (p.line === 0) tint.copy(purple).lerp(ice, p.u * 0.6 + r() * 0.15);
      else tint.copy(gold).lerp(ink, 0.15 + r() * 0.3);
      const sparkle = r() < 0.04 ? 1.8 : 1;
      const x = p.x + (r() - 0.5) * 0.05;
      f.put(i, x, p.y + 1.2 + (r() - 0.5) * 0.05, (r() - 0.5) * 0.35, 0.62 * sparkle, tint, 0.95 * sparkle);
    });
    dust(f, pts.length, 3, 30, 2, 0.2);
    for (let i = pts.length; i < N; i += 7)
      f.put(i, (r() - 0.5) * 60, (r() - 0.5) * 34, -12 - r() * 20, 0.35, C.ice, 0.3);
    return f;
  }
}
