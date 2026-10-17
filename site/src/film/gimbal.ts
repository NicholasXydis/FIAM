import * as THREE from "three";

const ROCKER = 0.9;
const CENTRE = 2.38;

export const chrome = () => new THREE.MeshPhysicalMaterial({ color: 0xf3f3f7, metalness: 1, roughness: 0.07 });
export const gold = () => new THREE.MeshPhysicalMaterial({ color: 0xe8bd62, metalness: 1, roughness: 0.2 });
export const ceramic = (color = 0xf6f4f9) =>
  new THREE.MeshPhysicalMaterial({ color, roughness: 0.42, clearcoat: 0.8, clearcoatRoughness: 0.12 });

// The face of the book: a white dial with fine gold ticks, like an instrument.
function dial() {
  const c = document.createElement("canvas");
  c.width = c.height = 1024;
  const g = c.getContext("2d")!;
  g.fillStyle = "#ffffff";
  g.fillRect(0, 0, 1024, 1024);
  g.translate(512, 512);
  g.strokeStyle = "#c79d45";
  for (let i = 0; i < 120; i++) {
    const a = (i / 120) * Math.PI * 2;
    const long = i % 10 === 0;
    g.lineWidth = long ? 9 : 5;
    g.beginPath();
    g.moveTo(Math.cos(a) * (long ? 370 : 415), Math.sin(a) * (long ? 370 : 415));
    g.lineTo(Math.cos(a) * 470, Math.sin(a) * 470);
    g.stroke();
  }
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

function rod(from: THREE.Vector3, to: THREE.Vector3, radius: number, material: THREE.Material) {
  const d = to.clone().sub(from);
  const m = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, d.length(), 24), material);
  m.position.copy(from).add(to).multiplyScalar(0.5);
  m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
  return m;
}

// A ship's compass gimbal: the base rocks with the market, two rings turn on their pins to take up
// the tilt, and the dial in the middle stays level.
export class Gimbal {
  group = new THREE.Group();
  base = new THREE.Group();
  stand = new THREE.Group();
  outer = new THREE.Group();
  inner = new THREE.Group();
  disc: THREE.Mesh;
  private face: THREE.Texture;
  private hand = new THREE.Group();
  private figure: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>;
  private ink: CanvasRenderingContext2D;
  private shown = "";

  constructor() {
    const steel = chrome();
    const brass = gold();
    const white = ceramic();
    this.face = dial();
    const rocker = new THREE.Mesh(
      new THREE.SphereGeometry(ROCKER, 64, 32, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2),
      steel,
    );
    const slab = new THREE.Mesh(new THREE.CylinderGeometry(3.25, 3.25, 0.28, 128), ceramic(0xf1eef6));
    slab.position.y = 0.14;
    this.stand.add(rocker, slab);
    for (const x of [-2.8, 2.8]) {
      this.stand.add(rod(new THREE.Vector3(x, 0.28, 0), new THREE.Vector3(x, CENTRE + 0.12, 0), 0.06, steel));
      const cap = new THREE.Mesh(new THREE.SphereGeometry(0.09, 32, 16), steel);
      cap.position.set(x, CENTRE + 0.12, 0);
      this.stand.add(cap);
    }
    this.outer.position.y = CENTRE;
    const ring = (r: number, tube: number, m: THREE.Material) => {
      const t = new THREE.Mesh(new THREE.TorusGeometry(r, tube, 32, 220), m);
      t.rotation.x = Math.PI / 2;
      return t;
    };
    this.outer.add(ring(2.56, 0.085, steel));
    for (const x of [-1, 1])
      this.outer.add(rod(new THREE.Vector3(x * 2.56, 0, 0), new THREE.Vector3(x * 2.8, 0, 0), 0.04, steel));
    this.inner.add(ring(2.14, 0.07, brass));
    for (const z of [-1, 1])
      this.inner.add(rod(new THREE.Vector3(0, 0, z * 2.14), new THREE.Vector3(0, 0, z * 2.56), 0.035, brass));
    for (const x of [-1, 1])
      this.inner.add(rod(new THREE.Vector3(x * 1.78, 0, 0), new THREE.Vector3(x * 2.14, 0, 0), 0.03, brass));
    const top = ceramic();
    top.map = this.face;
    this.disc = new THREE.Mesh(new THREE.CylinderGeometry(1.8, 1.8, 0.16, 160), [brass, top, white]);
    this.inner.add(this.disc);
    const glow = new THREE.MeshBasicMaterial({
      color: new THREE.Color(0xf2c14e).multiplyScalar(2.2),
      transparent: true,
    });
    const needle = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.012, 1.4), glow);
    needle.position.z = -0.7;
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.02, 32), glow);
    this.hand.add(needle, hub);
    this.hand.position.y = 0.092;
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
    this.figure.rotation.x = -Math.PI / 2;
    this.figure.position.set(0, 0.084, -0.62);
    this.disc.add(this.hand, this.figure);
    this.hand.visible = this.figure.visible = false;
    this.outer.add(this.inner);
    this.base.add(this.stand, this.outer);
    this.group.add(this.base);
    this.group.traverse((o) => {
      if (o instanceof THREE.Mesh) o.castShadow = o.receiveShadow = true;
    });
  }

  // The dial as a gauge: the hand sweeps three quarters of a turn as the figure counts up to its
  // value, with a small label under it. Show fades both in.
  read(value: number, top: number, show: number, label = "") {
    this.hand.visible = this.figure.visible = show > 0;
    if (!show) return;
    this.hand.rotation.y = (-value / top) * Math.PI * 1.5;
    for (const m of [this.figure.material, (this.hand.children[0] as THREE.Mesh).material as THREE.Material])
      m.opacity = show;
    const text = value.toFixed(2);
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

  // Tilts the base by a (about x) and b (about z), rolling the rocker on the floor, and turns the
  // rings back so the dial stays exactly level. Spin turns the dial's ticks.
  tilt(a: number, b: number, spin: number) {
    this.base.position.set(-ROCKER * b, ROCKER, ROCKER * a);
    this.base.rotation.set(a, 0, b, "ZXY");
    this.outer.rotation.set(-a, 0, 0);
    this.inner.rotation.set(0, 0, -b);
    this.face.rotation = spin;
  }
}
