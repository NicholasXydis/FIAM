import * as THREE from "three";
import { seeded } from "./ease";

const RADIUS = 330;
const GAP = 5.4;
const PLANET = 1100;
const CLUSTERS = 7;

// Where a light sits once the herd has gathered it: drawn toward its cluster and turned around it.
const herd = /* glsl */ `
  attribute vec3 pull;
  attribute vec2 birth;
  uniform float uTime, uReach, uGrow, uHerd, uPanic, uFade;
  uniform vec2 uOrigin;
  vec3 gather(vec3 home, float seed) {
    float k = uHerd * (0.35 + 0.45 * seed);
    vec3 off = home - pull;
    float a = uHerd * (1.2 + 1.6 * seed) + uTime * 0.05 * uHerd;
    float c = cos(a), s = sin(a);
    off.xz = mat2(c, -s, s, c) * off.xz;
    return pull + off * (1.0 - k * 0.75);
  }
  float shown(vec3 home) {
    float r = length(home.xz - uOrigin);
    return smoothstep(uReach, uReach - 24.0, r) * step(birth.x, uGrow);
  }
  float front(vec3 home) {
    return exp(-pow((length(home.xz - uOrigin) - uReach) / 7.0, 2.0));
  }
  float shock(vec3 home) {
    if (uPanic <= 0.0) return 0.0;
    float d = length(home.xz - pull.xz) + 20.0 * birth.y;
    return exp(-pow((d - uPanic * 70.0) / 9.0, 2.0)) + 0.35 * smoothstep(0.0, 1.2, uPanic);
  }
`;

const nodeVertex = /* glsl */ `
  attribute vec3 tint;
  attribute float seed;
  uniform float uPx;
  varying vec3 vCol;
  ${herd}
  void main() {
    vec3 p = gather(position, seed);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    float twinkle = 0.65 + 0.35 * sin(uTime * (0.8 + 2.4 * seed) + seed * 40.0);
    float depth = max(-mv.z, 0.1);
    float hot = shock(position);
    float edge = front(position);
    gl_PointSize = clamp(uPx * (0.7 + seed) / depth, 1.4, 10.0) * (1.0 + edge * 0.4 + hot * 0.4) * (1.0 - 0.3 * uHerd);
    vec3 red = vec3(1.0, 0.22, 0.1) * 2.2;
    vCol = mix(tint, red, clamp(hot, 0.0, 1.0)) * (shown(position) * twinkle + edge * 1.1 + hot * 0.7) * (1.0 - 0.72 * uHerd) * (1.0 - 0.9 * uHerd * (0.35 + 0.45 * seed));
    vCol *= uFade * exp(-depth * 0.0016) * smoothstep(1.5, 9.0, depth);
    gl_Position = projectionMatrix * mv;
  }
`;

const nodeFragment = /* glsl */ `
  varying vec3 vCol;
  void main() {
    vec2 q = gl_PointCoord * 2.0 - 1.0;
    float d = dot(q, q);
    if (d > 1.0) discard;
    gl_FragColor = vec4(vCol * (1.0 - d) * (1.0 - d), 1.0);
  }
`;

const edgeVertex = /* glsl */ `
  attribute float along;
  attribute float seed;
  attribute vec2 phase;
  varying float vAlong;
  varying vec2 vPhase;
  varying float vOn;
  varying float vHot;
  varying float vDepth;
  ${herd}
  void main() {
    vec4 mv = modelViewMatrix * vec4(gather(position, seed), 1.0);
    vAlong = along;
    vPhase = phase;
    vOn = shown(position) + front(position) * 1.8;
    vHot = shock(position);
    vDepth = max(-mv.z, 0.1);
    gl_Position = projectionMatrix * mv;
  }
`;

const edgeFragment = /* glsl */ `
  uniform float uTime, uFade, uHerd;
  uniform vec3 uBase, uGold;
  varying float vAlong;
  varying vec2 vPhase;
  varying float vOn;
  varying float vHot;
  varying float vDepth;
  void main() {
    float p = fract(vAlong - uTime * (0.35 + 0.5 * vPhase.y) + vPhase.x);
    float pulse = exp(-pow((p - 0.5) / 0.06, 2.0)) * step(0.45, vPhase.y);
    vec3 red = vec3(1.0, 0.25, 0.12);
    vec3 col = (mix(uBase, red, clamp(vHot, 0.0, 1.0)) * 0.16 * vOn + uGold * pulse * min(vOn, 1.0) * 1.4) * (1.0 - 0.95 * uHerd);
    gl_FragColor = vec4(col * uFade * exp(-vDepth * 0.0028) * smoothstep(1.5, 9.0, vDepth), 1.0);
  }
`;

// Thousands of AI agents across a curved world, joined by threads that carry pulses of gold. They
// light up as they arrive, then crowd into a few clusters, the herd, and can panic together.
export class Lattice {
  group = new THREE.Group();
  attractors: THREE.Vector3[] = [];
  private nodes: THREE.Points<THREE.BufferGeometry, THREE.ShaderMaterial>;
  private edges: THREE.LineSegments<THREE.BufferGeometry, THREE.ShaderMaterial>;
  private positions: number[] = [];

