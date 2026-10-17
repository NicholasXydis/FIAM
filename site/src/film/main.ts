import "./film.css";
import * as THREE from "three";
import { Agents } from "./agents";
import { Book, SHELF as LEDGE } from "./book";
import {
  AGENTS,
  AT,
  END,
  FADE,
  LENGTH,
  MARKS,
  opening,
  ROLES,
  said,
  SEA,
  SHARPE,
  SHELF,
  SHOCKS,
  SOUNDS,
  STUDIO,
  TITLES,
  VOICE,
} from "./cut";
import { clamp, halton, inOut, mix, out, ramp, span } from "./ease";
import { Gimbal } from "./gimbal";
import { Lattice } from "./lattice";
import { Look } from "./look";
import { lift, place, track, type Shot } from "./rig";
import { Rocker } from "./rocker";
import { contact, NIGHT, Studio } from "./studio";
import { End, h, Marks, Tags, Titles } from "./titles";
import { Water } from "./water";

const params = new URLSearchParams(location.search);
const record = params.has("record");
const canvas = h("canvas", { id: "gl", "aria-label": "QUARCC Purple, calm by design" }) as HTMLCanvasElement;
const titles = new Titles(TITLES);
const marks = new Marks(MARKS);
const tags = new Tags(ROLES, AGENTS.enter + 0.4, AGENTS.read - 0.1);
const end = new End(END, FADE);
document.body.append(canvas, marks.el, tags.el, titles.el, end.el);
await Promise.all([
  document.fonts.load("400 100px 'Instrument Serif'"),
  document.fonts.load("italic 400 100px 'Instrument Serif'"),
  document.fonts.load("500 100px 'Geist'"),
  document.fonts.load("400 100px 'Geist Mono'"),
]);

const look = new Look(canvas);
const { scene, camera } = look;
const studio = new Studio(look.studio);
const gimbal = new Gimbal();
const pool = contact(2.4, 0.42);
studio.group.add(pool);
const book = new Book();
book.times = {
  scan: AT.shelf,
  long: said("neutral", "strongest") - 0.2,
  short: said("neutral", "weakest") - 0.2,
  settle: said("neutral", "weakest") + 0.6,
  verify: AGENTS.verify,
};
const agents = new Agents(AGENTS);
const lattice = new Lattice();
const start = lattice.near(70, -35);
const OPEN = opening(start);
look.resize(innerWidth, innerHeight, record ? 1 : Math.min(devicePixelRatio, 2));
const water = new Water(SHOCKS, look.size);

// One light, the first agent the film sees, and later the steady gold light that is our book.
const glow = (power: number) =>
  new THREE.Mesh(
    new THREE.SphereGeometry(1, 24, 12),
    new THREE.MeshBasicMaterial({ color: new THREE.Color(0xf2c14e).multiplyScalar(power), transparent: true }),
  );
const spark = glow(7);
spark.position.copy(start);
const beacon = glow(5);
scene.add(studio.group, gimbal.group, book.group, agents.group, lattice.group, water.group, spark, beacon);

function resize() {
  look.resize(innerWidth, innerHeight, record ? 1 : Math.min(devicePixelRatio, 2));
  water.resize(look.size);
  document.documentElement.style.setProperty("--lift", String(lift(innerWidth, innerHeight)));
}
resize();
addEventListener("resize", resize);

// The market under the gimbal, rocking on its own and knocked twice as the line is spoken.
const KNOCKS = [
  { at: 14.6, a: -0.05, b: 0.34 },
  { at: 15.8, a: 0.24, b: -0.22 },
];
const rocker = new Rocker(AT.studio, AT.shelf + 0.5, KNOCKS);

// The camera flinching for a moment at each knock, and shaking as the herd breaks, in degrees.
function flinch(t: number) {
  return KNOCKS.reduce((sum, k) => {
    const s = t - k.at;
    return s > 0 ? sum + Math.sin(31 * s) * Math.exp(-7 * s) * 0.5 : sum;
  }, 0);
}
function shake(t: number) {
  const s = t - AT.panic;
  return s > 0 ? (Math.sin(t * 37) + Math.sin(t * 23 + 1)) * 0.45 * Math.exp(-s * 1.5) : 0;
}

