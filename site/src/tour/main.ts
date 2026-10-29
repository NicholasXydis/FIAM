import "./style.css";
import * as THREE from "three";
import { Chrome } from "./chrome";
import { Sim } from "./gl/sim";
import { Stage } from "./gl/stage";
import { scenes } from "./scenes";
import type { Scene, World } from "./scenes/scene";
import { Sound } from "./sound";
import { h } from "../shared/dom";
import { frame as fitView, setMode, stale, tick as layoutTick, titles } from "./layout";
import { hideTip, rayAt, showTip, tip } from "./ui";

// ?present hides hints and help, ?tour plays, ?q fixes the quality.
const params = new URLSearchParams(location.search);
// The WebGL canvas, one image to screen readers, named for the tour.
const canvas = h("canvas", {
  id: "gl",
  role: "img",
  "aria-label": "QUARCC Purple FIAM, an animated tour of the final book",
});
// The page layer over the canvas for the chrome, panels and labels.
const layer = h("div", { class: "ui" });
document.body.append(canvas, layer);
if (params.has("present")) document.body.classList.add("present");

// What the note says when the tour cannot start.
const CANNOT =
  "This screen cannot run the 3D tour. Open this page in a recent Chrome, Edge, Safari or Firefox with hardware acceleration on.";
// What the note says when the tour stops midway.
const STOPPED = "The 3D tour stopped. Reload the page to start it again.";

// Says so in plain words instead of a blank page; the reason is logged.
function fail(words: string, reason: string): never {
  layer.append(
    h(
      "div",
      { class: "absolute inset-0 grid place-items-center p-6 text-center" },
      h(
        "div",
        { class: "glass rounded-2xl p-6 max-w-md flex flex-col gap-3" },
        h("p", { class: "headline text-[32px]" }, "QUARCC Purple · FIAM"),
        h("p", { class: "body" }, words),
      ),
    ),
  );
  throw new Error(reason);
}

// The renderer and the particles; either failing shows the note.
let stage: Stage;
let sim: Sim;
// Build both; an error here means this screen cannot run it.
try {
  stage = new Stage(canvas);
  sim = new Sim(stage.renderer);
} catch (error) {
  fail(CANNOT, error instanceof Error ? error.message : "WebGL is unavailable");
}
stage.scene.add(sim.points);
// A lost graphics context ends the tour with a note to reload.
canvas.addEventListener("webglcontextlost", (e) => {
  e.preventDefault();
  fail(STOPPED, "the graphics context was lost");
});

// The intro draws its titles in these faces, so load them before it.
await document.fonts.load("italic 100px 'Instrument Serif'");
await document.fonts.load("600 100px 'Geist'");
await document.fonts.ready;

// Shared sound, silent until the viewer turns it on.
const sound = new Sound();
// The scene shown, -1 before the first.
let index = -1;
// Whether the guided tour is playing.
let touring = false;
// Seconds spent on this scene during the tour.
let dwelt = 0;
// What scenes may use; their go and next end the tour like a key press.
const world: World = { stage, sim, layer, sound, go: (i) => go(i, true), next: () => go(index + 1, true) };
// Every scene in order, built once around the shared world.
const list: Scene[] = scenes(world);
// The header, dots and panels, wired to moves, the tour and sound.
const chrome = new Chrome(layer, list, {
  go: (i) => go(i, true),
  tour: () => setTour(!touring),
  sound: () => setSound(!sound.on),
});
layer.append(tip);
// The layout follows the window, titles shrink to one line if small.
setMode();
titles(list);
// On resize, refit the layout and the titles.
addEventListener("resize", () => {
  // A new layout reshapes the scene, as some pack tall screens apart.
  if (setMode() && index >= 0) sim.show(list[index]!.formation(), 0.6, 0.9);
  titles(list);
});
visualViewport?.addEventListener("resize", stale);

// Compiles all shaders now, for the frames' target, so no scene stalls.
stage.renderer.setRenderTarget(stage.composer.readBuffer);
stage.renderer.compile(stage.scene, stage.camera);
stage.renderer.setRenderTarget(null);

