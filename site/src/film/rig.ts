import * as THREE from "three";

// A shot is a subject to keep in frame: its centre, the radius that must fit, and the angle (in
// degrees) the camera sees it from. Focus is the focal distance as a share of the distance to the
// subject, blur the lens aperture as a share of that distance, so a shot can rack focus.
export interface Shot {
  at: [number, number, number];
  r: number;
  yaw: number;
  pitch: number;
  fov?: number;
  roll?: number;
  shift?: number;
  focus?: number;
  blur?: number;
}

export type Key = [number, Shot];

const D2R = Math.PI / 180;
const FIELDS = ["r", "yaw", "pitch", "fov", "roll", "shift", "focus", "blur"] as const;
const DEFAULTS = { fov: 30, roll: 0, shift: 0, focus: 1, blur: 0 };

// One value along a smooth curve through the keys: a Catmull-Rom spline, so the speed carries
// through every key without stopping, eased to rest at the ends unless told to keep moving. A value
// held across two keys stays exactly still, rather than winding up for the next move.
function curve(ts: number[], ys: number[], t: number, start: boolean, end: boolean) {
  const n = ts.length;
  if (n === 1 || t <= ts[0]) return ys[0];
  if (t >= ts[n - 1]) return ys[n - 1];
  const m = ys.map((_, i) => {
    if (i === 0) return start ? (ys[1] - ys[0]) / (ts[1] - ts[0]) : 0;
    if (i === n - 1) return end ? (ys[i] - ys[i - 1]) / (ts[i] - ts[i - 1]) : 0;
    if (ys[i] === ys[i - 1] || ys[i] === ys[i + 1]) return 0;
    return (ys[i + 1] - ys[i - 1]) / (ts[i + 1] - ts[i - 1]);
  });
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

// The shot at time t: every value glides through the keys without stopping at any of them.
export function track(keys: Key[], t: number, moving: { start?: boolean; end?: boolean } = {}): Shot {
  const ts = keys.map((k) => k[0]);
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
  shot.r = Math.exp(value((s) => Math.log(s.r)));
  return shot;
}

const right = new THREE.Vector3();
const up = new THREE.Vector3();

// Frames a shot for any screen. Wide screens fit the subject to the height, tall ones to the width
// with a little more room, and both sit it slightly above centre to leave space for the words. A
// lens sample moves the camera across its aperture and shears the view so the focal plane stays put,
// which is how averaged subframes make real depth of field.
export function place(camera: THREE.PerspectiveCamera, s: Shot, w: number, h: number, jitter = [0, 0], lens = [0, 0]) {
  const aspect = w / h;
  const tall = aspect < 1;
  const fov = (s.fov ?? 30) * D2R;
  const v = tall ? 2 * Math.atan(Math.tan((fov * 1.18) / 2) / aspect) : fov;
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
  const aperture = d * (s.blur ?? 0);
  const scale = h / 2 / (d * (s.focus ?? 1) * Math.tan(v / 2));
  right.setFromMatrixColumn(camera.matrix, 0);
  up.setFromMatrixColumn(camera.matrix, 1);
  camera.position.addScaledVector(right, lens[0] * aperture).addScaledVector(up, lens[1] * aperture);
  camera.fov = v / D2R;
  camera.aspect = aspect;
  camera.near = Math.max(0.05, d * 0.02);
  camera.far = 1500;
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

// How far above centre the subject sits, as a share of the screen height.
export const lift = (w: number, h: number) => (w / h < 1 ? 0.09 : 0.06);
