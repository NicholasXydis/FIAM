import "./style.css";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { Chrome } from "./chrome";
import { Sim } from "./gl/sim";
import { Stage } from "./gl/stage";
import { scenes } from "./scenes";
import type { Scene, World } from "./scenes/scene";
import { Sound } from "./sound";
import { h, hideTip, rayAt, showTip, tip } from "./ui";

const params = new URLSearchParams(location.search);
const canvas = h("canvas", { id: "gl", "aria-label": "QUARCC Purple FIAM, an animated tour of the final book" });
const layer = h("div", { class: "ui" });
document.body.append(canvas, layer);
if (params.has("present")) document.body.classList.add("present");

// Without WebGL, or a GPU that cannot run the simulation, say so plainly instead of a blank page.
function fail(reason: string): never {
  layer.append(
    h(
      "div",
      { class: "absolute inset-0 grid place-items-center p-6 text-center" },
      h(
        "div",
        { class: "glass rounded-2xl p-6 max-w-md flex flex-col gap-3" },
        h("p", { class: "headline text-[32px]" }, "QUARCC Purple · FIAM"),
        h(
          "p",
          { class: "body" },
          `This screen cannot run the 3D tour (${reason}). Open the file in a recent Chrome, Edge, Safari or Firefox with hardware acceleration on.`,
        ),
      ),
    ),
  );
  throw new Error(reason);
}

let stage: Stage;
let sim: Sim;
try {
  stage = new Stage(canvas);
  sim = new Sim(stage.renderer);
} catch (error) {
  fail(error instanceof Error ? error.message : "WebGL is unavailable");
}
stage.scene.add(sim.points);
canvas.addEventListener("webglcontextlost", (e) => {
  e.preventDefault();
  fail("the graphics context was lost, reload the page");
});

await document.fonts.load("italic 100px 'Instrument Serif'");
await document.fonts.load("600 100px 'Geist'");
await document.fonts.ready;

const sound = new Sound();
let index = -1;
let explore = false;
let touring = false;
let dwelt = 0;
const world: World = { stage, sim, layer, sound, go: (i) => go(i, true), next: () => go(index + 1, true) };
const list: Scene[] = scenes(world);
const chrome = new Chrome(layer, list, {
  go: (i) => go(i, true),
  tour: () => setTour(!touring),
  sound: () => setSound(!sound.on),
});
layer.append(tip);

function go(i: number, byHand = false) {
  const next = Math.max(0, Math.min(list.length - 1, i));
  if (byHand && touring) setTour(false);
  if (next === index) return;
  const from = list[index];
  from?.hide();
  hideTip();
  sim.m.uHover.value = -1;
  sim.m.uSelect.value = -1;
  const scene = list[next];
  const first = index < 0;
  index = next;
  dwelt = 0;
  sim.u.uStiff.value = scene.physics.stiff;
  sim.u.uDamp.value = scene.physics.damp;
  sim.u.uFlow.value = scene.physics.flow * (stage.reduced ? 0.3 : 1);
  sim.u.uSpin.value = scene.physics.spin;
  sim.show(scene.formation(), first ? 2.4 : scene.stagger, scene.duration);
  if (from) {
    const amp = list.indexOf(from) === 0 ? 1.4 : 0.6;
    sim.wave({ at: new THREE.Vector3(...scene.shot.look), amp, speed: 11 });
    sound.whoosh();
  }
  stage.frame(scene.shot);
  scene.show();
  chrome.update(index);
  history.replaceState(null, "", `#${index}`);
}

function setTour(on: boolean) {
  touring = on;
  dwelt = 0;
  chrome.setTour(on);
  chrome.tourProgress(0);
  if (on && index === list.length - 1) go(0);
}

function setSound(on: boolean) {
  sound.toggle(on);
  chrome.setSound(on);
}

const orbit = new OrbitControls(stage.camera, canvas);
orbit.enabled = false;
orbit.enableDamping = true;
orbit.minDistance = 4;
orbit.maxDistance = 80;

function setExplore(on: boolean) {
  explore = on;
  orbit.enabled = on;
  if (on) orbit.target.copy(stage.look.value);
  else {
    stage.eye.value.copy(stage.camera.position);
    stage.eye.speed.set(0, 0, 0);
  }
  document.body.classList.toggle("exploring", on);
}

addEventListener("keydown", (e) => {
  const target = e.target as HTMLElement;
  if (target instanceof HTMLInputElement && (target.type !== "range" || e.key.startsWith("Arrow"))) return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (chrome.open && !["Escape", "o", "?", "h"].includes(key) && !/^[0-9]$/.test(key)) return;
  if (list[index]?.key(e)) return e.preventDefault();
  if (["ArrowRight", "ArrowDown", "PageDown", " "].includes(key)) go(index + 1, true);
  else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(key)) go(index - 1, true);
  else if (key === "Home") go(0, true);
  else if (key === "End") go(list.length - 1, true);
  else if (/^[0-9]$/.test(key)) {
    chrome.close();
    go(+key, true);
  } else if (key === "e") setExplore(!explore);
  else if (key === "p") setTour(!touring);
  else if (key === "m") setSound(!sound.on);
  else if (key === "o") chrome.toggleOverview();
  else if (key === "?" || key === "h") chrome.toggleHelp();
  else if (key === "f") {
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
    else void document.documentElement.requestFullscreen().catch(() => {});
  } else if (key === "Escape") {
    chrome.close();
    if (explore) setExplore(false);
  } else return;
  e.preventDefault();
});

