import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { FullScreenQuad } from "three/addons/postprocessing/Pass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { TexturePass } from "three/addons/postprocessing/TexturePass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { hash } from "../gl/glsl";

const quad = /* glsl */ `
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
`;

// Before the bloom: the gold level line, drawn out from the centre, and the slit it opens into.
const line = {
  uniforms: {
    tDiffuse: { value: null },
    uRes: { value: new THREE.Vector2(1, 1) },
    uY: { value: 0.5 },
    uDraw: { value: 0 },
    uSlit: { value: 0 },
    uGlow: { value: 1 },
    uGold: { value: new THREE.Color(0xf2c14e).multiplyScalar(1.5) },
  },
  vertexShader: quad,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse;
    uniform vec2 uRes;
    uniform float uY, uDraw, uSlit, uGlow;
    uniform vec3 uGold;
    varying vec2 vUv;
    void main() {
      vec3 col = texture2D(tDiffuse, vUv).rgb;
      float px = uRes.y / 1080.0;
      float dy = abs(vUv.y - uY) * uRes.y;
      float dx = abs(vUv.x - 0.5) * uRes.x;
      float open = uSlit * uRes.y * 0.62;
      col *= 1.0 - smoothstep(open - px, open + px, dy);
      float reach = uDraw * uRes.x * 0.52;
      float along = 1.0 - smoothstep(reach - 40.0 * px, reach, dx);
      float edge = dy - open;
      float core = exp(-edge * edge / (1.2 * px * px)) + 0.18 * exp(-edge * edge / (30.0 * px * px));
      float tip = exp(-pow((dx - reach) / (10.0 * px), 2.0)) * exp(-dy * dy / (9.0 * px * px)) * step(uDraw, 0.999);
      col += uGold * (core * along + tip * 2.5) * uGlow;
      gl_FragColor = vec4(col, 1.0);
    }
  `,
};

// After the bloom: a soft vignette, a fade to black, faint lens fringing and optional grain.
const grade = {
  uniforms: {
    tDiffuse: { value: null },
    uTime: { value: 0 },
    uGrain: { value: 0 },
    uVignette: { value: 0.4 },
    uFade: { value: 0 },
    uDim: { value: 0 },
    uLift: { value: new THREE.Color(0, 0, 0) },
  },
  vertexShader: quad,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse;
    uniform float uTime, uGrain, uVignette, uFade, uDim;
    uniform vec3 uLift;
    varying vec2 vUv;
    ${hash}
    void main() {
      vec2 c = vUv - 0.5;
      float edge = dot(c, c);
      vec2 o = c * edge * 0.004;
      vec3 col = vec3(texture2D(tDiffuse, vUv + o).r, texture2D(tDiffuse, vUv).g, texture2D(tDiffuse, vUv - o).b);
      col *= mix(1.0, smoothstep(0.9, 0.1, edge * 1.5), uVignette);
      col = col * (1.0 - uDim) + uLift;
      col += (hash12(vUv * 1000.0 + fract(uTime) * 100.0) - 0.5) * uGrain;
      gl_FragColor = vec4(max(col * (1.0 - uFade), 0.0), 1.0);
    }
  `,
};

