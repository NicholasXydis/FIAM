import gsap from "gsap";
import * as THREE from "three";
import { AfterimagePass } from "three/addons/postprocessing/AfterimagePass.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { hash, simplex } from "./glsl";

const BG = 0x040309;

// The last pass: a touch of lens fringing at the edges, a vignette and fine grain.
const grade = {
  uniforms: {
    tDiffuse: { value: null },
    uTime: { value: 0 },
    uGrain: { value: 0.014 },
    uVignette: { value: 0.85 },
    uShift: { value: 0.006 },
  },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
  `,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse;
    uniform float uTime, uGrain, uVignette, uShift;
    varying vec2 vUv;
    ${hash}
    void main() {
      vec2 c = vUv - 0.5;
      float edge = dot(c, c);
      vec2 o = c * edge * uShift;
      vec3 col = vec3(texture2D(tDiffuse, vUv + o).r, texture2D(tDiffuse, vUv).g, texture2D(tDiffuse, vUv - o).b);
      col *= mix(1.0, smoothstep(0.75, 0.05, edge * 1.6), uVignette);
      col += (hash12(vUv * 1000.0 + fract(uTime) * 100.0) - 0.5) * uGrain;
      gl_FragColor = vec4(max(col, 0.0), 1.0);
    }
  `,
};

const sky = /* glsl */ `
  uniform float uTime;
  varying vec3 vDir;
  ${simplex}
  void main() {
    vec3 d = normalize(vDir);
    float n = snoise(d * 1.6 + vec3(0.0, 0.0, uTime * 0.01)) * 0.55 + snoise(d * 3.4) * 0.3 + snoise(d * 7.0) * 0.15;
    float band = exp(-pow(d.y * 2.2 + 0.25 * snoise(d * 2.0), 2.0));
    vec3 deep = vec3(0.012, 0.009, 0.03);
    vec3 violet = vec3(0.09, 0.035, 0.2);
    vec3 teal = vec3(0.01, 0.05, 0.08);
    vec3 col = deep + violet * smoothstep(-0.1, 0.9, n) * (0.35 + 0.65 * band) + teal * smoothstep(0.2, 1.0, -n) * 0.6;
    gl_FragColor = vec4(col, 1.0);
  }
`;

// Stars twinkle as points, and while the camera travels each one also draws a streak toward the
// viewer, longer the faster the move.
const starVertex = /* glsl */ `
  attribute float seed;
  attribute float tail;
  uniform float uTime, uScale, uWarp;
  varying float vA;
  void main() {
    vec3 p = position * (1.0 - tail * uWarp * (0.08 + 0.12 * seed));
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    float twinkle = (0.45 + 0.55 * sin(uTime * (0.6 + seed * 2.0) + seed * 50.0)) * (0.35 + seed * 0.65);
    vA = tail < 0.5 ? twinkle : 0.0;
    gl_PointSize = tail < 0.5 ? uScale * (0.8 + seed * 1.6) : 0.0;
    gl_Position = projectionMatrix * mv;
  }
`;

const starFragment = /* glsl */ `
  varying float vA;
  void main() {
    vec2 q = gl_PointCoord * 2.0 - 1.0;
    float d = dot(q, q);
    if (d > 1.0) discard;
    gl_FragColor = vec4(vec3(0.75, 0.78, 1.0) * exp(-d * 5.0) * vA, 1.0);
  }
`;

const streakVertex = /* glsl */ `
  attribute float seed;
  attribute float tail;
  uniform float uWarp;
  varying float vA;
  void main() {
    vec3 p = position * (1.0 - tail * uWarp * (0.08 + 0.12 * seed));
    vA = (1.0 - tail) * uWarp * (0.3 + 0.7 * seed);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }
`;

const streakFragment = /* glsl */ `
  varying float vA;
  void main() { gl_FragColor = vec4(vec3(0.7, 0.75, 1.0) * vA, 1.0); }
`;

// A spring that pulls a value toward its target: x'' = -k (x - target) - c x'.
export class Spring {
  value = new THREE.Vector3();
  target = new THREE.Vector3();
  speed = new THREE.Vector3();
  private a = new THREE.Vector3();

