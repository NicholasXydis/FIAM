// Shared maths: blending, easing, seeded randomness, the golden angle.

// Keeps x between a and b, 0 and 1 by default.
export const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
// Blends from a to b as k goes from 0 to 1.
export const mix = (a: number, b: number, k: number) => a + (b - a) * k;
// Maps t in [a, b] onto 0 to 1, held at the ends.
export const ramp = (t: number, a: number, b: number) => clamp((t - a) / (b - a));
// Smoothstep: an S curve on 0 to 1, flat at both ends.
export const smooth = (x: number) => x * x * (3 - 2 * x);
// Cubic ease in and out: slow start, fast middle, slow finish.
export const inOut = (x: number) => (x < 0.5 ? 4 * x ** 3 : 1 - (-2 * x + 2) ** 3 / 2);
// Cubic ease out: fast start that settles gently.
export const out = (x: number) => 1 - (1 - x) ** 3;
// Exponential ease out: a sharp start that lands exactly on 1.
export const expo = (x: number) => (x >= 1 ? 1 : 1 - 2 ** (-10 * x));

// Rises over [a, a + rise], holds, and falls over [b - fall, b].
export const span = (t: number, a: number, b: number, rise = 0.6, fall = 0.6) =>
  smooth(ramp(t, a, a + rise)) * (1 - smooth(ramp(t, b - fall, b)));

// Mulberry32: the same random numbers for the same seed, every run.
export function seeded(seed: number) {
  let s = seed >>> 0;
  // Each call steps the state and gives a number from 0 up to 1.
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let x = Math.imul(s ^ (s >>> 15), 1 | s);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

// The k-th Halton point in a base, to spread subframe samples evenly.
export function halton(k: number, base: number) {
  let f = 1;
  let r = 0;
  // Read k's digits in the base and mirror them past the point.
  for (let i = k + 1; i > 0; i = Math.floor(i / base)) {
    f /= base;
    r += f * (i % base);
  }
  return r;
}

// The golden angle in radians, to spread points on a circle or sphere.
export const GOLDEN = Math.PI * (3 - Math.sqrt(5));
