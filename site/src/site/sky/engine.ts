import { seeded } from "@/shared/math";
import { FLOATS, points } from "./gl";
import { fontsReady, letters } from "./letters";

// What the motes form: the name, or dust drifting through the sky.
type Shape = "name" | "dust";

// What the page gives the sky: the box the name fills, if any.
interface Options {
  stage: () => DOMRect | null;
}

// A far star: place, depth for parallax, brightness, size, twinkle.
interface Star {
  x: number;
  y: number;
  z: number;
  a: number;
  s: number;
  ph: number;
  f: number;
}

// A mote: where it is and heads, its dust spot, colour and look.
interface Mote {
  x: number;
  y: number;
  vx: number;
  vy: number;
  tx: number;
  ty: number;
  dx: number;
  dy: number;
  col: [number, number, number];
  a: number;
  s: number;
  ph: number;
  wait: number;
  free: boolean;
  g: number;
}

// A speck of dust rising through the light.
interface Ember {
  x: number;
  y: number;
  vy: number;
  a: number;
  s: number;
  ph: number;
  f: number;
}

// A control the dust swirls round: its box and its corner radius.
export interface Ring {
  x: number;
  y: number;
  w: number;
  h: number;
  r: number;
}

// One reused answer, so measuring motes each frame allocates nothing.
const spot = { ox: 0, oy: 0, nx: 0, ny: 0, gap: 0 };

// The nearest point on a ring's outline to a point, and how far it is.
function outline(ring: Ring, x: number, y: number) {
  const cx = Math.min(Math.max(x, ring.x + ring.r), ring.x + ring.w - ring.r);
  const cy = Math.min(Math.max(y, ring.y + ring.r), ring.y + ring.h - ring.r);
  const d = Math.hypot(x - cx, y - cy) + 0.001;
  spot.nx = (x - cx) / d;
  spot.ny = (y - cy) / d;
  spot.ox = cx + spot.nx * ring.r;
  spot.oy = cy + spot.ny * ring.r;
  spot.gap = Math.hypot(x - spot.ox, y - spot.oy);
  return spot;
}

// How far from a control's outline the dust feels its pull.
const PULL = 170;
// How far outside the outline the captured dust settles into orbit.
const ORBIT = 13;

// A shooting star: when it started, its path, life and brightness.
interface Comet {
  t0: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  a: number;
}

// Dust between the stars: a soft violet, dimmer than the name.
const DUST: [number, number, number] = [0.72, 0.68, 1];
// At most three shooting stars at once, each a head and a tail.
const COMETS = 3;
const TAIL = 30;

// The name's colours: violet to periwinkle, a few gold and white.
function tint(across: number): [number, number, number] {
  const r = Math.random();
  if (r < 0.06) return [1, 0.84, 0.55];
  if (r < 0.14) return [0.95, 0.94, 1];
  return [0.66 - 0.1 * across, 0.55 + 0.12 * across, 1];
}

