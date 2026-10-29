import * as THREE from "three";

// A shot, the centre and radius to keep in frame and how to film it.
export interface Shot {
  at: [number, number, number];
  r: number;
  // Angles and the field of view, in degrees.
  yaw: number;
  pitch: number;
  fov?: number;
  roll?: number;
  // Extra lift, as a share of screen height.
  shift?: number;
  // Focus and aperture, as shares of the camera's distance.
  focus?: number;
  blur?: number;
}

// A key: a time and the shot to be at then.
export type Key = [number, Shot];

// Degrees to radians, and each gliding field with its default.
const D2R = Math.PI / 180;
const FIELDS = ["r", "yaw", "pitch", "fov", "roll", "shift", "focus", "blur"] as const;
const DEFAULTS = { fov: 30, roll: 0, shift: 0, focus: 1, blur: 0 };

// One value along a Catmull-Rom curve through the keys at time t.
function curve(ts: number[], ys: number[], t: number, start: boolean, end: boolean) {
  const n = ts.length;
  if (n === 1 || t <= ts[0]) return ys[0];
  if (t >= ts[n - 1]) return ys[n - 1];
  // Slopes, flat at eased ends and beside held values, which stay still.
  const m = ys.map((_, i) => {
    if (i === 0) return start ? (ys[1] - ys[0]) / (ts[1] - ts[0]) : 0;
    if (i === n - 1) return end ? (ys[i] - ys[i - 1]) / (ts[i] - ts[i - 1]) : 0;
    if (ys[i] === ys[i - 1] || ys[i] === ys[i + 1]) return 0;
    return (ys[i + 1] - ys[i - 1]) / (ts[i + 1] - ts[i - 1]);
  });
  // Finds the segment holding t and blends it with Hermite weights.
  let k = 0;
  while (t > ts[k + 1]) k++;
  const h = ts[k + 1] - ts[k];
  const s = (t - ts[k]) / h;
  const s2 = s * s;
  const s3 = s2 * s;
  return (
    (2 * s3 - 3 * s2 + 1) * ys[k] +
    (s3 - 2 * s2 + s) * h * m[k] +
    (-2 * s3 + 3 * s2) * ys[k + 1] +
    (s3 - s2) * h * m[k + 1]
  );
}

// The shot at time t, every value gliding through the keys nonstop.
export function track(keys: Key[], t: number, moving: { start?: boolean; end?: boolean } = {}): Shot {
  const ts = keys.map((k) => k[0]);
  // One field of the shot at t, read from every key by get.
  const value = (get: (s: Shot) => number) =>
    curve(
      ts,
      keys.map((k) => get(k[1])),
      t,
      !!moving.start,
      !!moving.end,
    );
  const shot = { at: [0, 1, 2].map((i) => value((s) => s.at[i])) } as Shot;
  for (const f of FIELDS) shot[f] = value((s) => s[f] ?? DEFAULTS[f as keyof typeof DEFAULTS] ?? 0);
  // The radius glides in log space, so a zoom moves by even ratios.
  shot.r = Math.exp(value((s) => Math.log(s.r)));
  return shot;
}

// Scratch camera axes for the lens shift, reused every frame.
const right = new THREE.Vector3();
const up = new THREE.Vector3();

// Frames a shot on any screen, a little above centre.
export function place(camera: THREE.PerspectiveCamera, s: Shot, w: number, h: number, jitter = [0, 0], lens = [0, 0]) {
  const aspect = w / h;
  const tall = aspect < 1;
  const fov = (s.fov ?? 30) * D2R;
  // On an upright screen the fov, widened 1.18 times, spans the width.
  const v = tall ? 2 * Math.atan(Math.tan((fov * 1.18) / 2) / aspect) : fov;
  // Backs off until the sphere fits the narrower side of the screen.
  const fit = Math.min(v, 2 * Math.atan(Math.tan(v / 2) * aspect));
  const d = s.r / Math.sin(fit / 2);
  const yaw = s.yaw * D2R;
  const pitch = s.pitch * D2R;
  camera.position.set(
    s.at[0] + d * Math.cos(pitch) * Math.sin(yaw),
    s.at[1] + d * Math.sin(pitch),
    s.at[2] + d * Math.cos(pitch) * Math.cos(yaw),
  );
  camera.up.set(0, 1, 0);
  camera.lookAt(...s.at);
  if (s.roll) camera.rotateZ(s.roll * D2R);
  camera.updateMatrix();
  // A lens sample shears the view for real depth of field.
  const aperture = d * (s.blur ?? 0);
  const scale = h / 2 / (d * (s.focus ?? 1) * Math.tan(v / 2));
  right.setFromMatrixColumn(camera.matrix, 0);
  up.setFromMatrixColumn(camera.matrix, 1);
  camera.position.addScaledVector(right, lens[0] * aperture).addScaledVector(up, lens[1] * aperture);
  camera.fov = v / D2R;
  camera.aspect = aspect;
  camera.near = Math.max(0.05, d * 0.02);
  camera.far = 1500;
  // Offsets the view by the lift, the pixel jitter and the lens shear.
  camera.setViewOffset(
    w,
    h,
    jitter[0] - lens[0] * aperture * scale,
    h * (lift(w, h) + (s.shift ?? 0)) + jitter[1] + lens[1] * aperture * scale,
    w,
    h,
  );
  camera.updateProjectionMatrix();
}

// How far above centre the subject sits, a share of screen height.
export const lift = (w: number, h: number) => (w / h < 1 ? 0.09 : 0.06);