let wheelLock = 0;
let wheelSum = 0;
addEventListener(
  "wheel",
  (e) => {
    if (explore || chrome.open || (e.target as HTMLElement).closest?.(".card, .controls, .panel")) return;
    e.preventDefault();
    const now = performance.now();
    if (now < wheelLock) return;
    wheelSum += e.deltaY + e.deltaX;
    if (Math.abs(wheelSum) > 60) {
      go(index + Math.sign(wheelSum), true);
      wheelSum = 0;
      wheelLock = now + 1100;
    }
  },
  { passive: false },
);

let press: { x: number; y: number; t: number } | null = null;
canvas.addEventListener("pointerdown", (e) => {
  press = { x: e.clientX, y: e.clientY, t: performance.now() };
});
canvas.addEventListener("pointerup", (e) => {
  if (!press || explore) return (press = null);
  const dx = e.clientX - press.x;
  const dy = e.clientY - press.y;
  const swipe = e.pointerType !== "mouse" && Math.hypot(dx, dy) > 60 && performance.now() - press.t < 700;
  press = null;
  if (swipe) return go(index + (Math.abs(dx) > Math.abs(dy) ? -Math.sign(dx) : -Math.sign(dy)), true);
  if (Math.hypot(dx, dy) > 6) return;
  const ray = rayAt(e.clientX, e.clientY, stage.camera).ray;
  const depth = Math.max(4, stage.look.value.clone().sub(ray.origin).dot(ray.direction));
  sim.wave({ at: ray.origin.clone().addScaledVector(ray.direction, depth), amp: 0.8, speed: 8 });
  sound.tick(0.75, 0.6);
  list[index].click(e.clientX, e.clientY);
});

let pointerAt = 0;
let pointerMoved = false;
const mouse = { x: -1, y: -1 };
addEventListener("pointermove", (e) => {
  mouse.x = e.clientX;
  mouse.y = e.clientY;
  pointerAt = performance.now();
  pointerMoved = true;
});
document.documentElement.addEventListener("mouseleave", () => (pointerAt = 0));
addEventListener("change", (e) => {
  if (e.target instanceof HTMLInputElement && e.target.type === "range") e.target.blur();
});

const fixedQuality = params.get("q");
stage.setQuality(fixedQuality !== null ? +fixedQuality : matchMedia("(max-width: 760px)").matches ? 1 : 2);

let last = performance.now();
let time = 0;
let frames = 0;
let slow = 0;
let windowStart = last;
let hoverAge = 0;

function loop() {
  const stamp = performance.now();
  const dt = Math.min((stamp - last) / 1000, 1 / 30);
  last = stamp;
  time += dt;
  const scene = list[index];
  const live = pointerAt > 0 && stamp - pointerAt < 2500;
  if (live && !explore && pointerMoved) {
    const ray = rayAt(mouse.x, mouse.y, stage.camera).ray;
    sim.u.uRayO.value.copy(ray.origin);
    sim.u.uRayD.value.copy(ray.direction);
  }
  const strength = live && !explore ? scene.physics.mouse : 0;
  sim.u.uMouse.value += (strength - sim.u.uMouse.value) * (1 - Math.exp(-dt * 4));
  sim.m.uScale.value = stage.pixel;
  sim.m.uFocus.value = stage.camera.position.distanceTo(stage.look.value);
  sim.step(time, dt);
  if (explore) orbit.update();
  stage.update(time, dt, explore);
  scene.tick(dt, time);
  scene.place(stage.camera);
  hoverAge += dt;
  if (live && !chrome.open && (pointerMoved || hoverAge > 0.15)) {
    hoverAge = 0;
    const onCanvas = document.elementFromPoint(mouse.x, mouse.y) === canvas;
    const html = onCanvas ? scene.hover(mouse.x, mouse.y) : null;
    if (html) showTip(html, mouse.x, mouse.y);
    else hideTip();
    canvas.style.cursor = html ? "pointer" : explore ? "grab" : "default";
  }
  pointerMoved = false;
  if (touring && !chrome.open) {
    dwelt += dt;
    chrome.tourProgress(dwelt / scene.dwell);
    if (dwelt >= scene.dwell) {
      if (index < list.length - 1) go(index + 1);
      else setTour(false);
    }
  }
  stage.render();
  frames++;
  if (stamp - windowStart > 2500) {
    const fps = (frames * 1000) / (stamp - windowStart);
    slow = fps < 38 ? slow + 1 : 0;
    if (slow >= 2 && fixedQuality === null && stage.quality > 0) {
      stage.setQuality(stage.quality - 1);
      slow = 0;
    }
    (window as unknown as { __fiam: object }).__fiam = { fps: Math.round(fps), quality: stage.quality, scene: index };
    frames = 0;
    windowStart = stamp;
  }
  requestAnimationFrame(loop);
}

const start = Number(location.hash.slice(1));
go(Number.isInteger(start) && start >= 0 && start < list.length ? start : 0);
if (params.has("tour")) setTour(true);
loop();
