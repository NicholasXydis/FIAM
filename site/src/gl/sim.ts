import * as THREE from "three";
import { GPUComputationRenderer, type Variable } from "three/addons/misc/GPUComputationRenderer.js";
import { hash, simplex } from "./glsl";

export const SIDE = 128;
export const N = SIDE * SIDE;

const color = new THREE.Color();

// One arrangement of every particle: where it rests (w is its size, negative to orbit the y axis)
// and how it looks (rgb in linear light, a its brightness).
export class Formation {
  pos = new Float32Array(N * 4);
  col = new Float32Array(N * 4);

  put(i: number, x: number, y: number, z: number, size: number, hex: number | THREE.Color, alpha = 1) {
    const o = i * 4;
    this.pos[o] = x;
    this.pos[o + 1] = y;
    this.pos[o + 2] = z;
    this.pos[o + 3] = size;
    const c = typeof hex === "number" ? color.setHex(hex) : hex;
    this.col[o] = c.r;
    this.col[o + 1] = c.g;
    this.col[o + 2] = c.b;
    this.col[o + 3] = alpha;
  }

  hide(i: number) {
    const o = i * 4;
    this.pos[o + 3] = 0;
    this.col[o + 3] = 0;
  }

  x(i: number) {
    return this.pos[i * 4];
  }
  y(i: number) {
    return this.pos[i * 4 + 1];
  }
  z(i: number) {
    return this.pos[i * 4 + 2];
  }
}

const velocity = /* glsl */ `
uniform float uTime, uDt, uSwitch, uStagger, uStiff, uDamp, uFlow, uFlowScale, uSpin;
uniform vec3 uRayO, uRayD, uWaveC;
uniform float uMouse, uMouseR, uWaveT, uWaveAmp, uWaveSpeed;
uniform sampler2D tPrev, tNext;
${hash}
${simplex}
vec3 orbit(vec4 t) {
  if (t.w >= 0.0) return t.xyz;
  float r = length(t.xz);
  float a = uTime * uSpin * 1.8 / (1.0 + 0.14 * r);
  float c = cos(a), s = sin(a);
  return vec3(c * t.x - s * t.z, t.y, s * t.x + c * t.z);
}
void main() {
  vec2 uv = gl_FragCoord.xy / resolution.xy;
  vec3 p = texture2D(texturePosition, uv).xyz;
  vec3 v = texture2D(textureVelocity, uv).xyz;
  float h = hash12(uv * 913.7);
  vec4 t = (uTime - uSwitch - h * uStagger) > 0.0 ? texture2D(tNext, uv) : texture2D(tPrev, uv);
  vec3 target = orbit(t);
  float k = uStiff * (0.65 + 0.7 * h);
  vec3 a = (target - p) * k - v * uDamp * sqrt(k);
  a += curl(p * uFlowScale + vec3(0.0, uTime * 0.07, h)) * uFlow * (0.6 + h);
  vec3 off = p - uRayO;
  vec3 side = off - uRayD * dot(off, uRayD);
  float d2 = dot(side, side);
  a += normalize(side + 1e-5) * uMouse * exp(-d2 / (uMouseR * uMouseR)) * 60.0;
  float age = uTime - uWaveT;
  if (age > 0.0 && age < 4.0) {
    vec3 w = p - uWaveC;
    float r = length(w);
    float band = (r - age * uWaveSpeed) / 1.2;
    a += normalize(w + 1e-5) * uWaveAmp * exp(-band * band) * exp(-age * 1.2) * 90.0;
  }
  v += a * uDt;
  float speed = length(v);
  if (speed > 40.0) v *= 40.0 / speed;
  gl_FragColor = vec4(v, 1.0);
}
`;

const position = /* glsl */ `
uniform float uDt;
void main() {
  vec2 uv = gl_FragCoord.xy / resolution.xy;
  vec4 p = texture2D(texturePosition, uv);
  vec3 v = texture2D(textureVelocity, uv).xyz;
  gl_FragColor = vec4(p.xyz + v * uDt, p.w);
}
`;

