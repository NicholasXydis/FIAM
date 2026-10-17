// Sound made in the browser, no files: a low drone under everything, a whoosh between scenes and a
// soft tick when something lands. Off until the viewer turns it on, as browsers require.
export class Sound {
  on = false;
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private noise: AudioBuffer | null = null;
  private lastTick = 0;

  private start() {
    const ctx = new AudioContext();
    const master = ctx.createGain();
    master.gain.value = 0;
    master.connect(ctx.destination);
    const filter = ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = 520;
    filter.Q.value = 0.7;
    filter.connect(master);
    const lfo = ctx.createOscillator();
    const depth = ctx.createGain();
    lfo.frequency.value = 0.06;
    depth.gain.value = 220;
    lfo.connect(depth).connect(filter.frequency);
    lfo.start();
    for (const [freq, type, level] of [
      [55, "sine", 0.32],
      [82.4, "triangle", 0.16],
      [110.3, "sine", 0.12],
      [164.6, "sine", 0.05],
    ] as const) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type;
      osc.frequency.value = freq;
      gain.gain.value = level;
      osc.connect(gain).connect(filter);
      osc.start();
    }
    const length = ctx.sampleRate * 2;
    this.noise = ctx.createBuffer(1, length, ctx.sampleRate);
    const data = this.noise.getChannelData(0);
    for (let i = 0; i < length; i++) data[i] = Math.random() * 2 - 1;
    this.ctx = ctx;
    this.master = master;
  }

  toggle(on = !this.on) {
    this.on = on;
    if (on && !this.ctx) this.start();
    if (!this.ctx || !this.master) return;
    if (on) void this.ctx.resume();
    const now = this.ctx.currentTime;
    this.master.gain.cancelScheduledValues(now);
    this.master.gain.setTargetAtTime(on ? 0.22 : 0, now, 0.4);
  }

  // A filtered noise sweep, like air rushing past, for moving between scenes.
  whoosh(strength = 1) {
    if (!this.on || !this.ctx || !this.noise || !this.master) return;
    const ctx = this.ctx;
    const now = ctx.currentTime;
    const source = ctx.createBufferSource();
    source.buffer = this.noise;
    const band = ctx.createBiquadFilter();
    band.type = "bandpass";
    band.Q.value = 1.4;
    band.frequency.setValueAtTime(260, now);
    band.frequency.exponentialRampToValueAtTime(2400, now + 0.55);
    band.frequency.exponentialRampToValueAtTime(380, now + 1.5);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.5 * strength, now + 0.35);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 1.6);
    source.connect(band).connect(gain).connect(this.master);
    source.start(now);
    source.stop(now + 1.7);
  }

  // A short soft bell, at most a few times a second.
  tick(pitch = 1, level = 1) {
    if (!this.on || !this.ctx || !this.master) return;
    const ctx = this.ctx;
    const now = ctx.currentTime;
    if (now - this.lastTick < 0.06) return;
    this.lastTick = now;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 660 * pitch;
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.18 * level, now + 0.008);
    gain.gain.exponentialRampToValueAtTime(0.0008, now + 0.45);
    osc.connect(gain).connect(this.master);
    osc.start(now);
    osc.stop(now + 0.5);
  }
}