// Moves to scene i (clamped); a move by hand ends the guided tour.
function go(i: number, byHand = false) {
  const next = Math.max(0, Math.min(list.length - 1, i));
  if (byHand && touring) setTour(false);
  if (next === index) return;
  // Hides the old scene, the tooltip and any hovered or picked particle.
  const from = list[index];
  from?.hide();
  hideTip();
  sim.m.uHover.value = -1;
  sim.m.uSelect.value = -1;
  const scene = list[next];
  const first = index < 0;
  index = next;
  dwelt = 0;
  // Takes on the scene's physics, 30% of the flow under reduced motion.
  sim.u.uStiff.value = scene.physics.stiff;
  sim.u.uDamp.value = scene.physics.damp;
  sim.u.uFlow.value = scene.physics.flow * (stage.reduced ? 0.3 : 1);
  sim.u.uSpin.value = scene.physics.spin;
  // The first scene shown gathers over a slower 2.4 s stagger.
  sim.show(scene.formation(), first ? 2.4 : scene.stagger, scene.duration);
  // Leaving sends a whoosh and a ripple, stronger out of scene 0.
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

// Plays or stops the tour, dwell reset; playing at the end rewinds.
function setTour(on: boolean) {
  touring = on;
  dwelt = 0;
  chrome.setTour(on);
  chrome.tourProgress(0);
  if (on && index === list.length - 1) go(0);
}

// Switches the sound and the header button's icon together.
function setSound(on: boolean) {
  sound.toggle(on);
  chrome.setSound(on);
}

// The last digit pressed and when, for two-digit scene numbers.
let digit: { n: number; at: number } | null = null;

// Keys go to the scene first, then to scene moves, modes and panels.
addEventListener("keydown", (e) => {
  // Inputs keep their keys and a focused slider keeps its arrows.
  const target = e.target as HTMLElement;
  if (target instanceof HTMLInputElement && (target.type !== "range" || e.key.startsWith("Arrow"))) return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  // Space and Enter press a focused control; tiles act as buttons too.
  if ((key === " " || key === "Enter") && target.closest?.("button, a, [role=button]")) {
    if (target.getAttribute("role") === "button") (e.preventDefault(), target.click());
    return;
  }
  // An open panel lets only Escape, O, ?, H and the digits through.
  if (chrome.open && !["Escape", "o", "?", "h"].includes(key) && !/^[0-9]$/.test(key)) return;
  if (list[index]?.key(e)) return e.preventDefault();
  if (["ArrowRight", "ArrowDown", "PageDown", " "].includes(key)) go(index + 1, true);
  else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(key)) go(index - 1, true);
  else if (key === "Home") go(0, true);
  else if (key === "End") go(list.length - 1, true);
  else if (/^[0-9]$/.test(key)) {
    chrome.close();
    // A second digit within half a second makes a two-digit scene.
    const now = performance.now();
    const two = digit !== null && now - digit.at < 500 ? digit.n * 10 + +key : -1;
    digit = two >= 0 ? null : { n: +key, at: now };
    go(two >= 0 && two < list.length ? two : +key, true);
  } else if (key === "p") setTour(!touring);
  else if (key === "m") setSound(!sound.on);
  else if (key === "o") chrome.toggleOverview();
  else if (key === "?" || key === "h") chrome.toggleHelp();
  else if (key === "f") {
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
    else void document.documentElement.requestFullscreen().catch(() => {});
  } else if (key === "Escape") chrome.close();
  else return;
  e.preventDefault();
});

// Scrolling builds past 60 to turn one scene, then waits 1.1 s.
let wheelLock = 0;
// Scroll built up since the last turn.
let wheelSum = 0;
addEventListener(
  // The wheel turns scenes, but not while a sheet is open or over UI.
  "wheel",
  (e) => {
    if (chrome.open || (e.target as HTMLElement).closest?.(".card, .controls, .panel")) return;
    e.preventDefault();
    const now = performance.now();
    if (now < wheelLock) return;
    wheelSum += e.deltaY + e.deltaX;
    // Past 60 of scroll, turn one scene and lock for 1.1 s.
    if (Math.abs(wheelSum) > 60) {
      go(index + Math.sign(wheelSum), true);
      wheelSum = 0;
      wheelLock = now + 1100;
    }
  },
  { passive: false },
);

