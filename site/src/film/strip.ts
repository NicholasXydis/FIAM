import * as THREE from "three";

const vertex = /* glsl */ `
  attribute vec3 prev;
  attribute vec3 next;
  attribute float side;
  attribute vec2 info;
  uniform vec2 uViewport;
  uniform float uWidth;
  varying float vSide;
  varying float vAlpha;
  vec2 screen(vec4 c) { return c.xy / c.w * 0.5 * uViewport; }
  void main() {
    mat4 m = projectionMatrix * modelViewMatrix;
    vec4 c = m * vec4(position, 1.0);
    vec2 d = screen(m * vec4(next, 1.0)) - screen(m * vec4(prev, 1.0));
    d = length(d) > 1e-4 ? normalize(d) : vec2(1.0, 0.0);
    float w = uWidth * info.y * uViewport.y / 1080.0;
    c.xy += vec2(-d.y, d.x) * side * w / (0.5 * uViewport) * c.w;
    gl_Position = c;
    vSide = side;
    vAlpha = info.x;
  }
`;

const fragment = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  varying float vSide;
  varying float vAlpha;
  void main() {
    float across = max(1.0 - vSide * vSide, 0.0);
    gl_FragColor = vec4(uColor * vAlpha * uOpacity * pow(across, 1.5), 1.0);
  }
`;

// A ribbon of light through a list of points, always facing the camera, its width in pixels at
// 1080p. Each point carries its own brightness and width, so trails can fade and taper.
export class Strip {
  mesh: THREE.Mesh<THREE.BufferGeometry, THREE.ShaderMaterial>;
  private pos: Float32Array;
  private prev: Float32Array;
  private next: Float32Array;
  private info: Float32Array;

  constructor(
    private max: number,
    color: THREE.ColorRepresentation,
    width = 2,
    power = 1,
  ) {
    const g = new THREE.BufferGeometry();
    this.pos = new Float32Array(max * 6);
    this.prev = new Float32Array(max * 6);
    this.next = new Float32Array(max * 6);
    this.info = new Float32Array(max * 4);
    const side = new Float32Array(max * 2);
    for (let i = 0; i < max; i++) side.set([-1, 1], i * 2);
    const index: number[] = [];
    for (let i = 0; i < max - 1; i++) {
      const a = i * 2;
      index.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
    g.setIndex(index);
    g.setAttribute("position", new THREE.BufferAttribute(this.pos, 3));
    g.setAttribute("prev", new THREE.BufferAttribute(this.prev, 3));
    g.setAttribute("next", new THREE.BufferAttribute(this.next, 3));
    g.setAttribute("info", new THREE.BufferAttribute(this.info, 2));
    g.setAttribute("side", new THREE.BufferAttribute(side, 1));
    this.mesh = new THREE.Mesh(
      g,
      new THREE.ShaderMaterial({
        vertexShader: vertex,
        fragmentShader: fragment,
        uniforms: {
          uViewport: { value: new THREE.Vector2(1920, 1080) },
          uWidth: { value: width },
          uColor: { value: new THREE.Color(color).multiplyScalar(power) },
          uOpacity: { value: 1 },
        },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
      }),
    );
    this.mesh.frustumCulled = false;
  }

  // Lays the ribbon through the points; alpha and width are given per point, from 0 to 1.
  set(points: THREE.Vector3[], alpha: (i: number) => number = () => 1, width: (i: number) => number = () => 1) {
    const n = Math.min(points.length, this.max);
    for (let i = 0; i < n; i++) {
      const p = points[i];
      const a = points[Math.max(0, i - 1)];
      const b = points[Math.min(n - 1, i + 1)];
      for (let s = 0; s < 2; s++) {
        const o = (i * 2 + s) * 3;
        this.pos.set([p.x, p.y, p.z], o);
        this.prev.set([a.x, a.y, a.z], o);
        this.next.set([b.x, b.y, b.z], o);
        this.info.set([alpha(i), width(i)], (i * 2 + s) * 2);
      }
    }
    const g = this.mesh.geometry;
    for (const k of ["position", "prev", "next", "info"]) g.attributes[k].needsUpdate = true;
    g.setDrawRange(0, Math.max(0, n - 1) * 6);
  }

  viewport(size: THREE.Vector2) {
    this.mesh.material.uniforms.uViewport.value.copy(size);
  }
}
