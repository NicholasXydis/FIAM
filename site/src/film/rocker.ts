// The market under the gimbal, a heavy body on a curved base.
export class Rocker {
  // Tilts about x and z, one every 1/600 s from the start.
  private table: [number, number][] = [];
  private step = 1 / 600;

  // Steps the knocked, settling sway at 600 Hz into the table of tilts.
  constructor(
    private from: number,
    to: number,
    knocks: { at: number; a: number; b: number }[],
    hz = 0.55,
    damping = 0.14,
  ) {
    const w = 2 * Math.PI * hz;
    // Starts a little tilted and already swaying.
    let [a, b, va, vb] = [0.035, -0.02, 0, 0.05];
    for (let t = from; t <= to + this.step; t += this.step) {
      // A knock that falls inside this step kicks both angular speeds.
      for (const k of knocks)
        if (t <= k.at && t + this.step > k.at) {
          va += k.a;
          vb += k.b;
        }
      // The rest tilt wanders slowly, so the body never stands dead still.
      const drift = 0.012 * Math.sin(t * 0.9) + 0.008 * Math.sin(t * 1.7 + 1);
      // A damped spring pulls each tilt toward the wandering rest.
      va += (-w * w * (a - drift) - 2 * damping * w * va) * this.step;
      vb += (-w * w * (b + drift * 0.7) - 2 * damping * w * vb) * this.step;
      a += va * this.step;
      b += vb * this.step;
      this.table.push([a, b]);
    }
  }

  // The tilt about x and about z at time t, in radians.
  at(t: number): [number, number] {
    const i = Math.min(this.table.length - 2, Math.max(0, (t - this.from) / this.step));
    const k = i - Math.floor(i);
    const [a0, b0] = this.table[Math.floor(i)];
    const [a1, b1] = this.table[Math.floor(i) + 1];
    return [a0 + (a1 - a0) * k, b0 + (b1 - b0) * k];
  }
}