  constructor(
    public stiffness = 9,
    public damping = 6,
  ) {}

  step(dt: number) {
    this.a.copy(this.target).sub(this.value).multiplyScalar(this.stiffness).addScaledVector(this.speed, -this.damping);
    this.speed.addScaledVector(this.a, dt);
    this.value.addScaledVector(this.speed, dt);
  }

  snap() {
    this.value.copy(this.target);
    this.speed.set(0, 0, 0);
  }
}

export interface Shot {
  eye: [number, number, number];
  look: [number, number, number];
  fov?: number;
  drift?: number;
  shift?: number;
}

function starfield(count: number) {
  const position = new Float32Array(count * 6);
  const seed = new Float32Array(count * 2);
  const tail = new Float32Array(count * 2);
  for (let i = 0; i < count; i++) {
    const u = Math.random() * 2 - 1;
    const a = Math.random() * Math.PI * 2;
    const r = 90 + Math.random() * 90;
    const s = Math.sqrt(1 - u * u);
    const p = [r * s * Math.cos(a), r * u, r * s * Math.sin(a)];
    position.set([...p, ...p], i * 6);
    seed[i * 2] = seed[i * 2 + 1] = Math.random();
    tail.set([0, 1], i * 2);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(position, 3));
  g.setAttribute("seed", new THREE.BufferAttribute(seed, 1));
  g.setAttribute("tail", new THREE.BufferAttribute(tail, 1));
  return g;
}

export class Stage {
  renderer: THREE.WebGLRenderer;
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(42, 1, 0.1, 400);
  composer: EffectComposer;
  bloom: UnrealBloomPass;
  trails: AfterimagePass;
  grade: ShaderPass;
  eye = new Spring(5, 4.6);
  look = new Spring(6, 5.2);
  drift = 1;
  quality = 2;
  reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  private pointer = new THREE.Vector2();
  private parallax = new THREE.Vector2();
  private wobble = new THREE.Vector3();
  private sky: THREE.Mesh<THREE.SphereGeometry, THREE.ShaderMaterial>;
  private stars: THREE.Group;
  private starUniforms = { uTime: { value: 0 }, uScale: { value: 2 }, uWarp: { value: 0 } };
  private fov = 42;
  private shift = 0;
  private lens = 0;

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" });
    this.renderer.setClearColor(BG, 1);
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.scene.background = new THREE.Color(BG);

    this.sky = new THREE.Mesh(
      new THREE.SphereGeometry(200, 48, 24),
      new THREE.ShaderMaterial({
        side: THREE.BackSide,
        depthWrite: false,
        uniforms: { uTime: { value: 0 } },
        vertexShader:
          "varying vec3 vDir; void main(){ vDir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
        fragmentShader: sky,
      }),
    );
    this.scene.add(this.sky);