// A sideways touch flick that starts on a 3D label turns scenes too.
let flick: { x: number; y: number; t: number } | null = null;
// Note a touch press on a label; the canvas notes its own below.
layer.addEventListener("pointerdown", (e) => {
  const on = (e.target as Element).closest?.(".label3d");
  flick = on && e.pointerType !== "mouse" ? { x: e.clientX, y: e.clientY, t: performance.now() } : null;
});
// On release, a 60 px flick in 0.7 s moves; a tap stays the label's.
layer.addEventListener("pointerup", (e) => {
  if (!flick) return;
  const dx = e.clientX - flick.x;
  const dy = e.clientY - flick.y;
  const quick = performance.now() - flick.t < 700;
  flick = null;
  if (quick && Math.abs(dx) > 60 && Math.abs(dx) > 1.2 * Math.abs(dy)) go(index - Math.sign(dx), true);
});

// The timer that clears a tap's tooltip after a few seconds.
let tapTip = 0;
// Where and when the last press on the canvas began.
let press: { x: number; y: number; t: number } | null = null;
// Note each press, to tell a tap from a swipe on release.
canvas.addEventListener("pointerdown", (e) => {
  press = { x: e.clientX, y: e.clientY, t: performance.now() };
});
// A 60 px touch flick in 0.7 s turns scenes; a tap under 6 px clicks.
canvas.addEventListener("pointerup", (e) => {
  if (!press) return;
  const dx = e.clientX - press.x;
  const dy = e.clientY - press.y;
  // Only a mostly sideways flick turns, so a drag up or down never does.
  const flick = Math.abs(dx) > 60 && Math.abs(dx) > 1.2 * Math.abs(dy);
  const swipe = e.pointerType !== "mouse" && flick && performance.now() - press.t < 700;
  press = null;
  if (swipe) return go(index - Math.sign(dx), true);
  if (Math.hypot(dx, dy) > 6) return;
  // The tap ripples on its ray at the look point's depth, at least 4 out.
  const ray = rayAt(e.clientX, e.clientY, stage.camera).ray;
  const depth = Math.max(4, stage.look.value.clone().sub(ray.origin).dot(ray.direction));
  sim.wave({ at: ray.origin.clone().addScaledVector(ray.direction, depth), amp: 0.8, speed: 8 });
  sound.tick(0.75, 0.6);
  const html = list[index].hover(e.clientX, e.clientY);
  list[index].click(e.clientX, e.clientY);
  // A finger has no hover, so a tap shows the tip unless a card opened.
  if (e.pointerType !== "mouse" && html && !layer.querySelector("aside.card:not([hidden])")) {
    showTip(html.replaceAll("Click", "Tap").replaceAll("click", "tap"), e.clientX, e.clientY, true);
    clearTimeout(tapTip);
    tapTip = window.setTimeout(hideTip, 4500);
  }
});

// When the pointer last moved, 0 once it has left.
let pointerAt = 0;
// Whether it moved since the last frame.
let pointerMoved = false;
// Whether it is over the canvas, not the page layer.
let overCanvas = false;
// Where it is on screen, in pixels.
const mouse = { x: -1, y: -1 };
// Feeds hover, the particles' push and the camera's parallax.
addEventListener("pointermove", (e) => {
  mouse.x = e.clientX;
  mouse.y = e.clientY;
  pointerAt = performance.now();
  pointerMoved = true;
  overCanvas = e.target === canvas;
  stage.pointer.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
});
// Leaving the window counts as no pointer, so the push fades out.
document.documentElement.addEventListener("mouseleave", () => (pointerAt = 0));

// A dragged slider frees the arrows on release; a keyed one keeps them.
let dragged: EventTarget | null = null;
// Note what each press lands on.
addEventListener("pointerdown", (e) => {
  dragged = e.target;
  // A new tap clears the last tap's tooltip.
  if (e.pointerType !== "mouse") hideTip();
});
// A slider let go after a drag gives up focus.
addEventListener("change", (e) => {
  if (e.target instanceof HTMLInputElement && e.target.type === "range" && e.target === dragged) e.target.blur();
});

// ?q fixes the quality, or it starts at 1 to 760 px wide and 2 above.
const fixedQuality = params.get("q");
stage.setQuality(fixedQuality !== null ? +fixedQuality : matchMedia("(max-width: 760px)").matches ? 1 : 2);

// When the last frame ran.
let last = performance.now();
// The tour's clock in seconds.
let time = 0;
// The particles' and camera's clock, slowed to a tenth during a hover.
let calm = 0;
// Whether a hover tip is holding the pointer.
let holding = false;
// Frames counted in this window.
let frames = 0;
// Slow windows in a row.
let slow = 0;
// A step down in quality on trial, and the fps before it.
let trial: { from: number; fps: number } | null = null;
// Whether quality has settled for good.
let settled = false;
// When this frame rate window began.
let windowStart = last;
// Seconds since hover was last checked.
let hoverAge = 0;
// The scene the camera last fitted on small screens.
let fitted = -1;