function bloom(strength: number, threshold: number, radius = 0.55) {
  look.bloom.strength = strength;
  look.bloom.threshold = threshold;
  look.bloom.radius = radius;
}

// A point on the unit disc, spread evenly, for sampling the lens.
function disc(a: number, b: number) {
  const x = 2 * a - 1;
  const y = 2 * b - 1;
  if (!x && !y) return [0, 0];
  const [r, theta] =
    Math.abs(x) > Math.abs(y) ? [x, (Math.PI / 4) * (y / x)] : [y, Math.PI / 2 - (Math.PI / 4) * (x / y)];
  return [r * Math.cos(theta), r * Math.sin(theta)];
}

function shotAt(t: number): Shot {
  if (t < AT.cut) {
    const shot = track(OPEN, t, { end: true });
    shot.yaw += shake(t);
    shot.pitch += shake(t + 0.13);
    return shot;
  }
  if (t < AT.shelf) {
    const shot = track(STUDIO, Math.max(t, AT.studio), { end: true });
    shot.pitch += flinch(t);
    shot.yaw += flinch(t + 0.05) * 0.6;
    return shot;
  }
  if (t < AT.sea) return track(SHELF, t, { start: true, end: true });
  return track(SEA, t, { start: true });
}

// Keeps a light the same size on screen wherever the camera is.
function steady(mesh: THREE.Mesh, at: THREE.Vector3, pixels: number, opacity: number) {
  const size = look.size;
  mesh.visible = opacity > 0;
  mesh.position.copy(at);
  const d = camera.position.distanceTo(at);
  mesh.scale.setScalar(((pixels / size.y) * 2 * d * Math.tan((camera.fov * Math.PI) / 360)) / 2);
  (mesh.material as THREE.MeshBasicMaterial).opacity = opacity;
}

