import * as THREE from "three";

// Points kept in each agent's trail.
const TRAIL = 22;
// Scratch reused every step, so the flock allocates nothing.
const d = new THREE.Vector3();
const m = new THREE.Matrix4();
const q = new THREE.Quaternion();
const s = new THREE.Vector3();
const acc = new THREE.Vector3();
const centre = new THREE.Vector3();
const heading = new THREE.Vector3();
// Speed limits in units per second, so no agent stalls or races off.
const TOP = 3.6;
const LOW = 1.2;

// One AI agent: position, velocity, its herd and its last 22 positions.
export interface Bird {
  p: THREE.Vector3;
  v: THREE.Vector3;
  herd: number;
  trail: Float32Array;
}

// Boids part, flock by herd and chase their stock in a soft sphere.
export class Flock {
  birds: Bird[] = [];
  // Where each herd heads, its stock's place, set by the scene.
  goals: THREE.Vector3[] = [];
  mesh: THREE.InstancedMesh;
  lines: THREE.LineSegments;
  // The herds the scene lights up, all when empty; the rest dim to 12%.
  focus: number[] = [];
  private colors: THREE.Color[];

  // Agents start in a 12 unit cube, with instanced balls and trail lines.
  constructor(herds: number[], colors: THREE.Color[], radius = 0.085) {
    this.colors = colors;
    // Park-Miller numbers from seed 1, so every load starts alike.
    let seed = 1;
    const r = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    herds.forEach((herd) => {
      const p = new THREE.Vector3(r() - 0.5, r() - 0.5, r() - 0.5).multiplyScalar(12);
      const trail = new Float32Array(TRAIL * 3);
      for (let i = 0; i < TRAIL; i++) trail.set(p.toArray(), i * 3);
      this.birds.push({ p, v: new THREE.Vector3(r() - 0.5, r() - 0.5, r() - 0.5).multiplyScalar(2), herd, trail });
    });
    this.goals = colors.map(() => new THREE.Vector3());
    // An instanced sphere per agent in its herd's colour at 1.5 times.
    this.mesh = new THREE.InstancedMesh(
      new THREE.SphereGeometry(radius, 12, 8),
      new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 1,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
      herds.length,
    );
    this.mesh.frustumCulled = false;
    herds.forEach((h, i) => this.mesh.setColorAt(i, colors[h].clone().multiplyScalar(1.5)));
    // Trails as line segments, 21 per agent, faded in each step.
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(herds.length * (TRAIL - 1) * 6), 3));
    g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(herds.length * (TRAIL - 1) * 6), 3));
    this.lines = new THREE.LineSegments(
      g,
      new THREE.LineBasicMaterial({
        vertexColors: true,
        transparent: true,
        opacity: 0.9,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    this.lines.frustumCulled = false;
  }

  // Steers every agent, then moves it and redraws its trail.
  step(dt: number, time: number) {
    const n = this.birds.length;
    for (let i = 0; i < n; i++) {
      const b = this.birds[i];
      acc.set(0, 0, 0);
      centre.set(0, 0, 0);
      heading.set(0, 0, 0);
      let mates = 0;
      // Closer than 0.9, agents push apart; mates within 5 are averaged.
      for (let j = 0; j < n; j++) {
        if (i === j) continue;
        const o = this.birds[j];
        d.copy(b.p).sub(o.p);
        const dist = d.length();
        if (dist < 0.9) acc.addScaledVector(d, ((0.9 - dist) * 9) / Math.max(dist, 0.05));
        if (o.herd === b.herd && dist < 5) {
          centre.add(o.p);
          heading.add(o.v);
          mates++;
        }
      }
      // Cohesion to the mates' centre, alignment to their heading.
      if (mates) {
        acc.addScaledVector(centre.divideScalar(mates).sub(b.p), 0.9);
        acc.addScaledVector(heading.divideScalar(mates).sub(b.v), 0.8);
      }
      // Seeks the herd's goal from beyond 1.2 and backs off a little inside.
      d.copy(this.goals[b.herd]).sub(b.p);
      const reach = d.length();
      acc.addScaledVector(d, (reach > 1.2 ? 1.6 : -0.6) / Math.max(reach, 0.5));
      // A gentle wander, and a pull back inward past radius 6.
      acc.x += Math.sin(time * 0.7 + i) * 0.6;
      acc.y += Math.cos(time * 0.9 + i * 1.3) * 0.6;
      acc.z += Math.sin(time * 0.5 + i * 0.7) * 0.6;
      if (b.p.length() > 6) acc.addScaledVector(b.p, -0.6);
      // Speed is held between LOW (1.2) and TOP (3.6).
      b.v.addScaledVector(acc, dt);
      const speed = b.v.length();
      if (speed > TOP) b.v.multiplyScalar(TOP / speed);
      else if (speed < LOW) b.v.multiplyScalar(LOW / Math.max(speed, 1e-3));
    }
    // A second pass moves them, so every steer read the same positions.
    const pos = this.lines.geometry.attributes.position.array as Float32Array;
    const col = this.lines.geometry.attributes.color.array as Float32Array;
    for (let i = 0; i < n; i++) {
      const b = this.birds[i];
      b.p.addScaledVector(b.v, dt);
      b.trail.copyWithin(3, 0, (TRAIL - 1) * 3);
      b.trail[0] = b.p.x;
      b.trail[1] = b.p.y;
      b.trail[2] = b.p.z;
      // Out of focus an agent shrinks to 0.6 and its trail dims to 12%.
      const lit = !this.focus.length || this.focus.includes(b.herd) ? 1 : 0.12;
      s.setScalar(lit > 0.5 ? 1 : 0.6);
      m.compose(b.p, q, s);
      this.mesh.setMatrixAt(i, m);
      // Trail segments fade from 60% at the head toward the tail.
      const c = this.colors[b.herd];
      for (let k = 0; k < TRAIL - 1; k++) {
        const o = (i * (TRAIL - 1) + k) * 6;
        const fadeA = (1 - k / TRAIL) * lit * 0.6;
        const fadeB = (1 - (k + 1) / TRAIL) * lit * 0.6;
        for (let a = 0; a < 6; a++) pos[o + a] = b.trail[k * 3 + a];
        col[o] = c.r * fadeA;
        col[o + 1] = c.g * fadeA;
        col[o + 2] = c.b * fadeA;
        col[o + 3] = c.r * fadeB;
        col[o + 4] = c.g * fadeB;
        col[o + 5] = c.b * fadeB;
      }
    }
    this.mesh.instanceMatrix.needsUpdate = true;
    this.lines.geometry.attributes.position.needsUpdate = true;
    this.lines.geometry.attributes.color.needsUpdate = true;
  }
}
