import * as THREE from "three";
import { C } from "../shared/palette";

// The rocker's radius, and the dial's height above the rocker's centre.
const ROCKER = 0.9;
const CENTRE = 2.38;

// The three materials: polished chrome, brushed gold and white ceramic.
const chrome = () => new THREE.MeshPhysicalMaterial({ color: 0xf3f3f7, metalness: 1, roughness: 0.07 });
export const gold = () => new THREE.MeshPhysicalMaterial({ color: 0xe8bd62, metalness: 1, roughness: 0.2 });
const ceramic = (color = 0xf6f4f9) =>
  new THREE.MeshPhysicalMaterial({ color, roughness: 0.42, clearcoat: 0.8, clearcoatRoughness: 0.12 });

// The book's face, a white instrument dial with fine gold ticks.
function dial() {
  const c = document.createElement("canvas");
  c.width = c.height = 1024;
  const g = c.getContext("2d")!;
  g.fillStyle = "#ffffff";
  g.fillRect(0, 0, 1024, 1024);
  g.translate(512, 512);
  g.strokeStyle = "#c79d45";
  // 120 ticks, every tenth longer and bolder.
  for (let i = 0; i < 120; i++) {
    const a = (i / 120) * Math.PI * 2;
    const long = i % 10 === 0;
    g.lineWidth = long ? 9 : 5;
    g.beginPath();
    g.moveTo(Math.cos(a) * (long ? 370 : 415), Math.sin(a) * (long ? 370 : 415));
    g.lineTo(Math.cos(a) * 470, Math.sin(a) * 470);
    g.stroke();
  }
  // An inner ring and a gold centre dot.
  g.lineWidth = 5;
  g.beginPath();
  g.arc(0, 0, 345, 0, Math.PI * 2);
  g.stroke();
  g.fillStyle = "#c79d45";
  g.beginPath();
  g.arc(0, 0, 14, 0, Math.PI * 2);
  g.fill();
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  t.center.set(0.5, 0.5);
  return t;
}

// A cylinder of the given radius running between two points.
function rod(from: THREE.Vector3, to: THREE.Vector3, radius: number, material: THREE.Material) {
  const d = to.clone().sub(from);
  const m = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, d.length(), 24), material);
  m.position.copy(from).add(to).multiplyScalar(0.5);
  m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
  return m;
}

// A ship's compass gimbal whose dial stays level as the market rocks.
export class Gimbal {
  // The base carries the stand and outer ring, the outer ring the inner.
  group = new THREE.Group();
  base = new THREE.Group();
  stand = new THREE.Group();
  outer = new THREE.Group();
  inner = new THREE.Group();
  disc: THREE.Mesh;
  // The dial texture, and the gauge's hand and figure.
  private face: THREE.Texture;
  private hand = new THREE.Group();
  private figure: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>;
  private ink: CanvasRenderingContext2D;
  // The text last drawn, so the figure redraws only on a change.
  private shown = "";