// A frame of at most 1/30 s: sim, camera, scene, hover, tour, quality.
function loop() {
  const stamp = performance.now();
  const dt = Math.min((stamp - last) / 1000, 1 / 30);
  last = stamp;
  time += dt;
  calm += holding ? dt * 0.1 : dt;
  const scene = list[index];
  // The pointer counts for 2.5 s after it moves, or while it holds a tip.
  const live = pointerAt > 0 && (holding || stamp - pointerAt < 2500);
  // A moved pointer casts a fresh ray for the particles' push.
  if (live && pointerMoved) {
    const ray = rayAt(mouse.x, mouse.y, stage.camera).ray;
    sim.u.uRayO.value.copy(ray.origin);
    sim.u.uRayD.value.copy(ray.direction);
  }
  // The push eases to the scene's strength, or away while hovering.
  const strength = live && !holding ? scene.physics.mouse : 0;
  sim.u.uMouse.value += (strength - sim.u.uMouse.value) * (1 - Math.exp(-dt * 4));
  // Point scale and focus, then the particles, camera and scene step.
  sim.m.uScale.value = stage.pixel;
  sim.m.uFocus.value = stage.camera.position.distanceTo(stage.look.value);
  sim.step(time, dt, calm);
  layoutTick();
  fitView(stage, scene, index !== fitted);
  fitted = index;
  stage.update(calm, dt, holding);
  scene.tick(dt, time);
  scene.place(stage.camera);
  // Rechecks hover as the pointer moves, or every 0.15 s while it rests.
  hoverAge += dt;
  // Ask the scene what is under the pointer and show its tip.
  if (live && !chrome.open && (pointerMoved || hoverAge > 0.15)) {
    hoverAge = 0;
    const html = overCanvas ? scene.hover(mouse.x, mouse.y) : null;
    if (html) showTip(html, mouse.x, mouse.y);
    else hideTip();
    canvas.style.cursor = html ? "pointer" : "default";
    holding = html !== null;
  }
  // Nothing is held once the pointer leaves or a sheet opens; tip goes.
  if (holding && (!live || chrome.open || !overCanvas)) {
    holding = false;
    hideTip();
  }
  pointerMoved = false;
  // The tour moves on after each dwell, waiting while a panel is open.
  if (touring && !chrome.open) {
    dwelt += dt;
    chrome.tourProgress(dwelt / scene.dwell);
    // The dwell is up: next scene, or stop at the end.
    if (dwelt >= scene.dwell) {
      if (index < list.length - 1) go(index + 1);
      else setTour(false);
    }
  }
  stage.render();
  frames++;
  // Every 2.5 s the frame rate is measured and quality may step down.
  if (stamp - windowStart > 2500) {
    const fps = (frames * 1000) / (stamp - windowStart);
    // No 15% gain from a step down means a 30 Hz screen: step back, stay.
    if (trial && fps < trial.fps * 1.15) {
      stage.setQuality(trial.from);
      settled = true;
    }
    trial = null;
    // Two slow windows in a row (under 38 fps) try one level lower.
    slow = fps < 38 ? slow + 1 : 0;
    // Two slow windows step quality down one, if it may.
    if (slow >= 2 && !settled && fixedQuality === null && stage.quality > 0) {
      trial = { from: stage.quality, fps };
      stage.setQuality(stage.quality - 1);
      slow = 0;
    }
    // Exposed on window so a check can read fps, quality and scene.
    (window as unknown as { __fiam: object }).__fiam = { fps: Math.round(fps), quality: stage.quality, scene: index };
    frames = 0;
    windowStart = stamp;
  }
  requestAnimationFrame(loop);
}

// A link or a typed address to another scene moves there.
addEventListener("hashchange", () => {
  const n = /^#\d+$/.test(location.hash) ? Number(location.hash.slice(1)) : -1;
  if (n >= 0 && n < list.length) go(n, true);
});

// Opens on the address's scene, else the first; ?tour plays at once.
const start = Number(location.hash.slice(1));
go(Number.isInteger(start) && start >= 0 && start < list.length ? start : 0);
if (params.has("tour")) setTour(true);
loop();