// Sets the whole world to time t. Jitter nudges the camera by under a pixel, the lens sample moves
// it across the aperture and soft moves the key light, so averaged subframes come out smooth, with
// depth of field and soft shadows.
function set(t: number, jitter = [0, 0], lens = [0, 0], soft = [0, 0]) {
  const size = look.size;
  const open = t < AT.cut;
  const inStudio = t >= AT.studio && t < AT.sea;
  const inSea = t >= AT.sea;
  const outro = inSea && t >= AT.outro;
  const night = inOut(ramp(t, AT.crowd, AT.crowd + 1.6));
  place(camera, shotAt(t), size.x, size.y, jitter, lens);
  studio.group.visible = inStudio && night < 1;
  gimbal.group.visible = (inStudio && t < AT.shelf) || inSea;
  book.group.visible = inStudio && t >= AT.shelf;
  lattice.group.visible = open || (inStudio && t >= AT.crowd) || (outro && t >= AT.outro + 1);
  water.group.visible = inSea;
  agents.group.visible = false;
  spark.visible = beacon.visible = false;
  scene.fog = null;
  scene.background = NIGHT;
  scene.environment = null;
  look.renderer.toneMappingExposure = 1;
  let vignette = 0.7;
  if (open) {
    const panic = t - AT.panic;
    lattice.update(t, size, {
      origin: [start.x, start.z],
      reach: 620 * out(ramp(t, 0.5, 8.4)),
      grow: mix(0.05, 1, ramp(t, 0.9, 7.6) ** 1.3),
      herd: 0.75 * inOut(ramp(t, said("rise", "And"), AT.panic)),
      panic: panic > 0 ? panic : 0,
    });
    steady(spark, start, 9, 1 - ramp(t, 2.4, 4.6));
    bloom(0.75, 0.35, 0.7);
    vignette = 0.75;
  } else if (inStudio) {
    const day = 1 - inOut(ramp(t, AT.dusk, AT.dusk + 1.6));
    studio.light(scene, day, soft, night);
    scene.environment = look.studio;
    if (t < AT.shelf) {
      const [a, b] = rocker.at(t);
      gimbal.group.position.set(0, 0, 0);
      gimbal.stand.visible = true;
      gimbal.tilt(a, b, t * 0.12);
      gimbal.read(0, 1, 0);
      pool.visible = true;
      pool.position.set(gimbal.base.position.x, 0.004, gimbal.base.position.z);
    } else {
      pool.visible = false;
      agents.centre.set(0, LEDGE + 0.4, 0);
      agents.update(t, size, camera);
      book.update(t, agents.group.visible ? agents.now : []);
      book.fade(1 - ramp(t, AT.dusk, AT.agents + 2));
    }
    if (t >= AT.crowd) {
      const thirty = said("crowd", "Thirty");
      lattice.update(t, size, {
        reach: 430 * ramp(t, AT.crowd + 0.4, AT.sea - 0.4) ** 1.6,
        herd: 0.38 * inOut(ramp(t, thirty - 1.5, thirty + 2)),
      });
      steady(beacon, new THREE.Vector3(0, LEDGE + 0.4, 0), 10, ramp(t, AT.crowd + 1.5, AT.crowd + 3));
      if (night >= 1) scene.fog = null;
    }
    bloom(
      mix(mix(0.55, t < 12.4 ? 0.6 : 0.12, day), 0.75, night),
      mix(mix(0.6, t < 12.4 ? 0.05 : 3, day), 0.45, night),
      mix(0.55, 0.75, night),
    );
    look.renderer.toneMappingExposure = mix(1, 0.92, day);
    vignette = mix(mix(0.65, 0.22, day), 0.75, night);
  } else if (inSea) {
    scene.environment = look.night;
    scene.environmentIntensity = 1;
    const sea = 1 - ramp(t, AT.outro + 1.2, AT.outro + 3);
    water.update(t, inOut(ramp(t, AT.outro, AT.outro + 6)), mix(0.012, 0.004, ramp(t, 44, 47)), sea);
    const stats = span(t, AT.stats + 0.6, AT.outro + 1.2, 0.8, 1.2);
    water.moon.intensity = mix(0.6, 1.0, stats);
    water.moon.color.lerpColors(MOON, WARM, stats);
    const dx = water.height(1.6, 0, t) - water.height(-1.6, 0, t);
    const dz = water.height(0, 1.6, t) - water.height(0, -1.6, t);
    gimbal.stand.visible = false;
    gimbal.tilt(dz * 0.06, -dx * 0.06, t * 0.12);
    gimbal.group.position.set(0, 0.6 - Gimbal.centre + water.height(0, 0, t) * 0.12, 0);
    gimbal.read(SHARPE * inOut(ramp(t, 46.2, 47.6)), 2, stats, "SHARPE RATIO");
    water.follow(camera);
    if (outro) {
      const centre = new THREE.Vector3(0, 0.6, 0);
      agents.centre.copy(centre);
      agents.update(t, size, camera, ramp(t, AT.outro + 1, AT.outro + 2.8));
      lattice.update(t, size, {
        reach: 520 * ramp(t, AT.outro + 1.4, LENGTH - 2) ** 1.4,
        herd: 0.25,
        fade: 0.75 * ramp(t, AT.outro + 1, AT.outro + 2.5),
      });
      steady(beacon, centre, 10, ramp(t, AT.outro + 3, AT.outro + 5));
    }
    const planet = ramp(t, AT.outro + 1, AT.outro + 3);
    bloom(mix(0.6, 0.75, planet), mix(0.6, 0.35, planet), mix(0.6, 0.7, planet));
  } else bloom(0.6, 0.05, 0.35);
  const line = t >= AT.cut && t < 13.8;
  look.line.enabled = line;
  if (line) {
    const u = look.line.uniforms;
    u.uY.value = 0.5 + lift(size.x, size.y);
    u.uDraw.value = out(ramp(t, AT.cut + 0.2, AT.cut + 1.2));
    u.uSlit.value = inOut(ramp(t, 12.4, 13.6));
    u.uGlow.value = 1 - ramp(t, 12.7, 13.7);
  }
  look.grade.uniforms.uVignette.value = vignette;
  look.grade.uniforms.uFade.value = ramp(t, FADE, LENGTH - 0.05);
  look.grade.uniforms.uDim.value = 0.62 * inOut(ramp(t, END.name + 0.3, END.name + 1.6));
}

