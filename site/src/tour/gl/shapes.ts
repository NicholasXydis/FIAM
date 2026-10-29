import * as THREE from "three";

// A glowing tube through points, drawn on start to end by uProgress.
export function tube(points: THREE.Vector3[], color: number, radius = 0.05, opacity = 1, dashed = false) {
  const curve = new THREE.CatmullRomCurve3(points, false, "centripetal");
  const geometry = new THREE.TubeGeometry(curve, Math.max(64, points.length * 6), radius, 10, false);
  const material = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uColor: { value: new THREE.Color(color) },
      uProgress: { value: 1 },
      uOpacity: { value: opacity },
      uDash: { value: dashed ? 1 : 0 },
    },
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      varying vec3 vN;
      varying vec3 vView;
      void main() {
        vUv = uv;
        vN = normalize(normalMatrix * normal);
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vView = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform vec3 uColor;
      uniform float uProgress, uOpacity, uDash;
      varying vec2 vUv;
      varying vec3 vN;
      varying vec3 vView;
      void main() {
        if (vUv.x > uProgress) discard;
        if (uDash > 0.5 && fract(vUv.x * 90.0) > 0.55) discard;
        float rim = pow(1.0 - abs(dot(vN, vView)), 1.6);
        float head = smoothstep(uProgress - 0.015, uProgress, vUv.x) * step(uProgress, 0.999);
        vec3 col = uColor * (0.75 + 1.4 * rim) + vec3(1.0) * head * 2.0;
        gl_FragColor = vec4(col * uOpacity, 1.0);
      }
    `,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.userData.curve = curve;
  return mesh;
}

// A soft glowing disc facing the camera, for markers and halos.
export function glow(color: number, size: number, opacity = 1) {
  const material = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: { uColor: { value: new THREE.Color(color) }, uOpacity: { value: opacity } },
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        vec4 mv = modelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0);
        mv.xy += position.xy;
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform vec3 uColor;
      uniform float uOpacity;
      varying vec2 vUv;
      void main() {
        float d = length(vUv - 0.5) * 2.0;
        float a = (exp(-d * d * 6.0) + 0.25 * exp(-d * d * 1.5)) * smoothstep(1.0, 0.6, d);
        gl_FragColor = vec4(uColor * a * uOpacity, 1.0);
      }
    `,
  });
  return new THREE.Mesh(new THREE.PlaneGeometry(size, size), material);
}

// Particles streaming forever on quadratic curves, a to b bent via c.
export function streams(
  paths: { a: THREE.Vector3; b: THREE.Vector3; c: THREE.Vector3; color: number; count: number }[],
  size = 0.18,
) {
  // One point per particle, with its path, colour, phase and lane.
  const total = paths.reduce((n, p) => n + p.count, 0);
  const a = new Float32Array(total * 3);
  const b = new Float32Array(total * 3);
  const c = new Float32Array(total * 3);
  const col = new Float32Array(total * 3);
  const phase = new Float32Array(total);
  const lane = new Float32Array(total);
  const tint = new THREE.Color();
  let k = 0;
  // Fill in each path's particles with its ends, colour and lane.
  paths.forEach((p, i) => {
    tint.setHex(p.color);
    // Each particle gets the path's points and a random phase.
    for (let j = 0; j < p.count; j++, k++) {
      a.set(p.a.toArray(), k * 3);
      b.set(p.b.toArray(), k * 3);
      c.set(p.c.toArray(), k * 3);
      col.set([tint.r, tint.g, tint.b], k * 3);
      phase[k] = Math.random();
      lane[k] = i;
    }
  });
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(a, 3));
  g.setAttribute("b", new THREE.BufferAttribute(b, 3));
  g.setAttribute("c", new THREE.BufferAttribute(c, 3));
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  g.setAttribute("phase", new THREE.BufferAttribute(phase, 1));
  g.setAttribute("lane", new THREE.BufferAttribute(lane, 1));
  // uFocus lights one lane and dims the rest; -1 lights them all alike.
  const material = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uTime: { value: 0 },
      uOpacity: { value: 1 },
      uScale: { value: 300 },
      uSize: { value: size },
      uFocus: { value: -1 },
      uSpeed: { value: 0.22 },
    },
    vertexShader: /* glsl */ `
      attribute vec3 b, c, color;
      attribute float phase, lane;
      uniform float uTime, uScale, uSize, uFocus, uSpeed;
      varying vec3 vColor;
      varying float vA;
      void main() {
        float t = fract(phase + uTime * uSpeed * (0.8 + 0.4 * fract(phase * 7.0)));
        vec3 p = mix(mix(position, c, t), mix(c, b, t), t);
        p += 0.12 * vec3(sin(phase * 91.0 + uTime), cos(phase * 57.0 + uTime * 1.3), sin(phase * 33.0));
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        float lit = uFocus < 0.0 ? 1.0 : (lane == uFocus ? 1.8 : 0.25);
        vA = sin(t * 3.14159) * lit;
        vColor = color;
        gl_PointSize = uSize * uScale / max(-mv.z, 0.1) * (0.6 + 0.6 * lit);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float uOpacity;
      varying vec3 vColor;
      varying float vA;
      void main() {
        vec2 q = gl_PointCoord * 2.0 - 1.0;
        float d = dot(q, q);
        if (d > 1.0) discard;
        gl_FragColor = vec4(vColor * exp(-d * 5.0) * vA * uOpacity, 1.0);
      }
    `,
  });
  const points = new THREE.Points(g, material);
  points.frustumCulled = false;
  return points;
}

// A see-through surface, bright at its silhouette, for hologram solids.
export function rim(color: number, opacity = 1, core = 0.18) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
    uniforms: { uColor: { value: new THREE.Color(color) }, uOpacity: { value: opacity }, uCore: { value: core } },
    vertexShader: /* glsl */ `
      varying vec3 vN;
      varying vec3 vView;
      void main() {
        vN = normalize(normalMatrix * normal);
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vView = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform vec3 uColor;
      uniform float uOpacity, uCore;
      varying vec3 vN;
      varying vec3 vView;
      void main() {
        float f = pow(1.0 - abs(dot(normalize(vN), normalize(vView))), 2.2);
        gl_FragColor = vec4(uColor * (uCore + 1.6 * f) * uOpacity, 1.0);
      }
    `,
  });
}
