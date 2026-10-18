import * as THREE from "three";

// Gravity on the balls, in units per second squared.
const G = -20;
// Scratch for writing the instance matrices.
const m = new THREE.Matrix4();
const q = new THREE.Quaternion();
const s = new THREE.Vector3();
const p = new THREE.Vector3();

// One ball: where it is, where it settles, when it drops and its size.
export interface Ball {
  x: number;
  y: number;
  z: number;
  vy: number;
  rest: THREE.Vector3;
  start: number;
  radius: number;
  landed: boolean;
  shown: boolean;
}

// Balls that rain down, bounce and settle in their slot of a histogram.
export class Pile {
  balls: Ball[] = [];
  mesh: THREE.InstancedMesh;
  // Called the first time each ball lands.
  onLand?: (i: number) => void;

  // One ball per slot, with its radius, drop time and colour.
  constructor(rests: THREE.Vector3[], radii: number[], starts: number[], colors: THREE.Color[]) {
    const geometry = new THREE.SphereGeometry(1, 16, 12);
    // Lit balls: soft diffuse, a highlight and a rim, faded by uOpacity.
    const material = new THREE.ShaderMaterial({
      transparent: true,
      uniforms: { uOpacity: { value: 1 } },
      vertexShader: /* glsl */ `
        varying vec3 vN;
        varying vec3 vView;
        varying vec3 vColor;
        void main() {
          vColor = instanceColor;
          vec4 mv = modelViewMatrix * instanceMatrix * vec4(position, 1.0);
          vN = normalize(normalMatrix * mat3(instanceMatrix) * normal);
          vView = normalize(-mv.xyz);
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: /* glsl */ `
        uniform float uOpacity;
        varying vec3 vN;
        varying vec3 vView;
        varying vec3 vColor;
        void main() {
          vec3 n = normalize(vN);
          vec3 l = normalize(vec3(-0.4, 0.8, 0.5));
          float diffuse = max(dot(n, l), 0.0);
          float spec = pow(max(dot(reflect(-l, n), normalize(vView)), 0.0), 24.0);
          float rim = pow(1.0 - max(dot(n, normalize(vView)), 0.0), 2.5);
          vec3 col = vColor * (0.18 + 0.75 * diffuse) + vec3(1.0) * spec * 0.6 + vColor * rim * 1.4;
          gl_FragColor = vec4(col * uOpacity, uOpacity);
        }
      `,
    });
    this.mesh = new THREE.InstancedMesh(geometry, material, rests.length);
    this.mesh.frustumCulled = false;
    rests.forEach((rest, i) => {
      this.balls.push({
        x: rest.x,
        y: rest.y,
        z: rest.z,
        vy: 0,
        rest,
        start: starts[i],
        radius: radii[i],
        landed: false,
        shown: false,
      });
      this.mesh.setColorAt(i, colors[i]);
    });
    this.reset();
  }

  // Lifts every ball 10 or more up, a little off its slot, to drop again.
  reset() {
    this.balls.forEach((b, i) => {
      b.x = b.rest.x + Math.sin(i * 12.9898) * 0.5;
      b.y = 10 + (i % 7) * 0.4;
      b.z = b.rest.z;
      b.vy = 0;
      b.landed = false;
      b.shown = false;
    });
    this.write();
  }

  // Throws one ball back up; it falls onto its own slot again.
  bounce(i: number, speed: number) {
    this.balls[i].vy = speed;
  }

  // Drops each ball at its start time; writes only when one moved.
  step(dt: number, clock: number) {
    let changed = false;
    for (let i = 0; i < this.balls.length; i++) {
      const b = this.balls[i];
      if (clock < b.start) continue;
      if (!b.shown) b.shown = changed = true;
      if (b.landed && b.vy === 0) continue;
      changed = true;
      // Falls, drifting sideways onto its slot.
      b.vy += G * dt;
      b.y += b.vy * dt;
      b.x += (b.rest.x - b.x) * Math.min(1, dt * 5);
      // Lands, bouncing at 34% until under 1.2, then rests on its slot.
      if (b.y <= b.rest.y) {
        b.y = b.rest.y;
        if (!b.landed) this.onLand?.(i);
        b.landed = true;
        b.vy = Math.abs(b.vy) > 1.2 ? -b.vy * 0.34 : 0;
        if (b.vy === 0) b.x = b.rest.x;
      }
    }
    if (changed) this.write();
  }

  // Writes every ball into the instanced mesh, unshown ones at size 0.
  private write() {
    this.balls.forEach((b, i) => {
      s.setScalar(b.shown ? b.radius : 0);
      p.set(b.x, b.y, b.z);
      m.compose(p, q, s);
      this.mesh.setMatrixAt(i, m);
    });
    this.mesh.instanceMatrix.needsUpdate = true;
    this.mesh.computeBoundingSphere();
  }
}