  constructor() {
    const r = seeded(29);
    for (let i = 0; i < CLUSTERS; i++) {
      const a = (i / CLUSTERS) * Math.PI * 2 + r() * 0.6;
      const d = 55 + r() * 170;
      this.attractors.push(new THREE.Vector3(Math.cos(a) * d, 0, Math.sin(a) * d));
    }
    const rows = Math.ceil(RADIUS / (GAP * 0.866));
    const cols = Math.ceil(RADIUS / GAP);
    const index = new Map<string, number>();
    const pos: number[] = [];
    const pull: number[] = [];
    const birth: number[] = [];
    const tint: number[] = [];
    const seed: number[] = [];
    const palette = [new THREE.Color(0xf2c14e), new THREE.Color(0xb9a2ff), new THREE.Color(0x9fe3f0)];
    const curve = (x: number, z: number) => -(x * x + z * z) / (2 * PLANET);
    for (let j = -rows; j <= rows; j++) {
      for (let i = -cols; i <= cols; i++) {
        const x = (i + (j % 2) * 0.5) * GAP + (r() - 0.5) * GAP * 0.55;
        const z = j * GAP * 0.866 + (r() - 0.5) * GAP * 0.55;
        const d = Math.hypot(x, z);
        if (d > RADIUS || d < 7) continue;
        index.set(`${i},${j}`, pos.length / 3);
        pos.push(x, curve(x, z), z);
        const near = this.attractors.reduce((a, b) =>
          b.distanceToSquared(new THREE.Vector3(x, 0, z)) < a.distanceToSquared(new THREE.Vector3(x, 0, z)) ? b : a,
        );
        pull.push(near.x, curve(near.x, near.z), near.z);
        birth.push(r(), r());
        const c = palette[r() < 0.3 ? 0 : r() < 0.7 ? 1 : 2];
        const power = 0.6 + r() * 0.9;
        tint.push(c.r * power, c.g * power, c.b * power);
        seed.push(r());
      }
    }
    this.positions = pos;
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("pull", new THREE.Float32BufferAttribute(pull, 3));
    g.setAttribute("birth", new THREE.Float32BufferAttribute(birth, 2));
    g.setAttribute("tint", new THREE.Float32BufferAttribute(tint, 3));
    g.setAttribute("seed", new THREE.Float32BufferAttribute(seed, 1));
    const shared = {
      uTime: { value: 0 },
      uReach: { value: 0 },
      uGrow: { value: 1 },
      uHerd: { value: 0 },
      uPanic: { value: 0 },
      uFade: { value: 1 },
      uOrigin: { value: new THREE.Vector2() },
    };
    this.nodes = new THREE.Points(
      g,
      new THREE.ShaderMaterial({
        vertexShader: nodeVertex,
        fragmentShader: nodeFragment,
        uniforms: { ...shared, uPx: { value: 1000 } },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    const ep: number[] = [];
    const ePull: number[] = [];
    const eBirth: number[] = [];
    const eSeed: number[] = [];
    const along: number[] = [];
    const phase: number[] = [];
    const copy = (from: number[], to: number[], i: number, n: number) => to.push(...from.slice(i * n, i * n + n));
    for (const [key, a] of index) {
      const [i, j] = key.split(",").map(Number);
      for (const [di, dj] of [
        [1, 0],
        [j % 2 ? 1 : 0, 1],
        [j % 2 ? 0 : -1, 1],
      ]) {
        const b = index.get(`${i + di},${j + dj}`);
        if (b === undefined || r() < 0.18) continue;
        for (const v of [a, b]) {
          copy(pos, ep, v, 3);
          copy(pull, ePull, v, 3);
          copy(birth, eBirth, v, 2);
          copy(seed, eSeed, v, 1);
        }
        along.push(0, 1);
        const s = [r(), r()];
        phase.push(...s, ...s);
      }
    }
    const eg = new THREE.BufferGeometry();
    eg.setAttribute("position", new THREE.Float32BufferAttribute(ep, 3));
    eg.setAttribute("pull", new THREE.Float32BufferAttribute(ePull, 3));
    eg.setAttribute("birth", new THREE.Float32BufferAttribute(eBirth, 2));
    eg.setAttribute("seed", new THREE.Float32BufferAttribute(eSeed, 1));
    eg.setAttribute("along", new THREE.Float32BufferAttribute(along, 1));
    eg.setAttribute("phase", new THREE.Float32BufferAttribute(phase, 2));
    this.edges = new THREE.LineSegments(
      eg,
      new THREE.ShaderMaterial({
        vertexShader: edgeVertex,
        fragmentShader: edgeFragment,
        uniforms: {
          ...shared,
          uBase: { value: new THREE.Color(0x8f7ae6) },
          uGold: { value: new THREE.Color(0xf2c14e).multiplyScalar(1.6) },
        },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    this.nodes.frustumCulled = this.edges.frustumCulled = false;
    this.group.add(this.edges, this.nodes);
  }

  // The light nearest a point on the ground, where the opening shot begins.
  near(x: number, z: number) {
    let best = 0;
    let dist = Infinity;
    for (let i = 0; i < this.positions.length; i += 3) {
      const d = (this.positions[i] - x) ** 2 + (this.positions[i + 2] - z) ** 2;
      if (d < dist) [dist, best] = [d, i];
    }
    return new THREE.Vector3(...this.positions.slice(best, best + 3));
  }

  // Reach is how far the light has spread from the origin, grow the share of agents that exist yet,
  // herd how far they have crowded together, panic the seconds since the herd broke.
  update(
    t: number,
    size: THREE.Vector2,
    { reach = 1e4, origin = [0, 0], grow = 1, herd = 0, panic = 0, fade = 1 } = {} as {
      reach?: number;
      origin?: number[];
      grow?: number;
      herd?: number;
      panic?: number;
      fade?: number;
    },
  ) {
    const u = this.nodes.material.uniforms;
    u.uTime.value = t;
    u.uReach.value = reach;
    u.uOrigin.value.set(origin[0], origin[1]);
    u.uGrow.value = grow;
    u.uHerd.value = herd;
    u.uPanic.value = panic;
    u.uFade.value = fade;
    u.uPx.value = size.y * 2.2;
  }
}