  // Builds stand, rings and dial, every mesh casting and taking shadows.
  constructor() {
    const steel = chrome();
    const brass = gold();
    const white = ceramic();
    this.face = dial();
    // A chrome half sphere to rock on, under a ceramic slab.
    const rocker = new THREE.Mesh(
      new THREE.SphereGeometry(ROCKER, 64, 32, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2),
      steel,
    );
    const slab = new THREE.Mesh(new THREE.CylinderGeometry(3.25, 3.25, 0.28, 128), ceramic(0xf1eef6));
    slab.position.y = 0.14;
    this.stand.add(rocker, slab);
    // Two chrome posts with ball caps hold the outer ring's pivots.
    for (const x of [-2.8, 2.8]) {
      this.stand.add(rod(new THREE.Vector3(x, 0.28, 0), new THREE.Vector3(x, CENTRE + 0.12, 0), 0.06, steel));
      const cap = new THREE.Mesh(new THREE.SphereGeometry(0.09, 32, 16), steel);
      cap.position.set(x, CENTRE + 0.12, 0);
      this.stand.add(cap);
    }
    this.outer.position.y = CENTRE;
    // A torus laid flat, for both rings.
    const ring = (r: number, tube: number, m: THREE.Material) => {
      const t = new THREE.Mesh(new THREE.TorusGeometry(r, tube, 32, 220), m);
      t.rotation.x = Math.PI / 2;
      return t;
    };
    // Chrome outer ring on x pivots, gold inner on z, spokes to the dial.
    this.outer.add(ring(2.56, 0.085, steel));
    for (const x of [-1, 1])
      this.outer.add(rod(new THREE.Vector3(x * 2.56, 0, 0), new THREE.Vector3(x * 2.8, 0, 0), 0.04, steel));
    this.inner.add(ring(2.14, 0.07, brass));
    for (const z of [-1, 1])
      this.inner.add(rod(new THREE.Vector3(0, 0, z * 2.14), new THREE.Vector3(0, 0, z * 2.56), 0.035, brass));
    for (const x of [-1, 1])
      this.inner.add(rod(new THREE.Vector3(x * 1.78, 0, 0), new THREE.Vector3(x * 2.14, 0, 0), 0.03, brass));
    // The dial, gold at the rim, the face on top, white beneath.
    const top = ceramic();
    top.map = this.face;
    this.disc = new THREE.Mesh(new THREE.CylinderGeometry(1.8, 1.8, 0.16, 160), [brass, top, white]);
    this.inner.add(this.disc);
    // A glowing gold hand, hidden until the dial becomes a gauge.
    const glow = new THREE.MeshBasicMaterial({
      color: new THREE.Color(C.gold).multiplyScalar(2.2),
      transparent: true,
    });
    const needle = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.012, 1.4), glow);
    needle.position.z = -0.7;
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.02, 32), glow);
    this.hand.add(needle, hub);
    this.hand.position.y = 0.092;
    // The figure, text on a 2048 by 1024 canvas lying on the dial.
    const canvas = document.createElement("canvas");
    canvas.width = 2048;
    canvas.height = 1024;
    this.ink = canvas.getContext("2d")!;
    const map = new THREE.CanvasTexture(canvas);
    map.colorSpace = THREE.SRGBColorSpace;
    map.anisotropy = 8;
    this.figure = new THREE.Mesh(
      new THREE.PlaneGeometry(2.3, 1.15),
      new THREE.MeshBasicMaterial({
        map,
        transparent: true,
        depthWrite: false,
        color: 0xffffff,
      }),
    );
    // The figure lies on the lower half of the dial, below the hub.
    this.figure.rotation.x = -Math.PI / 2;
    this.figure.position.set(0, 0.084, 0.62);
    this.disc.add(this.hand, this.figure);
    this.hand.visible = this.figure.visible = false;
    this.outer.add(this.inner);
    this.base.add(this.stand, this.outer);
    this.group.add(this.base);
    this.group.traverse((o) => {
      if (o instanceof THREE.Mesh) o.castShadow = o.receiveShadow = true;
    });
  }

  // The dial as a gauge, its hand and figure counting up to value.
  read(value: number, top: number, show: number, label = "", format = (v: number) => v.toFixed(2)) {
    this.hand.visible = this.figure.visible = show > 0;
    if (!show) return;
    // Show fades both in, and the hand turns 270 degrees at the top value.
    this.hand.rotation.y = (-value / top) * Math.PI * 1.5;
    for (const m of [this.figure.material, (this.hand.children[0] as THREE.Mesh).material as THREE.Material])
      m.opacity = show;
    // Redraws the figure and its label only when the text changes.
    const text = format(value);
    if (text + label === this.shown) return;
    this.shown = text + label;
    const g = this.ink;
    g.clearRect(0, 0, 2048, 1024);
    g.textAlign = "center";
    g.fillStyle = "#16111f";
    g.font = "italic 600px 'Instrument Serif'";
    g.fillText(text, 1024, 600);
    g.fillStyle = "#8a6418";
    g.font = "500 108px 'Geist Mono'";
    g.letterSpacing = "36px";
    g.fillText(label, 1024, 840);
    this.figure.material.map!.needsUpdate = true;
  }

  // The dial's height above the floor when the base is level.
  static centre = ROCKER + CENTRE;

  // Rolls the base by a and b on the rocker, the rings undoing the tilt.
  tilt(a: number, b: number, spin: number) {
    // Rolling, not sliding, shifts the base by the radius times the tilt.
    this.base.position.set(-ROCKER * b, ROCKER, ROCKER * a);
    this.base.rotation.set(a, 0, b, "ZXY");
    this.outer.rotation.set(-a, 0, 0);
    this.inner.rotation.set(0, 0, -b);
    this.face.rotation = spin;
  }
}