const vertex = /* glsl */ `
attribute vec2 ref;
attribute float index;
uniform sampler2D tPos, tPrev, tNext, tPrevC, tNextC;
uniform float uTime, uSwitch, uStagger, uDur, uScale, uFocus, uAperture, uHover, uSelect, uDim;
varying vec4 vColor;
${hash}
void main() {
  vec3 p = texture2D(tPos, ref).xyz;
  float h = hash12(ref * 913.7);
  float k = smoothstep(0.0, 1.0, clamp((uTime - uSwitch - h * uStagger) / uDur, 0.0, 1.0));
  float size = mix(abs(texture2D(tPrev, ref).w), abs(texture2D(tNext, ref).w), k);
  vec4 c = mix(texture2D(tPrevC, ref), texture2D(tNextC, ref), k);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  float depth = max(-mv.z, 0.1);
  float blur = clamp(abs(depth - uFocus) * uAperture, 0.0, 3.0);
  float lit = (index == uHover || index == uSelect) ? 1.0 : 0.0;
  float twinkle = 0.85 + 0.15 * sin(uTime * (1.5 + 3.0 * h) + h * 40.0);
  gl_PointSize = size * (1.0 + 1.6 * lit) * uScale * (1.0 + blur) / depth;
  vColor = vec4(c.rgb * (1.0 + 1.5 * lit), c.a * twinkle * uDim / (1.0 + blur * blur * 0.8));
  if (size <= 0.0 || c.a <= 0.0) gl_PointSize = 0.0;
  gl_Position = projectionMatrix * mv;
}
`;

const fragment = /* glsl */ `
varying vec4 vColor;
void main() {
  vec2 q = gl_PointCoord * 2.0 - 1.0;
  float d = dot(q, q);
  if (d > 1.0) discard;
  float glow = exp(-d * 7.0) + 0.22 * exp(-d * 2.2);
  gl_FragColor = vec4(vColor.rgb * glow * vColor.a, 1.0);
}
`;

export interface Wave {
  at: THREE.Vector3;
  amp?: number;
  speed?: number;
}

// The particles: positions and velocities live in float textures and step on the GPU each frame.
export class Sim {
  gpu: GPUComputationRenderer;
  pos: Variable;
  vel: Variable;
  points: THREE.Points;
  material: THREE.ShaderMaterial;
  current: Formation;
  private targets: THREE.DataTexture[];
  private colors: THREE.DataTexture[];
  private slot = 0;
  private uniforms: Record<string, THREE.IUniform>;

