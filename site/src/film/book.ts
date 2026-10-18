import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { clamp, expo, inOut, mix, ramp, seeded, smooth } from "../shared/math";
import { gold } from "./gimbal";

// A 14 by 14 grid of 0.36 cubes 0.5 apart, 28 picked at each end.
const SIDE = 14;
const N = SIDE * SIDE;
const GAP = 0.5;
const CUBE = 0.36;
const PICK = 28;
// The height of the glass shelf the cubes stand on.
export const SHELF = 2.8;

// White at rest, gold for the longs, violet for the shorts, then pale.
const WHITE = new THREE.Color(0xf7f5fa);
const LONG = new THREE.Color(0xdcb05a);
const SHORT = new THREE.Color(0x6c50e6);
const PALE = new THREE.Color(0xe6e2ee);

// The book on a glass shelf, the best rising gold, the worst violet.
export class Book {
  group = new THREE.Group();
  // Cue times in seconds, which the film resets to the spoken words.
  times = { scan: 16.0, long: 16.8, short: 18.65, settle: 19.8, verify: 32.05 };
  // The cubes as one instanced mesh, each with its own glow.
  private cubes: THREE.InstancedMesh;
  private glow: THREE.InstancedBufferAttribute;
  private rank: number[];
  // Scratch matrix, rotation, position, scale and colour for each cube.
  private m = new THREE.Matrix4();
  private q = new THREE.Quaternion();
  private p = new THREE.Vector3();
  private s = new THREE.Vector3();
  private c = new THREE.Color();
  // The glass and its gold trim, which fade once the point is made.
  private glass: THREE.Mesh<THREE.BoxGeometry, THREE.MeshPhysicalMaterial>;
  private trim: THREE.MeshPhysicalMaterial;

