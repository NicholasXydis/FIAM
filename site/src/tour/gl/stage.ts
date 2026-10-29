import gsap from "gsap";
import * as THREE from "three";
import { AfterimagePass } from "three/addons/postprocessing/AfterimagePass.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { hash, simplex } from "../../shared/glsl";

// The near-black violet behind everything.
const BG = 0x040309;

// The last pass: slight lens fringing at the edges, a vignette, grain.
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

// The sky: drifting noise, violet toward the horizon, teal in the dips.
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

// Twinkling stars that streak toward the viewer as the camera travels.
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

// A soft round star in pale blue.
const starFragment = /* glsl */ `
  varying float vA;
  void main() {
    vec2 q = gl_PointCoord * 2.0 - 1.0;
    float d = dot(q, q);
    if (d > 1.0) discard;
    gl_FragColor = vec4(vec3(0.75, 0.78, 1.0) * exp(-d * 5.0) * vA, 1.0);
  }
`;

// Streaks: a line from each star toward the camera, bright at the star.
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

// The streak's pale blue, faded along its length.
const streakFragment = /* glsl */ `
  varying float vA;
  void main() { gl_FragColor = vec4(vec3(0.7, 0.75, 1.0) * vA, 1.0); }
`;

// A spring toward a target: x'' = -k (x - target) - c x'.
class Spring {
  value = new THREE.Vector3();
  target = new THREE.Vector3();
  speed = new THREE.Vector3();
  private a = new THREE.Vector3();

  // Stiffness k and damping c, 9 and 6 unless the caller sets them.
  constructor(
    public stiffness = 9,
    public damping = 6,
  ) {}

  // One semi-implicit Euler step: speed first, then the value.
  step(dt: number) {
    this.a.copy(this.target).sub(this.value).multiplyScalar(this.stiffness).addScaledVector(this.speed, -this.damping);
    this.speed.addScaledVector(this.a, dt);
    this.value.addScaledVector(this.speed, dt);
  }

  // Jumps straight to the target at rest, for a cut.
  snap() {
    this.value.copy(this.target);
    this.speed.set(0, 0, 0);
  }
}

// A shot: eye, look point, fov (42), drift (1) and lens shift (0.15).
export interface Shot {
  eye: [number, number, number];
  look: [number, number, number];
  fov?: number;
  drift?: number;
  shift?: number;
}