  constructor(renderer: THREE.WebGLRenderer) {
    this.gpu = new GPUComputationRenderer(SIDE, SIDE, renderer);
    if (!renderer.extensions.has("EXT_color_buffer_float")) this.gpu.setDataType(THREE.HalfFloatType);
    const start = this.gpu.createTexture();
    const data = start.image.data as Float32Array;
    for (let i = 0; i < N; i++) {
      const u = Math.random() * 2 - 1;
      const a = Math.random() * Math.PI * 2;
      const r = 26 + Math.random() * 30;
      const s = Math.sqrt(1 - u * u);
      data.set([r * s * Math.cos(a), r * u, r * s * Math.sin(a), Math.random()], i * 4);
    }
    const still = this.gpu.createTexture();
    this.pos = this.gpu.addVariable("texturePosition", position, start);
    this.vel = this.gpu.addVariable("textureVelocity", velocity, still);
    this.gpu.setVariableDependencies(this.pos, [this.pos, this.vel]);
    this.gpu.setVariableDependencies(this.vel, [this.pos, this.vel]);
    const blank = new Formation();
    this.current = blank;
    const texture = (array: Float32Array) => {
      const t = new THREE.DataTexture(array.slice(), SIDE, SIDE, THREE.RGBAFormat, THREE.FloatType);
      t.needsUpdate = true;
      return t;
    };
    this.targets = [texture(blank.pos), texture(blank.pos)];
    this.colors = [texture(blank.col), texture(blank.col)];
    this.uniforms = {
      uTime: { value: 0 },
      uDt: { value: 1 / 60 },
      uSwitch: { value: -100 },
      uStagger: { value: 1.2 },
      uStiff: { value: 9 },
      uDamp: { value: 1.25 },
      uFlow: { value: 0.6 },
      uFlowScale: { value: 0.12 },
      uSpin: { value: 0.04 },
      uRayO: { value: new THREE.Vector3() },
      uRayD: { value: new THREE.Vector3(0, 0, -1) },
      uMouse: { value: 0 },
      uMouseR: { value: 1.1 },
      uWaveC: { value: new THREE.Vector3() },
      uWaveT: { value: -100 },
      uWaveAmp: { value: 0 },
      uWaveSpeed: { value: 9 },
      tPrev: { value: this.targets[0] },
      tNext: { value: this.targets[1] },
    };
    Object.assign(this.vel.material.uniforms, this.uniforms);
    this.pos.material.uniforms.uDt = this.uniforms.uDt;
    const error = this.gpu.init();
    if (error) throw new Error(error);

    const geometry = new THREE.BufferGeometry();
    const ref = new Float32Array(N * 2);
    const index = new Float32Array(N);
    for (let i = 0; i < N; i++) {
      ref[i * 2] = ((i % SIDE) + 0.5) / SIDE;
      ref[i * 2 + 1] = (Math.floor(i / SIDE) + 0.5) / SIDE;
      index[i] = i;
    }
    geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(N * 3), 3));
    geometry.setAttribute("ref", new THREE.BufferAttribute(ref, 2));
    geometry.setAttribute("index", new THREE.BufferAttribute(index, 1));
    this.material = new THREE.ShaderMaterial({
      vertexShader: vertex,
      fragmentShader: fragment,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        tPos: { value: null },
        tPrev: this.uniforms.tPrev,
        tNext: this.uniforms.tNext,
        tPrevC: { value: this.colors[0] },
        tNextC: { value: this.colors[1] },
        uTime: this.uniforms.uTime,
        uSwitch: this.uniforms.uSwitch,
        uStagger: this.uniforms.uStagger,
        uDur: { value: 1.4 },
        uScale: { value: 300 },
        uFocus: { value: 24 },
        uAperture: { value: 0.035 },
        uHover: { value: -1 },
        uSelect: { value: -1 },
        uDim: { value: 1 },
      },
    });
    this.points = new THREE.Points(geometry, this.material);
    this.points.frustumCulled = false;
  }

  get u() {
    return this.uniforms;
  }

  get m() {
    return this.material.uniforms;
  }

  // Sends every particle to a new formation, each leaving after its own small delay.
  show(f: Formation, stagger = 1.1, duration = 1.4) {
    const next = 1 - this.slot;
    (this.targets[next].image.data as Float32Array).set(f.pos);
    (this.colors[next].image.data as Float32Array).set(f.col);
    this.targets[next].needsUpdate = true;
    this.colors[next].needsUpdate = true;
    this.uniforms.tPrev.value = this.targets[this.slot];
    this.uniforms.tNext.value = this.targets[next];
    this.m.tPrevC.value = this.colors[this.slot];
    this.m.tNextC.value = this.colors[next];
    this.slot = next;
    this.uniforms.uSwitch.value = this.uniforms.uTime.value;
    this.uniforms.uStagger.value = stagger;
    this.m.uDur.value = duration;
    this.current = f;
  }

  // Rewrites the formation in place, for small changes (a new month) without a staggered move.
  update(f: Formation) {
    const now = this.slot;
    (this.targets[now].image.data as Float32Array).set(f.pos);
    (this.colors[now].image.data as Float32Array).set(f.col);
    this.targets[now].needsUpdate = true;
    this.colors[now].needsUpdate = true;
    this.uniforms.uSwitch.value = this.uniforms.uTime.value - 100;
    this.uniforms.tPrev.value = this.targets[now];
    this.m.tPrevC.value = this.colors[now];
    this.current = f;
  }

  wave({ at, amp = 1, speed = 9 }: Wave) {
    this.uniforms.uWaveC.value.copy(at);
    this.uniforms.uWaveT.value = this.uniforms.uTime.value;
    this.uniforms.uWaveAmp.value = amp;
    this.uniforms.uWaveSpeed.value = speed;
  }

  step(time: number, dt: number) {
    this.uniforms.uTime.value = time;
    this.uniforms.uDt.value = dt;
    this.gpu.compute();
    this.m.tPos.value = this.gpu.getCurrentRenderTarget(this.pos).texture;
  }
}