    const field = starfield(2600);
    const glow = {
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: this.starUniforms,
    };
    const points = new THREE.Points(
      field,
      new THREE.ShaderMaterial({ ...glow, vertexShader: starVertex, fragmentShader: starFragment }),
    );
    const streaks = new THREE.LineSegments(
      field,
      new THREE.ShaderMaterial({ ...glow, vertexShader: streakVertex, fragmentShader: streakFragment }),
    );
    points.frustumCulled = streaks.frustumCulled = false;
    this.stars = new THREE.Group().add(points, streaks);
    this.scene.add(this.stars);

    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.trails = new AfterimagePass(0);
    this.composer.addPass(this.trails);
    this.bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.95, 0.55, 0.12);
    this.composer.addPass(this.bloom);
    this.grade = new ShaderPass(grade);
    this.composer.addPass(this.grade);
    this.composer.addPass(new OutputPass());

    this.eye.target.set(0, 0, 30);
    this.eye.snap();
    this.look.snap();
    addEventListener("resize", () => this.resize());
    addEventListener("pointermove", (e) => {
      this.pointer.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
    });
    this.resize();
  }

  get ratio() {
    return Math.min(devicePixelRatio, this.quality >= 2 ? 2 : this.quality === 1 ? 1.5 : 1);
  }

  // The particles' size scale in pixels for a world size of 1 at depth 1.
  get pixel() {
    return innerHeight * this.ratio * 0.2;
  }

  resize() {
    const w = innerWidth;
    const h = innerHeight;
    this.renderer.setPixelRatio(this.ratio);
    this.renderer.setSize(w, h, false);
    this.composer.setPixelRatio(this.ratio);
    this.composer.setSize(w, h);
    this.bloom.resolution.set(w * this.ratio * 0.5, h * this.ratio * 0.5);
    this.camera.aspect = w / h;
    this.camera.setViewOffset(w, h, -w * this.lens, 0, w, h);
    this.camera.updateProjectionMatrix();
    this.starUniforms.uScale.value = 1.6 * this.ratio;
  }

  frame(shot: Shot, snap = false) {
    const travel = this.eye.value.distanceTo(new THREE.Vector3(...shot.eye));
    this.eye.target.set(...shot.eye);
    this.look.target.set(...shot.look);
    this.drift = shot.drift ?? 1;
    this.fov = shot.fov ?? 42;
    this.shift = shot.shift ?? 0.15;
    if (snap) {
      this.eye.snap();
      this.look.snap();
    } else if (!this.reduced) this.warp(Math.min(1, 0.35 + travel / 14));
  }

  // Stretches the stars into streaks and smears the frame for a moment, as the camera jumps.
  warp(strength = 1) {
    gsap.killTweensOf(this.starUniforms.uWarp);
    gsap
      .timeline()
      .to(this.starUniforms.uWarp, { value: strength, duration: 0.35, ease: "power2.in" })
      .to(this.starUniforms.uWarp, { value: 0, duration: 1.3, ease: "power3.out" });
    if (this.trails.enabled)
      gsap.fromTo(
        this.trails.uniforms.damp,
        { value: 0.82 * strength },
        { value: 0, duration: 1.6, ease: "power2.out" },
      );
  }

  setQuality(level: number) {
    this.quality = level;
    this.trails.enabled = level >= 2 && !this.reduced;
    this.bloom.enabled = level >= 1;
    this.grade.uniforms.uGrain.value = level >= 1 ? 0.014 : 0;
    this.resize();
  }

  update(time: number, dt: number, free: boolean) {
    const d = this.drift * (this.reduced ? 0.25 : 1);
    this.parallax.lerp(this.pointer, 1 - Math.exp(-dt * 2));
    if (!free) {
      this.eye.step(dt);
      this.look.step(dt);
      this.wobble.set(
        Math.sin(time * 0.11) * 0.9 * d + this.parallax.x * 1.1 * d,
        Math.sin(time * 0.083) * 0.45 * d + this.parallax.y * 0.7 * d,
        Math.cos(time * 0.07) * 0.6 * d,
      );
      const aspect = innerWidth / innerHeight;
      const back = aspect < 1 ? Math.min(2.8, Math.max(1, 1.25 / aspect)) : 1;
      this.camera.position
        .copy(this.eye.value)
        .sub(this.look.value)
        .multiplyScalar(back)
        .add(this.look.value)
        .add(this.wobble);
      this.camera.lookAt(this.look.value);
      const lens = innerWidth > 760 ? this.shift : 0;
      if (Math.abs(this.camera.fov - this.fov) > 0.01 || Math.abs(this.lens - lens) > 1e-4) {
        this.camera.fov += (this.fov - this.camera.fov) * (1 - Math.exp(-dt * 3));
        this.lens += (lens - this.lens) * (1 - Math.exp(-dt * 2.5));
        this.camera.setViewOffset(innerWidth, innerHeight, -innerWidth * this.lens, 0, innerWidth, innerHeight);
        this.camera.updateProjectionMatrix();
      }
    }
    this.sky.position.copy(this.camera.position);
    this.stars.position.copy(this.camera.position).multiplyScalar(0.92);
    this.sky.material.uniforms.uTime.value = time;
    this.starUniforms.uTime.value = time;
    this.grade.uniforms.uTime.value = time;
  }

  render() {
    this.composer.render();
  }
}
