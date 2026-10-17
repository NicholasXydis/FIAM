export const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const mix = (a: number, b: number, k: number) => a + (b - a) * k;
export const ramp = (t: number, a: number, b: number) => clamp((t - a) / (b - a));
export const smooth = (x: number) => x * x * (3 - 2 * x);
export const inOut = (x: number) => (x < 0.5 ? 4 * x ** 3 : 1 - (-2 * x + 2) ** 3 / 2);
export const out = (x: number) => 1 - (1 - x) ** 3;
export const expo = (x: number) => (x >= 1 ? 1 : 1 - 2 ** (-10 * x));

// Rises over [a, a + rise], holds, and falls over [b - fall, b].
export const span = (t: number, a: number, b: number, rise = 0.6, fall = 0.6) =>
  smooth(ramp(t, a, a + rise)) * (1 - smooth(ramp(t, b - fall, b)));

// The same random numbers for the same seed, every run.
export function seeded(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let x = Math.imul(s ^ (s >>> 15), 1 | s);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

// The k-th point of a low-discrepancy sequence, for spreading subframe samples evenly.
export function halton(k: number, base: number) {
  let f = 1;
  let r = 0;
  for (let i = k + 1; i > 0; i = Math.floor(i / base)) {
    f /= base;
    r += f * (i % base);
  }
  return r;
}