  // Ranks the cubes in a fixed shuffle, then builds them, glass and trim.
  constructor() {
    const r = seeded(5);
    this.rank = [...Array(N).keys()].sort(() => r() - 0.5);
    const geometry = new RoundedBoxGeometry(1, 1, 1, 3, 0.06);
    this.glow = new THREE.InstancedBufferAttribute(new Float32Array(N), 1);
    geometry.setAttribute("glow", this.glow);
    const material = new THREE.MeshPhysicalMaterial({
      color: 0xffffff,
      roughness: 0.3,
      clearcoat: 1,
      clearcoatRoughness: 0.08,
    });
    // Patches the shader so each cube's glow adds its colour as light.
    material.onBeforeCompile = (s) => {
      s.vertexShader = s.vertexShader
        .replace("#include <common>", "#include <common>\nattribute float glow;\nvarying float vGlow;")
        .replace("#include <begin_vertex>", "#include <begin_vertex>\nvGlow = glow;");
      s.fragmentShader = s.fragmentShader
        .replace("#include <common>", "#include <common>\nvarying float vGlow;")
        .replace(
          "#include <emissivemap_fragment>",
          "#include <emissivemap_fragment>\ntotalEmissiveRadiance += vColor.rgb * vGlow;",
        );
    };
    this.cubes = new THREE.InstancedMesh(geometry, material, N);
    this.cubes.castShadow = this.cubes.receiveShadow = true;
    this.cubes.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(N * 3), 3);
    // A thin iridescent glass shelf 18 square, almost clear.
    const glass = (this.glass = new THREE.Mesh(
      new THREE.BoxGeometry(18, 0.05, 18),
      new THREE.MeshPhysicalMaterial({
        color: 0xffffff,
        roughness: 0.05,
        iridescence: 0.35,
        iridescenceIOR: 1.4,
        transparent: true,
        opacity: 0.2,
        envMapIntensity: 1.4,
        depthWrite: false,
      }),
    ));
    glass.position.y = SHELF - 0.025;
    // Gold bars along the four edges of the glass.
    const trim = (this.trim = gold());
    trim.transparent = true;
    for (const [x, z, w, d] of [
      [0, 9, 18.04, 0.04],
      [0, -9, 18.04, 0.04],
      [9, 0, 0.04, 18.04],
      [-9, 0, 0.04, 18.04],
    ]) {
      const bar = new THREE.Mesh(new THREE.BoxGeometry(w, 0.05, d), trim);
      bar.position.set(x, SHELF - 0.025, z);
      this.group.add(bar);
    }
    this.group.add(this.cubes, glass);
  }

  // Fades the glass and its gold edge, once the shelf has made its point.
  fade(k: number) {
    this.glass.material.opacity = 0.2 * k;
    this.glass.visible = k > 0;
    this.trim.opacity = k;
  }

  // Sets every cube to time t, lit by the agents passing over it.
  update(t: number, lights: THREE.Vector3[] = []) {
    const T = this.times;
    // A scan line crosses the grid in 0.9 s, the rest settle over 1.2 s.
    const scan = mix(4.4, -4.4, ramp(t, T.scan, T.scan + 0.9));
    const settle = inOut(ramp(t, T.settle, T.settle + 1.2));
    for (let i = 0; i < N; i++) {
      const x = ((i % SIDE) - (SIDE - 1) / 2) * GAP;
      const z = (Math.floor(i / SIDE) - (SIDE - 1) / 2) * GAP;
      const rank = this.rank[i];
      // Every cube bobs a little, each out of step with the others.
      const bob = Math.sin(t * 1.9 + rank * 0.7) * 0.02;
      let height = CUBE * (1 + bob);
      let y = SHELF + height / 2;
      let width = CUBE;
      // Lit by the scan line, which shines only until the longs rise.
      let glow = Math.exp(-(((z - scan) / 0.5) ** 2)) * 0.35 * (t < T.long ? 1 : 0);
      this.c.copy(WHITE);
      if (rank < PICK) {
        // The 28 best rise as gold columns, the best first and tallest.
        const k = expo(ramp(t, T.long + (rank / PICK) * 0.5, T.long + 0.9 + (rank / PICK) * 0.5));
        height = mix(CUBE, CUBE + 2.1 * (1 - rank / PICK) ** 0.9, k) * (1 + bob * 0.5);
        y = SHELF + height / 2;
        this.c.lerp(LONG, smooth(clamp(k * 1.4)));
      } else if (rank >= N - PICK) {
        // The 28 worst hang under the glass, the worst first and longest.
        const depth = (rank - (N - PICK) + 1) / PICK;
        const k = expo(ramp(t, T.short + (1 - depth) * 0.5, T.short + 0.9 + (1 - depth) * 0.5));
        height = mix(CUBE, CUBE + 2.1 * depth ** 0.9, k) * (1 + bob * 0.5);
        y = mix(SHELF + CUBE / 2, SHELF - 0.05 - height / 2, k);
        this.c.lerp(SHORT, smooth(clamp(k * 1.4)));
      } else {
        // The rest settle flat into pale tiles.
        height = mix(height, 0.035, settle);
        width = mix(CUBE, 0.3, settle);
        y = SHELF + height / 2;
        this.c.lerp(PALE, settle);
      }
      // Each passing agent lights the cubes near it.
      for (const l of lights) {
        const d2 = (l.x - x) ** 2 + (l.z - z) ** 2 + (l.y - y) ** 2 * 0.3;
        glow += Math.exp(-d2 / 1.2) * 0.2;
      }
      // At verify a wave of light runs out from the centre over the picks.
      const wave = t - T.verify - Math.hypot(x, z) * 0.12;
      if (wave > 0 && (rank < PICK || rank >= N - PICK)) glow += Math.exp(-wave * 2.2) * 0.4;
      this.p.set(x, y, z);
      this.s.set(width, height, width);
      this.m.compose(this.p, this.q, this.s);
      this.cubes.setMatrixAt(i, this.m);
      this.cubes.setColorAt(i, this.c);
      this.glow.setX(i, glow);
    }
    this.cubes.instanceMatrix.needsUpdate = true;
    this.cubes.instanceColor!.needsUpdate = true;
    this.glow.needsUpdate = true;
  }
}
