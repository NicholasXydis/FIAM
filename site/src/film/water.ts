import * as THREE from "three";
import { Reflector } from "three/addons/objects/Reflector.js";

export const SPEED = 5.5;

export interface Shock {
  x: number;
  z: number;
  at: number;
  amp: number;
  up: boolean;
}

const sky = /* glsl */ `
  uniform float uDawn, uDip;
  varying vec3 vDir;
  void main() {
    vec3 d = normalize(vDir);
    float e = d.y + uDip;
    vec3 zenith = mix(vec3(0.004, 0.003, 0.01), vec3(0.03, 0.022, 0.06), uDawn);
    vec3 horizon = mix(vec3(0.03, 0.02, 0.06), vec3(0.2, 0.12, 0.18), uDawn);
    vec3 col = mix(horizon, zenith, smoothstep(0.0, 0.45, e));
    col = mix(col, vec3(0.004, 0.003, 0.01), smoothstep(0.0, -0.2, e));
    vec3 gold = vec3(1.0, 0.72, 0.3);
    col += gold * exp(-e * e / 0.00002) * (0.25 + 0.9 * uDawn);
    col += gold * exp(-e * e / 0.004) * (0.02 + 0.12 * uDawn);
    gl_FragColor = vec4(col, 1.0);
  }
`;

const vertex = /* glsl */ `
  uniform mat4 textureMatrix;
  varying vec4 vUv;
  varying vec3 vWorld;
  void main() {
    vUv = textureMatrix * vec4(position, 1.0);
    vWorld = (modelMatrix * vec4(position, 1.0)).xyz;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const fragment = (n: number) => /* glsl */ `
  uniform vec3 color;
  uniform sampler2D tDiffuse;
  uniform float uTime, uSwell, uVisible;
  uniform vec4 uShocks[${n}];
  uniform vec3 uTints[${n}];
  varying vec4 vUv;
  varying vec3 vWorld;
  void main() {
    vec2 p = vWorld.xz;
    vec2 grad = vec2(0.0);
    vec3 glow = vec3(0.0);
    for (int i = 0; i < ${n}; i++) {
      vec4 s = uShocks[i];
      float age = uTime - s.z;
      if (age <= 0.0) continue;
      vec2 o = p - s.xy;
      float r = length(o) + 1e-4;
      float d = r - age * ${SPEED.toFixed(2)};
      float w = 0.7 + age * 0.35;
      float env = exp(-d * d / (w * w)) * exp(-age * 0.42) / sqrt(1.0 + r * 0.25);
      float k = 3.2;
      grad += (o / r) * s.w * k * cos(d * k) * env;
      glow += uTints[i] * s.w * exp(-d * d / (0.16 * w * w)) * exp(-age * 1.1) / sqrt(1.0 + r * 0.2);
    }
    grad += uSwell * vec2(sin(p.x * 0.9 + uTime * 0.8) + sin(p.y * 1.3 - uTime * 0.6), cos(p.y * 0.7 + uTime * 0.7));
    vec3 n = normalize(vec3(-grad.x, 1.0, -grad.y));
    vec3 v = normalize(cameraPosition - vWorld);
    float fresnel = 0.03 + 0.97 * pow(1.0 - max(dot(n, v), 0.0), 5.0);
    vec4 uv = vUv;
    uv.xy += n.xz * 0.9 * uv.w * 0.04;
    vec3 reflection = texture2DProj(tDiffuse, uv).rgb;
    vec3 col = vec3(0.003, 0.002, 0.007) + reflection * mix(0.35, 1.0, fresnel) * color;
    col += glow * 2.2;
    gl_FragColor = vec4(col, uVisible);
  }
`;

// A night sea under a sky that slowly turns to dawn. Every shock sends a glowing ripple across it,
// red when the market fell, cyan when it jumped, and the water reflects everything above it.
export class Water {
  group = new THREE.Group();
  moon: THREE.DirectionalLight;
  private sky: THREE.Mesh<THREE.SphereGeometry, THREE.ShaderMaterial>;
  private sea: Reflector;

  constructor(
    public shocks: Shock[],
    size: THREE.Vector2,
  ) {
    this.sky = new THREE.Mesh(
      new THREE.SphereGeometry(300, 64, 32),
      new THREE.ShaderMaterial({
        side: THREE.BackSide,
        depthWrite: false,
        uniforms: { uDawn: { value: 0 }, uDip: { value: 0 } },
        vertexShader:
          "varying vec3 vDir; void main(){ vDir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
        fragmentShader: sky,
      }),
    );
    const n = shocks.length;
    this.sea = new Reflector(new THREE.PlaneGeometry(600, 600), {
      clipBias: 0.003,
      textureWidth: size.x,
      textureHeight: size.y,
      color: 0xffffff,
      multisample: 4,
      shader: {
        name: "Sea",
        uniforms: {
          color: { value: null },
          tDiffuse: { value: null },
          textureMatrix: { value: null },
          uTime: { value: 0 },
          uSwell: { value: 0.02 },
          uVisible: { value: 1 },
          uShocks: { value: shocks.map((s) => new THREE.Vector4(s.x, s.z, s.at, s.amp)) },
          uTints: { value: shocks.map((s) => new THREE.Color(s.up ? 0x4fd0ea : 0xff4a26)) },
        },
        vertexShader: vertex,
        fragmentShader: fragment(n),
      },
    });
    this.sea.rotation.x = -Math.PI / 2;
    (this.sea.material as THREE.ShaderMaterial).transparent = true;
    this.moon = new THREE.DirectionalLight(0xc9c0ff, 0.6);
    this.moon.position.set(4, 10, 8);
    this.group.add(this.sky, this.sea, this.moon);
  }

  resize(size: THREE.Vector2) {
    this.sea.getRenderTarget().setSize(size.x, size.y);
  }

  // How high the sea stands at a point, for anything floating on it.
  height(x: number, z: number, t: number) {
    let h = 0;
    for (const s of this.shocks) {
      const age = t - s.at;
      if (age <= 0) continue;
      const r = Math.hypot(x - s.x, z - s.z);
      const d = r - age * SPEED;
      const w = 0.7 + age * 0.35;
      h += s.amp * Math.sin(d * 3.2) * Math.exp(-(d * d) / (w * w)) * Math.exp(-age * 0.42);
    }
    return h;
  }

  // Visible fades the sea itself away, leaving the sky, for what lies beneath it.
  update(t: number, dawn: number, swell: number, visible = 1) {
    const m = this.sea.material as THREE.ShaderMaterial;
    const u = m.uniforms;
    u.uTime.value = t;
    u.uSwell.value = swell;
    u.uVisible.value = visible;
    m.depthWrite = visible >= 1;
    this.sea.visible = visible > 0;
    this.sky.material.uniforms.uDawn.value = dawn;
  }

  // The sky follows the camera, its gold line lowered to meet the far edge of the sea.
  follow(camera: THREE.Camera) {
    this.sky.position.copy(camera.position);
    this.sky.material.uniforms.uDip.value = Math.min(camera.position.y / 290, 0.03);
  }
}
