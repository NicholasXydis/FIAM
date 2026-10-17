import * as THREE from "three";
import { clamp, inOut, mix, out, ramp, seeded, smooth, span } from "./ease";
import { Strip } from "./strip";

const COUNT = 7;
const TAIL = 40;
const STEP = 0.024;
const CARDS = 160;
const TINTS = [0xf2c14e, 0x9fe3f0, 0xb9a2ff, 0xffffff, 0xf2c14e, 0x9fe3f0, 0xb9a2ff];
const TAU = Math.PI * 2;
const FORWARD = new THREE.Vector3(0, 0, 1);

export interface Times {
  enter: number;
  read: number;
  argue: number;
  ring: number;
  verify: number;
  rest: number;
}

// A page of a filing as the agents see it: a pale page of text, with the company's name and every
// identifying detail blacked out so no model can lean on what it remembers.
function page() {
  const c = document.createElement("canvas");
  c.width = 192;
  c.height = 240;
  const g = c.getContext("2d")!;
  g.fillStyle = "rgba(246,243,252,0.94)";
  g.beginPath();
  g.roundRect(4, 4, 184, 232, 10);
  g.fill();
  g.fillStyle = "#0b0912";
  g.fillRect(22, 24, 96, 16);
  g.fillStyle = "rgba(40,34,60,0.55)";
  for (let y = 58, n = 0; y < 214; y += 14, n++) {
    g.fillRect(22, y, n % 4 === 3 ? 100 : 148, 5);
    if (n % 3 === 1) {
      g.fillStyle = "#0b0912";
      g.fillRect(40 + ((n * 37) % 70), y - 3, 46, 11);
      g.fillStyle = "rgba(40,34,60,0.55)";
    }
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// Seven agents as points of light. They come out of the book, circle it, pull in thousands of
// filings to read, throw threads of light between each other as they challenge the thinking, then
// settle into one even ring as every number checks out.
export class Agents {
  group = new THREE.Group();
  now: THREE.Vector3[] = [];
  centre = new THREE.Vector3(0, 3.2, 0);
  private orbs: THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>[] = [];
  private lights: THREE.PointLight[] = [];
  private trails: Strip[] = [];
  private beams: Strip[] = [];
  private ring = new Strip(COUNT + 1, 0xf2c14e, 1.6, 2.2);
  private pulse = new Strip(97, 0xf2c14e, 2.4, 1.6);
  private tail = [...Array(TAIL)].map(() => new THREE.Vector3());
  private cards: THREE.InstancedMesh;
  private spawn: THREE.Vector3[] = [];
  private start: number[] = [];
  private spin: number[] = [];
  private v = new THREE.Vector3();
  private y = new THREE.Vector3(0, 1, 0);
  private x = new THREE.Vector3(1, 0, 0);
  private m = new THREE.Matrix4();
  private q = new THREE.Quaternion();
  private z = new THREE.Quaternion();
  private s = new THREE.Vector3();

  constructor(public times: Times) {
    const T = times;
    for (let i = 0; i < COUNT; i++) {
      const tint = new THREE.Color(TINTS[i]);
      const orb = new THREE.Mesh(
        new THREE.SphereGeometry(0.11, 24, 12),
        new THREE.MeshBasicMaterial({ color: tint.clone().multiplyScalar(9), transparent: true }),
      );
      const light = new THREE.PointLight(tint, 0, 7, 1.6);
      const trail = new Strip(TAIL, tint, 3.2, 1.8);
      const beam = new Strip(16, tint, 1.2, 2.4);
      this.orbs.push(orb);
      this.lights.push(light);
      this.trails.push(trail);
      this.beams.push(beam);
      this.now.push(new THREE.Vector3());
      this.group.add(orb, light, trail.mesh, beam.mesh);
    }
    const r = seeded(41);
    for (let i = 0; i < CARDS; i++) {
      const a = r() * TAU;
      const e = (r() - 0.35) * 1.1;
      const d = 9 + r() * 8;
      this.spawn.push(new THREE.Vector3(Math.cos(a) * Math.cos(e) * d, Math.sin(e) * d, Math.sin(a) * Math.cos(e) * d));
      this.start.push(T.read - 0.5 + (i / CARDS) * 2.6 + r() * 0.3);
      this.spin.push((r() - 0.5) * 3);
    }
    this.cards = new THREE.InstancedMesh(
      new THREE.PlaneGeometry(0.3, 0.375),
      new THREE.MeshBasicMaterial({
        map: page(),
        color: 0x9a94ad,
        transparent: true,
        opacity: 0.85,
        depthWrite: false,
        side: THREE.DoubleSide,
      }),
      CARDS,
    );
    this.cards.frustumCulled = false;
    this.group.add(this.ring.mesh, this.pulse.mesh, this.cards);
  }

  // Where agent i is at time t, a pure function so its trail is just its own past.
  at(i: number, t: number, into: THREE.Vector3) {
    const c = this.centre;
    const grow = out(ramp(t, this.times.enter, this.times.enter + 1.3));
    const read =
      smooth(ramp(t, this.times.read, this.times.read + 0.8)) *
      (1 - smooth(ramp(t, this.times.argue + 0.2, this.times.argue + 1.0)));
    const r = mix(4.9, 3.0, read) * grow * (1 + 0.07 * Math.sin(t * 0.8 + i * 1.7));
    const tilt = (0.3 + 0.55 * ((i * 0.618) % 1)) * (1 - read * 0.7);
    const angle = i * 2.4 + t * (0.95 + 0.11 * i) * (i % 2 ? 1 : -1);
    this.v.set(Math.cos(angle) * r, 0, Math.sin(angle) * r).applyAxisAngle(this.x, tilt);
    this.v.applyAxisAngle(this.y, (i * TAU) / COUNT);
    this.v.y += mix(0.9, 0.35, read);
    const a = (i * TAU) / COUNT + t * 0.22;
    const k = inOut(ramp(t, this.times.ring, this.times.ring + 1.1));
    into.set(
      c.x + mix(this.v.x, Math.cos(a) * 4.2, k),
      c.y + mix(this.v.y, 0.75, k),
      c.z + mix(this.v.z, Math.sin(a) * 4.2, k),
    );
    return into;
  }

  update(t: number, size: THREE.Vector2, camera: THREE.Camera, dim = 1) {
    const shown = ramp(t, this.times.enter, this.times.enter + 0.7) * dim;
    this.group.visible = shown > 0;
    if (!shown) return;
    const trail = shown * (1 - ramp(t, this.times.rest, this.times.rest + 0.8));
    for (let i = 0; i < COUNT; i++) {
      this.at(i, t, this.now[i]);
      this.orbs[i].position.copy(this.now[i]);
      this.orbs[i].material.opacity = shown;
      this.lights[i].position.copy(this.now[i]);
      this.lights[i].intensity = 2.2 * shown;
      for (let k = 0; k < TAIL; k++) this.at(i, Math.max(this.times.enter, t - k * STEP), this.tail[k]);
      this.trails[i].set(
        this.tail,
        (k) => trail * 0.9 * (1 - k / TAIL) ** 1.6,
        (k) => 1 - k / TAIL,
      );
      this.trails[i].viewport(size);
      this.trails[i].mesh.visible = trail > 0.01;
    }
    const argue = span(t, this.times.argue - 0.1, this.times.ring + 0.3, 0.25, 0.45);
    for (let i = 0; i < COUNT; i++) {
      const a = this.now[i];
      const b = this.now[(i + 3) % COUNT];
      const flicker = 0.55 + 0.45 * Math.sin(t * 8 + i * 2.1);
      const points = [...Array(16)].map((_, k) => {
        const u = k / 15;
        return a
          .clone()
          .lerp(b, u)
          .lerp(this.centre, Math.sin(u * Math.PI) * 0.25);
      });
      this.beams[i].set(points, (k) => argue * flicker * Math.sin((k / 15) * Math.PI) ** 0.5);
      this.beams[i].viewport(size);
      this.beams[i].mesh.visible = argue > 0.01;
    }
    const joined = smooth(ramp(t, this.times.verify + 0.3, this.times.verify + 1.0)) * dim;
    this.ring.set([...this.now, this.now[0]], () => joined * 0.9);
    this.ring.viewport(size);
    this.ring.mesh.visible = joined > 0.01;
    const age = t - this.times.verify;
    const reach = out(ramp(age, 0, 1.8)) * 10;
    const circle = [...Array(97)].map((_, k) =>
      new THREE.Vector3(Math.cos((k / 96) * TAU) * reach, 0, Math.sin((k / 96) * TAU) * reach).add(this.centre),
    );
    const fade = age > 0 ? Math.exp(-age * 1.6) : 0;
    this.pulse.set(circle, () => fade);
    this.pulse.viewport(size);
    this.pulse.mesh.visible = fade > 0.01 && dim === 1;
    this.file(t, camera);
  }

  // The filings: each card flies in from the dark, speeding up, and is taken in by one agent.
  private file(t: number, camera: THREE.Camera) {
    let any = false;
    for (let i = 0; i < CARDS; i++) {
      const age = (t - this.start[i]) / 1.3;
      if (age <= 0 || age >= 1) {
        this.m.makeScale(0, 0, 0);
        this.cards.setMatrixAt(i, this.m);
        continue;
      }
      any = true;
      const k = age * age;
      this.v
        .copy(this.spawn[i])
        .add(this.centre)
        .lerp(this.now[i % COUNT], k);
      this.v.y += Math.sin(k * Math.PI) * 0.6;
      this.z.setFromAxisAngle(FORWARD, this.spin[i] * (1 - k));
      this.q.copy(camera.quaternion).multiply(this.z);
      const near = clamp((this.v.distanceTo(camera.position) - 2) / 5);
      this.s.setScalar((1 - k ** 4) * out(clamp(age / 0.12)) * (0.4 + 0.6 * near));
      this.m.compose(this.v, this.q, this.s);
      this.cards.setMatrixAt(i, this.m);
    }
    this.cards.visible = any;
    this.cards.instanceMatrix.needsUpdate = true;
  }
}