const MOON = new THREE.Color(0xc9c0ff);
const WARM = new THREE.Color(0xfff1dc);

// One frame of the film at time t, as the average of n subframes spread over the shutter.
function draw(t: number, n = 1, fps = 60, shutter = 0.5) {
  look.render(n, (k) => {
    const many = n > 1;
    const dt = many ? (((k + 0.5) / n - 0.5) * shutter) / fps : 0;
    const j = many ? [halton(k, 2) - 0.5, halton(k, 3) - 0.5] : [0, 0];
    const lens = many ? disc(halton(k, 5), halton(k, 7)) : [0, 0];
    const s = many ? [(halton(k, 11) - 0.5) * 1.4, (halton(k, 13) - 0.5) * 1.4] : [0, 0];
    set(t + dt, j, lens, s);
  });
  titles.update(t);
  marks.update(t, camera, innerWidth, innerHeight);
  tags.update(t, agents.now, camera, innerWidth, innerHeight);
  end.update(t);
}

// Watching it live: the picture runs at once; a click adds the soundtrack (film.m4a beside the
// page), space pauses, the arrows step five seconds, and the bar along the bottom seeks.
function player(from: number) {
  const audio = new Audio("film.m4a");
  const bar = h("div", { class: "bar" }, h("div", { class: "bar-fill" }));
  const hint = h("p", { class: "hint" }, "Click for sound · Space pauses · ← → skip");
  document.body.append(bar, hint);
  let clock = from;
  let paused = false;
  let last = performance.now();
  const seek = (to: number) => {
    clock = (to + LENGTH) % LENGTH;
    audio.currentTime = clock;
  };
  addEventListener("pointerdown", (e) => {
    if (e.clientY > innerHeight - 40) return seek((e.clientX / innerWidth) * LENGTH);
    if (audio.paused) {
      audio.currentTime = clock;
      void audio.play().catch(() => {});
      paused = false;
    }
    hint.classList.add("off");
  });
  addEventListener("keydown", (e) => {
    if (e.key === " ") {
      paused = !paused;
      if (paused) audio.pause();
      else {
        audio.currentTime = clock;
        void audio.play().catch(() => {});
      }
    } else if (e.key === "ArrowRight") seek(clock + 5);
    else if (e.key === "ArrowLeft") seek(clock - 5);
    else return;
    e.preventDefault();
  });
  const loop = () => {
    const now = performance.now();
    if (!audio.paused && !audio.ended) clock = audio.currentTime;
    else if (!paused) clock += (now - last) / 1000;
    last = now;
    if (clock >= LENGTH) seek(0);
    draw(clock);
    (bar.firstChild as HTMLElement).style.transform = `scaleX(${clamp(clock / LENGTH).toFixed(4)})`;
    requestAnimationFrame(loop);
  };
  loop();
}

if (record) {
  Object.assign(window, {
    __draw: draw,
    __camera: (t: number) => {
      set(t);
      return camera.position.toArray();
    },
    __length: LENGTH,
    __cues: { voice: VOICE, sounds: SOUNDS },
    __ready: true,
  });
} else if (params.has("t")) {
  const t = Number(params.get("t"));
  const still = () => {
    draw(t);
    requestAnimationFrame(still);
  };
  still();
} else player(Number(params.get("from") ?? 0));