// Starts the sky on a canvas; null without WebGL2, so the text stays.
export function startSky(canvas: HTMLCanvasElement, options: Options) {
  const gl = points(canvas);
  if (!gl) return null;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const pointer = { x: -1e4, y: -1e4, vx: 0, vy: 0 };
  // Where the name's light falls, for the stars it brightens.
  const light = { x: 0, y: 0, rx: 1, ry: 1, on: 0, k: 0 };
  const comets: Comet[] = [];
  let random = seeded(7);
  let w = 0;
  let h = 0;
  let stars: Star[] = [];
  let motes: Mote[] = [];
  let embers: Ember[] = [];
  let data = new Float32Array(0);
  let current: Shape = "dust";
  let instant = false;
  let nextComet = 1;
  let start = 0;
  let then = 0;
  let raf = 0;
  let o = 0;
  let ring: Ring | null = null;

  // Writes one point into the frame's buffer.
  const put = (x: number, y: number, r: number, g: number, b: number, a: number, s: number) => {
    data[o++] = x;
    data[o++] = y;
    data[o++] = r;
    data[o++] = g;
    data[o++] = b;
    data[o++] = a;
    data[o++] = s;
  };

  // Lays the sky out for the screen; motes keep their place on resize.
  function layout() {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    w = innerWidth;
    h = innerHeight;
    gl!.resize(w, h, dpr);
    random = seeded(7);
    const area = w * h;
    stars = Array.from({ length: Math.round(Math.min(2600, Math.max(500, area / 900))) }, () => ({
      x: random() * w,
      y: random() * h,
      z: 0.3 + random() * 0.7,
      a: 0.03 + random() ** 2 * 0.36,
      s: 0.9 + random() ** 4 * 2.6,
      ph: random() * 6.28,
      f: 0.4 + random() * 1.6,
    }));
    const old = motes;
    motes = Array.from({ length: Math.round(Math.min(22000, Math.max(6500, area / 45))) }, (_, i) => {
      const was = old[i];
      return {
        x: was ? was.x : random() * w,
        y: was ? was.y : h * (0.6 + random() * 0.6),
        vx: 0,
        vy: was ? was.vy : -40 - random() * 80,
        tx: 0,
        ty: 0,
        dx: random() * w,
        dy: random() * h,
        col: was ? was.col : [1, 1, 1],
        a: 0.5 + random() * 0.5,
        s: 1.6 + random() ** 3 * 3.2,
        ph: random() * 6.28,
        wait: reduce || was ? 0 : random() * 1.2,
        free: true,
        g: was ? was.g : 0,
      };
    });
    embers = Array.from({ length: Math.round(Math.min(520, Math.max(140, area / 2800))) }, () => ({
      x: random() * w,
      y: random() * h,
      vy: -(8 + random() * 20),
      a: 0.05 + random() * 0.2,
      s: 1 + random() ** 2 * 2.4,
      ph: random() * 6.28,
      f: 0.3 + random() * 0.9,
    }));
    data = new Float32Array((stars.length + motes.length * 2 + embers.length + COMETS * TAIL) * FLOATS);
    shape(current, instant);
    // Only the first layout may snap; a resize lets the motes drift over.
    instant = false;
  }

  // Sends the motes to the name or to dust; instant skips the flight.
  function shape(next: Shape, now = false) {
    current = next;
    const box = next === "name" ? options.stage() : null;
    const spots = box ? letters(box, motes.length, random) : [];
    motes.forEach((m, i) => {
      const s = spots[i];
      if (s) Object.assign(m, { tx: s.x, ty: s.y, col: tint(s.across), free: false });
      else Object.assign(m, { tx: m.dx, ty: m.dy, col: DUST, free: true });
      if (reduce || now) Object.assign(m, { x: m.tx, y: m.ty, vx: 0, vy: 0, wait: 0, g: m.free ? 0 : 1 });
    });
    if (box) Object.assign(light, { x: box.x + box.width / 2, y: box.y + box.height / 2, rx: box.width * 0.55 });
    Object.assign(light, { on: box ? 1 : 0 });
    if (box) light.ry = box.height * 0.75;
    if (box && (reduce || now)) light.k = 1;
  }

  // One frame: stars, the motes' springs, dust, and shooting stars.
  function step(now: number) {
    const dt = Math.min(0.033, (now - then) / 1000);
    then = now;
    const t = (now - start) / 1000;
    const reach = Math.min(w, h) * 0.17;
    // Dust floats loosely; the name's motes settle fast, so it reads soon.
    const damp = Math.exp(-dt * 4.2);
    const hold = Math.exp(-dt * 10.5);
    const px = (pointer.x - w / 2) / w;
    const py = (pointer.y - h / 2) / h;
    o = 0;
    light.k += (light.on - light.k) * Math.min(1, dt * 2.5);
    // Stars drift at their depth, and brighten in the name's light.
    for (const s of stars) {
      const tw = 0.4 + 0.6 * Math.sin(t * s.f + s.ph);
      const x = (((s.x + (reduce ? 0 : -px * 18 * s.z - t * 9 * s.z)) % w) + w) % w;
      const y = (((s.y + (reduce ? 0 : -py * 12 * s.z + t * 2 * s.z)) % h) + h) % h;
      const gx = (x - light.x) / light.rx;
      const gy = (y - light.y) / light.ry;
      const lit = light.k * Math.exp(-(gx * gx + gy * gy));
      put(x, y, 0.8 + lit * 0.1, 0.74 + lit * 0.08, 1, s.a * tw * (0.7 + lit * 1.8), s.s);
    }
    // Motes spring home, swirl gently, and part around the pointer.
    let halo = o + motes.length * FLOATS;
    for (const m of motes) {
      if (!reduce && t > m.wait) {
        const wob = m.free ? 40 : 2.2;
        const tx = m.tx + Math.sin(t * (m.free ? 0.15 : 1.3) + m.ph) * wob;
        const ty = m.ty + Math.cos(t * (m.free ? 0.12 : 1.1) + m.ph) * wob;
        const k = m.free ? 2.5 : 34;
        let ax = (tx - m.x) * k;
        let ay = (ty - m.y) * k;
        const dx = m.x - pointer.x;
        const dy = m.y - pointer.y;
        const d = Math.hypot(dx, dy) + 0.001;
        if (d < reach && !ring) {
          const f = (1 - d / reach) ** 2;
          ax += ((dx / d) * 2200 - (dy / d) * 1300) * f + pointer.vx * f * 16;
          ay += ((dy / d) * 2200 + (dx / d) * 1300) * f + pointer.vy * f * 16;
        }
        // Free dust near a hovered control lets go of home and orbits it.
        if (ring && m.free) {
          const { ox, oy, nx, ny, gap } = outline(ring, m.x, m.y);
          if (gap < PULL) {
            const f = (1 - gap / PULL) ** 0.7;
            const px = ox + nx * ORBIT - m.x;
            const py = oy + ny * ORBIT - m.y;
            ax += (px * 26 - (tx - m.x) * k * 0.85) * f - ny * 300 * f;
            ay += (py * 26 - (ty - m.y) * k * 0.85) * f + nx * 300 * f;
          }
        }
        m.vx = (m.vx + ax * dt) * (m.free ? damp : hold);
        m.vy = (m.vy + ay * dt) * (m.free ? damp : hold);
        m.x += m.vx * dt;
        m.y += m.vy * dt;
      }
      // Brightness eases between dust and name, so changes never snap.
      m.g += ((m.free ? 0 : 1) - m.g) * Math.min(1, dt * 3);
      const near = ring && m.free ? Math.max(0, 1 - Math.abs(outline(ring, m.x, m.y).gap - ORBIT) / 30) : 0;
      const speed = Math.min(1, Math.hypot(m.vx, m.vy) / 600);
      const breath = 1 - 0.1 * m.g + 0.1 * m.g * Math.sin(t * 0.9);
      const glow = (0.45 + 0.55 * m.g + near * 0.9) * breath * (0.8 + 0.2 * Math.sin(t * 2 + m.ph));
      const [r, g, b] = m.col;
      put(
        m.x,
        m.y,
        r + speed * 0.3 + near * 0.2,
        g + speed * 0.2 + near * 0.15,
        b,
        m.a * glow,
        m.s * (1 + speed * 0.6),
      );
      // A wide, faint copy of every mote: the bloom that lights the dark.
      const at = o;
      o = halo;
      put(m.x, m.y, (r + speed * 0.3) * 0.8, (g + speed * 0.2) * 0.7, b, (0.015 + 0.055 * m.g) * m.a, m.s * 7);
      halo = o;
      o = at;
    }
    o = halo;
    // Dust rises, sways and wraps round to the bottom again.
    for (const e of embers) {
      if (!reduce) e.y += e.vy * dt;
      // Rising dust is drawn to a hovered control too, more gently.
      if (ring && !reduce) {
        const { ox, oy, gap } = outline(ring, e.x, e.y);
        if (gap < PULL) {
          e.x += (ox - e.x) * Math.min(1, dt * 3) * (1 - gap / PULL);
          e.y += (oy - e.y) * Math.min(1, dt * 3) * (1 - gap / PULL);
        }
      }
      if (e.y < -10) Object.assign(e, { y: h + 10, x: Math.random() * w });
      const sway = reduce ? 0 : Math.sin(t * e.f + e.ph) * 14;
      put(e.x + sway, e.y, 0.82, 0.76, 1, e.a * (0.6 + 0.4 * Math.sin(t * e.f * 2 + e.ph)), e.s);
    }
    // A shooting star every one to four seconds, quiet and behind.
    if (!reduce && t > nextComet && comets.length < COMETS) {
      const left = Math.random() < 0.5;
      comets.push({
        t0: t,
        x: left ? -60 : w + 60,
        y: h * (0.02 + Math.random() * 0.6),
        vx: (left ? 1 : -1) * (w * 0.7 + Math.random() * w * 0.6),
        vy: h * (0.06 + Math.random() * 0.16),
        life: 1 + Math.random() * 0.6,
        a: 0.35 + Math.random() * 0.4,
      });
      nextComet = t + 1.2 + Math.random() * 2.6;
    }
    for (let c = comets.length - 1; c >= 0; c--) if (t - comets[c]!.t0 > comets[c]!.life) comets.splice(c, 1);
    for (let c = 0; c < COMETS; c++) {
      const cm = comets[c];
      for (let k = 0; k < TAIL; k++) {
        if (!cm) {
          put(-99, -99, 0, 0, 0, 0, 1);
          continue;
        }
        const age = t - cm.t0 - k * 0.011;
        const fade = Math.sin(((t - cm.t0) / cm.life) * Math.PI);
        put(cm.x + cm.vx * age, cm.y + cm.vy * age, 0.9, 0.86, 1, fade * (1 - k / TAIL) ** 1.4 * cm.a, 2.6 - k * 0.06);
      }
    }
    pointer.vx *= 0.8;
    pointer.vy *= 0.8;
    gl!.draw(data);
  }

  // The pointer stirs the motes; a tap away from a control bursts them.
  const move = (e: PointerEvent) => {
    // Arriving from nowhere, the pointer has no speed yet.
    const known = pointer.x > -1e3;
    pointer.vx = known ? e.clientX - pointer.x : 0;
    pointer.vy = known ? e.clientY - pointer.y : 0;
    pointer.x = e.clientX;
    pointer.y = e.clientY;
  };
  // Throws motes out from a point, harder the nearer they are to it.
  const push = (x: number, y: number, radius: number, force: number) => {
    for (const m of motes) {
      const dx = m.x - x;
      const dy = m.y - y;
      const d = Math.hypot(dx, dy) + 0.001;
      if (d < radius) {
        m.vx += (dx / d) * (1 - d / radius) * force;
        m.vy += (dy / d) * (1 - d / radius) * force;
      }
    }
  };
  const burst = (e: PointerEvent) => {
    Object.assign(pointer, { x: e.clientX, y: e.clientY, vx: 0, vy: 0 });
    if (reduce || (e.target instanceof Element && e.target.closest("a, button"))) return;
    push(e.clientX, e.clientY, Math.min(w, h) * 0.3, 1100);
  };
  const away = () => Object.assign(pointer, { x: -1e4, y: -1e4 });
  // Runs only while the page is shown, to spare the battery.
  const loop = (now: number) => {
    step(now);
    raf = requestAnimationFrame(loop);
  };
  const shown = () => {
    cancelAnimationFrame(raf);
    if (document.hidden || !motes.length) return;
    then = performance.now();
    raf = requestAnimationFrame(loop);
  };
  addEventListener("pointermove", move, { passive: true });
  addEventListener("pointerdown", burst, { passive: true });
  document.addEventListener("pointerleave", away);
  document.addEventListener("visibilitychange", shown);
  addEventListener("resize", layout);
  let stopped = false;
  // Laid out once the serif has loaded; openings wait for this.
  const ready = fontsReady().then(() => {
    if (stopped) return;
    layout();
    start = then = performance.now();
    shown();
  });

  return {
    ready,
    // Draws the dust round a control while it is hovered, or lets it go.
    attract(next: Ring | null) {
      ring = next;
    },
    // The name dissolves outward into dust, evenly, as the visitor leaves.
    scatter() {
      const { x, y } = light;
      shape("dust");
      if (reduce) return;
      for (const m of motes) {
        const d = Math.hypot(m.x - x, m.y - y) + 0.001;
        const speed = 260 + Math.random() * 380;
        m.vx += ((m.x - x) / d) * speed + (Math.random() - 0.5) * 160;
        m.vy += ((m.y - y) / d) * speed * 0.8 + (Math.random() - 0.5) * 160;
      }
    },
    // Draws one frame now and returns the canvas, for a page to keep.
    frame() {
      if (motes.length) step(performance.now());
      return canvas;
    },
    // Changes the shape, now or once the sky has laid itself out.
    shape: (next: Shape, now = false) => (motes.length ? shape(next, now) : ((current = next), (instant = now))),
    // Stops the frames and lets go of every listener.
    stop() {
      stopped = true;
      cancelAnimationFrame(raf);
      removeEventListener("pointermove", move);
      removeEventListener("pointerdown", burst);
      document.removeEventListener("pointerleave", away);
      document.removeEventListener("visibilitychange", shown);
      removeEventListener("resize", layout);
    },
  };
}