// The renderer and its passes. Each frame can be drawn as several subframes, averaged before the
// bloom, which gives true motion blur, smooth edges and soft shadows when recording.
export class Look {
  renderer: THREE.WebGLRenderer;
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(30, 16 / 9, 0.1, 400);
  composer: EffectComposer;
  bloom: UnrealBloomPass;
  line: ShaderPass;
  grade: ShaderPass;
  studio: THREE.Texture;
  night: THREE.Texture;
  private target: THREE.WebGLRenderTarget;
  private accum: THREE.WebGLRenderTarget;
  private copy: TexturePass;
  private add: FullScreenQuad;

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" });
    this.renderer.toneMapping = THREE.NeutralToneMapping;
    this.renderer.toneMappingExposure = 1;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.VSMShadowMap;
    this.target = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: 4 });
    this.accum = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, depthBuffer: false });
    this.add = new FullScreenQuad(
      new THREE.ShaderMaterial({
        uniforms: { tDiffuse: { value: null }, uWeight: { value: 1 } },
        vertexShader: quad,
        fragmentShader: /* glsl */ `
          uniform sampler2D tDiffuse;
          uniform float uWeight;
          varying vec2 vUv;
          void main() { gl_FragColor = vec4(texture2D(tDiffuse, vUv).rgb * uWeight, 1.0); }
        `,
        blending: THREE.AdditiveBlending,
        depthTest: false,
        depthWrite: false,
        transparent: true,
      }),
    );
    this.composer = new EffectComposer(this.renderer);
    this.copy = new TexturePass(this.target.texture);
    this.composer.addPass(this.copy);
    this.line = new ShaderPass(line);
    this.composer.addPass(this.line);
    this.bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.3, 0.6, 0.9);
    this.composer.addPass(this.bloom);
    this.grade = new ShaderPass(grade);
    this.composer.addPass(this.grade);
    this.composer.addPass(new OutputPass());

    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.studio = pmrem.fromScene(studio(), 0.03).texture;
    this.night = pmrem.fromScene(night(), 0.04).texture;
    pmrem.dispose();
  }

  get size() {
    return this.renderer.getDrawingBufferSize(new THREE.Vector2());
  }

  resize(w: number, h: number, ratio: number) {
    this.renderer.setPixelRatio(ratio);
    this.renderer.setSize(w, h, false);
    const W = Math.round(w * ratio);
    const H = Math.round(h * ratio);
    this.target.setSize(W, H);
    this.accum.setSize(W, H);
    this.composer.setPixelRatio(ratio);
    this.composer.setSize(w, h);
    this.line.uniforms.uRes.value.set(W, H);
  }

  // Draws n subframes, each set up by sub(k) first, and shows their average.
  render(n: number, sub: (k: number) => void) {
    const r = this.renderer;
    for (let k = 0; k < n; k++) {
      sub(k);
      r.setRenderTarget(this.target);
      r.render(this.scene, this.camera);
      if (n === 1) break;
      r.setRenderTarget(this.accum);
      if (k === 0) {
        r.setClearColor(0, 0);
        r.clear();
      }
      const m = this.add.material as THREE.ShaderMaterial;
      m.uniforms.tDiffuse.value = this.target.texture;
      m.uniforms.uWeight.value = 1 / n;
      r.autoClear = false;
      this.add.render(r);
      r.autoClear = true;
    }
    this.copy.map = n === 1 ? this.target.texture : this.accum.texture;
    r.setRenderTarget(null);
    this.composer.render();
  }
}

function room(color: number, panels: [number, number, [number, number, number], [number, number]][]) {
  const scene = new THREE.Scene();
  scene.add(
    new THREE.Mesh(new THREE.SphereGeometry(20, 32, 16), new THREE.MeshBasicMaterial({ color, side: THREE.BackSide })),
  );
  for (const [tint, power, at, size] of panels) {
    const m = new THREE.Mesh(
      new THREE.PlaneGeometry(...size),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(tint).multiplyScalar(power), side: THREE.DoubleSide }),
    );
    m.position.set(...at);
    m.lookAt(0, 0, 0);
    scene.add(m);
  }
  return scene;
}

// What chrome reflects in the bright room: soft boxes above and to the side, a white floor, and
// black cards that give polished metal its dark edges, as a product photographer would set it.
const studio = () =>
  room(0x4f4c58, [
    [0xffffff, 5, [0, 12, 3], [14, 8]],
    [0xffffff, 3.5, [-13, 3, 5], [5, 10]],
    [0xfff4e6, 5, [12, 2, -3], [2.2, 12]],
    [0xe9e6ef, 1.1, [0, -9, 0], [30, 30]],
    [0x060509, 1, [7, 1, 11], [7, 14]],
    [0x060509, 1, [-9, 0, -10], [9, 12]],
    [0x060509, 1, [0, 1, -15], [6, 3]],
  ]);

// What chrome reflects at night: a dark violet room with a long low gold glow, like a horizon.
const night = () =>
  room(0x07050f, [
    [0xf2c14e, 3, [0, 0.5, -16], [40, 1.2]],
    [0xa98bff, 1.4, [0, 14, 0], [16, 16]],
    [0xffffff, 1.2, [-12, 4, 8], [3, 8]],
    [0x5cc8e0, 0.8, [12, 2, 6], [3, 6]],
  ]);