// Random stars 90 to 180 out, each a head and tail pair with one seed.
function starfield(count: number) {
  const position = new Float32Array(count * 6);
  const seed = new Float32Array(count * 2);
  const tail = new Float32Array(count * 2);
  // A random point on a shell; head and tail start at the same spot.
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

// The renderer, camera, stars and passes every scene draws through.
export class Stage {
  renderer: THREE.WebGLRenderer;
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(42, 1, 0.1, 400);
  composer: EffectComposer;
  bloom: UnrealBloomPass;
  trails: AfterimagePass;
  grade: ShaderPass;
  // Camera springs, stiffness then damping; the look is a little stiffer.
  eye = new Spring(5, 4.6);
  look = new Spring(6, 5.2);
  drift = 1;
  quality = 2;
  reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  pointer = new THREE.Vector2();
  private parallax = new THREE.Vector2();
  private wobble = new THREE.Vector3();
  private sky: THREE.Mesh<THREE.SphereGeometry, THREE.ShaderMaterial>;
  private stars: THREE.Group;
  private starUniforms = { uTime: { value: 0 }, uScale: { value: 2 }, uWarp: { value: 0 } };
  // The shot's fov and shift, the lens eased so far, the last size fit.
  private fov = 42;
  private shift = 0;
  private lens = 0;
  private size = "";
  // On small screens, the zoom and offset that fit the scene to its band.
  view: { zoom: number; ox: number; oy: number } | null = null;
  private shown = { zoom: 1, ox: 0, oy: 0 };
  private rest = new THREE.PerspectiveCamera(42, 1, 0.1, 400);

  // Builds the renderer, sky, stars and passes, then fits the window.
  constructor(canvas: HTMLCanvasElement) {
    // No antialias; ACES filmic tone mapping at 1.05 exposure.
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" });
    this.renderer.setClearColor(BG, 1);
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.scene.background = new THREE.Color(BG);

    // A 200 unit sky sphere, seen from inside.
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

    // 2600 stars drawn twice from one geometry, as points and as streaks.
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

    // Passes: scene, trails, bloom (strength 0.95), grade, then output.
    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.trails = new AfterimagePass(0);
    this.composer.addPass(this.trails);
    this.bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.95, 0.55, 0.12);
    this.composer.addPass(this.bloom);
    this.grade = new ShaderPass(grade);
    this.composer.addPass(this.grade);
    this.composer.addPass(new OutputPass());

    // The camera starts at rest 30 out on z, then fits the window.
    this.eye.target.set(0, 0, 30);
    this.eye.snap();
    this.look.snap();
    addEventListener("resize", () => this.resize());
    this.resize();
  }

  // Pixel ratio by quality: up to 2, 1.5 or 1, never above the screen's.
  get ratio() {
    return Math.min(devicePixelRatio, this.quality >= 2 ? 2 : this.quality === 1 ? 1.5 : 1);
  }

  // The particles' size scale in pixels for a world size of 1 at depth 1.
  get pixel() {
    return innerHeight * this.ratio * 0.2 * this.camera.zoom;
  }

  // The camera where its springs are headed, to fit a shot to a band.
  restCamera() {
    const aspect = innerWidth / innerHeight;
    const back = aspect < 1 ? Math.min(2.8, Math.max(1, 1.25 / aspect)) : 1;
    const c = this.rest;
    c.position.copy(this.eye.target).sub(this.look.target).multiplyScalar(back).add(this.look.target);
    c.lookAt(this.look.target);
    Object.assign(c, { fov: this.fov, aspect, zoom: 1 });
    c.clearViewOffset();
    c.updateProjectionMatrix();
    c.updateMatrixWorld(true);
    return c;
  }

  // Fits the canvas and passes to the window, skipping an unchanged size.
  resize() {
    const w = innerWidth;
    const h = innerHeight;
    const size = `${w}x${h}@${this.ratio}`;
    if (size === this.size) return;
    this.size = size;
    this.renderer.setPixelRatio(this.ratio);
    this.renderer.setSize(w, h, false);
    this.composer.setPixelRatio(this.ratio);
    this.composer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.setViewOffset(w, h, -w * this.lens, 0, w, h);
    this.camera.updateProjectionMatrix();
    this.starUniforms.uScale.value = 1.6 * this.ratio;
  }

  // Flies to a shot, the warp growing with distance, or cuts with snap.
  frame(shot: Shot, snap = false) {
    const travel = this.eye.value.distanceTo(new THREE.Vector3(...shot.eye));
    this.eye.target.set(...shot.eye);
    this.look.target.set(...shot.look);
    this.drift = shot.drift ?? 1;
    this.fov = shot.fov ?? 42;
    this.shift = shot.shift ?? 0.15;
    // A cut snaps at once; a move warps unless motion is reduced.
    if (snap) {
      this.eye.snap();
      this.look.snap();
    } else if (!this.reduced) this.warp(Math.min(1, 0.35 + travel / 14));
  }

  // Streaks stars and smears the frame about 1.6 s as the camera jumps.
  warp(strength = 1) {
    gsap.killTweensOf(this.starUniforms.uWarp);
    gsap
      .timeline()
      .to(this.starUniforms.uWarp, { value: strength, duration: 0.35, ease: "power2.in" })
      .to(this.starUniforms.uWarp, { value: 0, duration: 1.3, ease: "power3.out" });
    // The frame smears too, while trails are on.
    if (this.trails.enabled)
      gsap.fromTo(
        this.trails.uniforms.damp,
        { value: 0.82 * strength },
        { value: 0, duration: 1.6, ease: "power2.out" },
      );
  }

  // Trails at level 2 unless motion is reduced, bloom and grain from 1.
  setQuality(level: number) {
    this.quality = level;
    this.trails.enabled = level >= 2 && !this.reduced;
    this.bloom.enabled = level >= 1;
    this.grade.uniforms.uGrain.value = level >= 1 ? 0.014 : 0;
    this.resize();
  }

  // Moves the camera along its springs with drift and parallax.
  update(time: number, dt: number, hold = false) {
    // Drift is quartered for reduced motion; parallax eases to the pointer.
    const d = this.drift * (this.reduced ? 0.25 : 1);
    // Held for a hover, the camera stops following the pointer.
    if (!hold) this.parallax.lerp(this.pointer, 1 - Math.exp(-dt * 2));
    this.eye.step(dt);
    this.look.step(dt);
    this.wobble.set(
      Math.sin(time * 0.11) * 0.9 * d + this.parallax.x * 1.1 * d,
      Math.sin(time * 0.083) * 0.45 * d + this.parallax.y * 0.7 * d,
      Math.cos(time * 0.07) * 0.6 * d,
    );
    // Portrait screens pull the camera back, up to 2.8 times, to fit.
    const aspect = innerWidth / innerHeight;
    const back = aspect < 1 ? Math.min(2.8, Math.max(1, 1.25 / aspect)) : 1;
    this.camera.position
      .copy(this.eye.value)
      .sub(this.look.value)
      .multiplyScalar(back)
      .add(this.look.value)
      .add(this.wobble);
    this.camera.lookAt(this.look.value);
    // The lens shift, off at 760 px or less or in a band, eases in.
    const lens = innerWidth > 760 && !this.view ? this.shift : 0;
    // Ease the fov and lens toward the shot's while they differ.
    if (Math.abs(this.camera.fov - this.fov) > 0.01 || Math.abs(this.lens - lens) > 1e-4) {
      this.camera.fov += (this.fov - this.camera.fov) * (1 - Math.exp(-dt * 3));
      this.lens += (lens - this.lens) * (1 - Math.exp(-dt * 2.5));
      this.camera.setViewOffset(innerWidth, innerHeight, -innerWidth * this.lens, 0, innerWidth, innerHeight);
      this.camera.updateProjectionMatrix();
    }
    this.fitView(dt);
    // Sky and stars travel with the camera, the stars at 0.92 of its move.
    this.sky.position.copy(this.camera.position);
    this.stars.position.copy(this.camera.position).multiplyScalar(0.92);
    this.sky.material.uniforms.uTime.value = time;
    this.starUniforms.uTime.value = time;
    this.grade.uniforms.uTime.value = time;
  }

  // Eases the camera to the band's zoom and offset, or back to none.
  private fitView(dt: number) {
    const to = this.view ?? { zoom: 1, ox: 0, oy: 0 };
    const s = this.shown;
    if (!this.view && this.camera.zoom === 1 && s.ox === 0 && s.oy === 0) return;
    const k = 1 - Math.exp(-dt * 3);
    const near = Math.abs(to.zoom - s.zoom) < 1e-3 && Math.abs(to.ox - s.ox) < 0.5 && Math.abs(to.oy - s.oy) < 0.5;
    // Snap once close enough, else ease a step closer.
    if (near) Object.assign(s, to);
    else
      Object.assign(s, {
        zoom: s.zoom + (to.zoom - s.zoom) * k,
        ox: s.ox + (to.ox - s.ox) * k,
        oy: s.oy + (to.oy - s.oy) * k,
      });
    this.camera.zoom = s.zoom;
    this.camera.setViewOffset(innerWidth, innerHeight, s.ox - innerWidth * this.lens, s.oy, innerWidth, innerHeight);
    this.camera.updateProjectionMatrix();
  }

  // Draws the frame through every pass.
  render() {
    this.composer.render();
  }
}
