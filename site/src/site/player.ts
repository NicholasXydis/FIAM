// The film over the landing: one video at a time, its sound its own.
import vtt from "@/content/captions.vtt?raw";
import files from "@/content/media.json";
import { FILM, GATHER, type Gather } from "./ui/press";

// Where the copies live: R2 once live, the local /media while building.
const MEDIA = (import.meta.env["VITE_MEDIA"] as string | undefined) ?? "/media";
// Where a visitor's captions choice is kept between visits.
const KEPT = "film:captions";
// How long the dust takes to gather into the light before the film.
const GATHER_MS = 1000;

// The shapes: wide 16:9, tall 9:16, side 2.17:1 for sideways phones.
type Shape = "wide" | "tall" | "side";
// Each shape's width over its height.
const RATIO: Record<Shape, number> = { wide: 16 / 9, tall: 9 / 16, side: 2340 / 1080 };
// The parts of the player, found in the markup the page rendered.
interface Parts {
  root: HTMLElement;
  videos: [HTMLVideoElement, HTMLVideoElement];
  fill: HTMLCanvasElement;
  tiny: HTMLCanvasElement;
  caption: HTMLElement;
}

// A WebVTT time such as 00:01:02.345 in seconds.
function secs(time: string) {
  return time.split(":").reduce((n, part) => n * 60 + Number(part), 0);
}
// Each caption's start and end in film seconds, and its words.
const CUES = [...vtt.matchAll(/([\d:.]+) --> ([\d:.]+)\n(.+)/g)].map((m) => ({
  start: secs(m[1] ?? ""),
  end: secs(m[2] ?? ""),
  text: m[3] ?? "",
}));

// The player's parts, null until it mounts.
let parts: Parts | null = null;
// Whether the sky holds the film's light.
let gathered = false;
// The wait before the film starts, while the dust gathers.
let gatherTimer = 0;
// Whether the film is open.
let on = false;
// Whether the viewer wants it playing, not paused.
let want = false;
// The shape of the copy now in use.
let shape: Shape = "wide";
// Whether the smaller lite copies are in use.
let lite = false;
// Whether captions are on.
let cc = false;
// The video showing now; the other is free for a change of copy.
let live: HTMLVideoElement | null = null;
// Each change of copy has a number, so a newer one cancels the old.
let changing = 0;
// Whether a turn holds the film.
let turning = false;
// The timer that waits for a turn to settle.
let settle = 0;
// Whether the other way up has been made ready.
let warm = false;
// When the film opened, to spot a slow start.
let opened = 0;
// Whether the film has begun to play.
let started = false;
// When the current turn began, for the loading ring.
let turnFrom = 0;
// Time spent in counted waits mid film; too much means lite.
let waited = 0;
// How many counted waits there have been.
let waits = 0;
// When the current wait began, 0 when not waiting.
let waitFrom = 0;
// Since when the film has played smoothly, -1 in a counted wait.
let smoothSince = 0;
// When it last jumped; a wait soon after a jump is not a stall.
let jumped = 0;
// A change of copy wanted while the iPhone's player has the film.
let later = false;
// The copy a change is loading, so a newer change can stop it.
let loading: HTMLVideoElement | null = null;
// The next frame's request, kept to cancel it.
let raf = 0;
// The timer that hides the controls when still.
let idle = 0;
// Whether the blurred fill shows in the strips.
let fillOn = false;
// When the fill was last painted.
let painted = 0;
// The caption on screen now.
let said = "";
// What had focus before the film opened, to give it back.
let opener: HTMLElement | null = null;
// Whether the iPhone's own player has the film.
let native = false;
// When full screen last ended, so its Escape is not also Back.
let leftFull = 0;
// Those who want to know when full screen starts and ends.
const watchers = new Set<(full: boolean) => void>();

// The document with the prefixed full screen calls Safari uses.
type Doc = Document & {
  webkitFullscreenEnabled?: boolean;
  webkitFullscreenElement?: Element | null;
  webkitExitFullscreen?: () => void;
};
// An element with Safari's prefixed full screen call.
type Box = HTMLElement & { webkitRequestFullscreen?: () => void };
// A video with the iPhone's own full screen player calls.
type Native = HTMLVideoElement & { webkitEnterFullscreen?: () => void; webkitExitFullscreen?: () => void };
// The document, typed with Safari's prefixed calls.
const doc = () => document as Doc;
// The element now full screen, if any.
const fullElement = () => doc().fullscreenElement ?? doc().webkitFullscreenElement ?? null;

// The shape nearest a screen's: upright gets tall, past 1.96 side.
const shapeOf = (ratio: number): Shape => (ratio <= 1 ? "tall" : ratio >= 1.96 ? "side" : "wide");
// The shape nearest this screen now.
const current = () => shapeOf(innerWidth / innerHeight);
// Upright as a query, which says when a screen turns.
const upright = () => matchMedia("(max-aspect-ratio: 1/1)");
// Past 1.96 wide as a query, for the same reason.
const long = () => matchMedia("(min-aspect-ratio: 49/25)");
// A file's fingerprinted name from the list pnpm media web writes.
const named = (key: string) => String((files as Record<string, unknown>)[key] ?? "");
// A copy's full address, the lite one when small.
const source = (s: Shape, small: boolean) => new URL(`${MEDIA}/${named(small ? `${s}-lite` : s)}`, location.href).href;
// The poster of a shape's first light.
const poster = (s: Shape) => `/film/${named(`poster-${s}`)}`;
// A promise's failure that needs no answer.
const quiet = () => undefined;
// The video that is not showing.
const spare = (videos: Parts["videos"]) => (live === videos[0] ? videos[1] : videos[0]);

// A slow or metered connection starts on the lite copies.
function slow() {
  const c = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  return c?.saveData === true || /2g|3g/.test(c?.effectiveType ?? "");
}

// Whether the screen's shape leaves strips, which the blur then fills.
function fit() {
  if (!parts) return;
  const r = RATIO[shape];
  fillOn = Math.abs(Math.log(innerWidth / innerHeight / r)) > 0.02;
  // A few pixels across the long side, and four times that for the fill.
  const [w, h] = r > 1 ? [12, Math.round(12 / r)] : [Math.round(12 * r), 12];
  [parts.tiny.width, parts.tiny.height] = [w, h];
  [parts.fill.width, parts.fill.height] = [w * 4, h * 4];
  parts.fill.style.visibility = fillOn ? "visible" : "hidden";
}

// The fill: the picture shrunk to a few pixels, then smoothly enlarged.
function paint(v: HTMLVideoElement) {
  if (!parts) return;
  const { tiny, fill } = parts;
  tiny.getContext("2d")?.drawImage(v, 0, 0, tiny.width, tiny.height);
  const ctx = fill.getContext("2d");
  if (!ctx) return;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(tiny, 0, 0, fill.width, fill.height);
}

// Shows the controls, then hides them after 2.5 s of stillness.
function wake() {
  if (!parts) return;
  parts.root.removeAttribute("data-idle");
  clearTimeout(idle);
  idle = window.setTimeout(() => want && parts?.root.setAttribute("data-idle", ""), 2500);
}

// Plays or pauses; a pause keeps the controls and the Play button up.
function playing(next: boolean) {
  want = next;
  parts?.root.toggleAttribute("data-paused", !next);
  wake();
  if (!on || !live) return;
  if (next) live.play().catch(blocked);
  else live.pause();
}

// Sound refused without a press: the film waits for Play instead.
function blocked(e: unknown) {
  if (e instanceof DOMException && e.name === "NotAllowedError") playing(false);
}

// The caption at the film's time, or none.
function caption(t: number) {
  if (!parts) return;
  const text = cc ? (CUES.find((c) => t >= c.start && t < c.end)?.text ?? "") : "";
  if (text === said) return;
  said = text;
  parts.caption.firstElementChild!.textContent = text;
  parts.caption.style.visibility = text ? "visible" : "hidden";
}

// A light pass each frame: the caption, and the fill now and then.
function tick(t: number) {
  if (!on || !live) return;
  if (!warm && !turning && live.currentTime > 2) prewarm();
  started ||= live.currentTime > 0.05;
  // Not begun after 4 s, the connection is slow: the lite copies.
  if (!started && want && !lite && !turning && !native && t - opened > 4000) {
    lite = true;
    swap();
  }
  // The ring, for any wait over 1.2 s: to begin, to turn, mid film.
  const slowStart = !started && want && t - opened > 1200;
  const slowTurn = turning && t - turnFrom > 1200;
  const slowFilm = waitFrom > 0 && t - waitFrom > 1200;
  parts?.root.toggleAttribute("data-loading", slowStart || slowTurn || slowFilm);
  // Repaint the fill at most every 150 ms, once there is a frame.
  if (fillOn && t - painted > 150 && live.readyState >= 2) {
    painted = t;
    paint(live);
  }
  caption(live.currentTime);
  raf = requestAnimationFrame(tick);
}

// Lets go of a copy, so nothing keeps loading.
function release(v: HTMLVideoElement) {
  v.pause();
  v.classList.remove("is-on");
  v.removeAttribute("src");
  v.load();
}

// Close to the end the end card fits any shape, so nothing changes.
const late = () => !!live && live.duration - live.currentTime < 1.5;

// The picture dips to black and the film holds, as a turn begins.
function dip() {
  if (!parts || !live || turning) return;
  turning = true;
  turnFrom = performance.now();
  parts.root.setAttribute("data-turning", "");
  live.pause();
}

// The picture comes back and the film goes on, if it was playing.
function rise(mine: number) {
  if (!parts || !live || mine !== changing) return;
  turning = false;
  parts.root.removeAttribute("data-turning");
  if (want) live.play().catch(blocked);
}

// Changes copy at the same frame, held in black until it can show.
function swap() {
  if (!parts || !on || !live) return;
  // The iPhone's player cannot change copy; it waits until it is left.
  if (native) return void (later = true);
  const mine = ++changing;
  const from = live;
  const next = source(shape, lite);
  fit();
  smoothSince = 0;
  // Turned back before it arrived: the copy loading for nothing stops.
  if (from.src === next) {
    if (loading) release(loading);
    loading = null;
    return rise(mine);
  }
  dip();
  const to = spare(parts.videos);
  loading = to;
  const t = from.currentTime;
  to.preload = "auto";
  to.muted = false;
  if (to.src !== next) to.src = next;
  // A play and pause starts the loading even where a pause would not.
  to.play().catch(quiet);
  to.pause();
  // Jump the new copy to the old one's time, unless overtaken.
  const seek = () => mine === changing && (to.currentTime = t);
  if (to.readyState >= 1) seek();
  else to.addEventListener("loadedmetadata", seek, { once: true });
  // Waits for that frame, then shows it and lets the old copy go.
  const arrive = () => {
    if (mine !== changing || !on) return;
    // Not on that frame yet, so look again next frame.
    if (to.seeking || to.readyState < 2 || Math.abs(to.currentTime - t) > 0.1) {
      return void requestAnimationFrame(arrive);
    }
    to.classList.add("is-on");
    live = to;
    loading = null;
    release(from);
    warm = false;
    // The screen turned again meanwhile: on to the shape it is now.
    if (current() !== shape) {
      shape = current();
      return swap();
    }
    rise(mine);
  };
  requestAnimationFrame(arrive);
}

// On a phone, the other way up is made ready: only its index loads.
function prewarm() {
  warm = true;
  if (!parts || !live || !matchMedia("(pointer: coarse)").matches) return;
  const other = shapeOf(innerHeight / innerWidth);
  const s = spare(parts.videos);
  const next = source(other, lite);
  if (other === shape || s.src === next) return;
  s.preload = "metadata";
  s.src = next;
}

// Waiting mid film is timed; over 3 s or 3 waits, the lite copies.
function stall(e: Event) {
  const v = e.target as HTMLVideoElement;
  if (v !== live || !on) return;
  const now = performance.now();
  // A jump resets the smooth play clock; it is not a wait.
  if (e.type === "seeking") {
    jumped = now;
    smoothSince = 0;
    return;
  }
  // A wait counts only after 2 s of smooth play with no jump or turn.
  const fair = started && smoothSince > 0 && now - smoothSince > 2000 && now - jumped > 2000;
  // A wait begins; it counts only if play was smooth before.
  if (e.type === "waiting") {
    waitFrom = now;
    if (fair) waits++;
    smoothSince = fair ? -1 : 0;
    return;
  }
  // Playing again: a counted wait adds its length; smooth play begins.
  if (waitFrom && smoothSince === -1) waited += now - waitFrom;
  waitFrom = 0;
  smoothSince = now;
  // Over 3 s or 3 waits in all, change to the lite copies.
  if (!lite && (waited > 3000 || waits >= 3)) {
    lite = true;
    swap();
  }
}

// The rest of the page, inert while the film covers it.
function behind(inert: boolean) {
  // Every sibling of the film goes inert, or comes back.
  for (const el of parts?.root.parentElement?.children ?? []) {
    if (el !== parts?.root) (el as HTMLElement).inert = inert;
  }
}

// In the press itself: picks the copy and lets both videos play later.
export function prime() {
  if (!parts) return;
  const [a, b] = parts.videos;
  shape = current();
  lite = slow();
  live = a;
  a.muted = false;
  a.poster = poster(shape);
  a.preload = "auto";
  a.src = source(shape, lite);
  a.classList.add("is-on");
  b.muted = true;
  b.src = a.src;
  // A play begun in the press lets each play later, sound and all.
  for (const v of [a, b]) {
    v.play().catch(quiet);
    v.pause();
  }
  release(b);
}

// Where the film's first light falls on this screen, and how wide.
function firstLight(): Gather {
  const r = RATIO[shape];
  const [w, h] = innerWidth / innerHeight > r ? [innerHeight * r, innerHeight] : [innerWidth, innerWidth / r];
  const [fx = 0.5, fy = 0.44] = (files.lights as Record<Shape, number[]>)[shape];
  // The light's core is 13 px across a 1080 px short side.
  return { x: (innerWidth - w) / 2 + fx * w, y: (innerHeight - h) / 2 + fy * h, r: (13 / 1080) * Math.min(w, h) };
}

// Runs once the player itself has faded, or soon after if it cannot.
function afterFade(then: () => void) {
  if (!parts) return then();
  const root = parts.root;
  let done = false;
  // Runs then just once, from whichever comes first.
  const once = () => {
    if (done) return;
    done = true;
    root.removeEventListener("transitionend", own);
    then();
  };
  // The player's own opacity fade has ended.
  const own = (e: Event) => e.target === root && (e as TransitionEvent).propertyName === "opacity" && once();
  root.addEventListener("transitionend", own);
  setTimeout(once, 900);
}

// Opens the film: the dust gathers into its first light, then it plays.
export function open() {
  if (!parts || on) return;
  opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  on = true;
  turning = warm = started = false;
  waited = waits = waitFrom = smoothSince = jumped = 0;
  later = false;
  loading = null;
  history.pushState({ film: true }, "", "#film");
  behind(true);
  parts.root.focus({ preventScroll: true });
  // With the particle sky and motion, the page gives way to the light.
  const root = document.documentElement;
  const sky = root.hasAttribute("data-lit") && !matchMedia("(prefers-reduced-motion: reduce)").matches;
  // With the sky, gather the dust into the film's first light.
  if (sky) {
    gathered = true;
    root.setAttribute("data-gather", "");
    dispatchEvent(new CustomEvent<Gather>(GATHER, { detail: firstLight() }));
  }
  gatherTimer = window.setTimeout(show, sky ? GATHER_MS : 0);
}

// The film fades in over its light, and plays from the start.
function show() {
  if (!parts || !on) return;
  opened = performance.now();
  fit();
  const root = document.documentElement;
  root.setAttribute("data-film", "");
  requestAnimationFrame(() => on && root.setAttribute("data-film", "on"));
  // Once it covers the page, the page beneath rests and stops drawing.
  afterFade(() => {
    if (!on) return;
    root.setAttribute("data-film", "full");
    dispatchEvent(new CustomEvent(FILM, { detail: true }));
  });
  playing(true);
  raf = requestAnimationFrame(tick);
}

// Takes the film away and gives the page back, at once or fading.
function close(instant = false) {
  if (!parts || !on) return;
  unfull();
  on = false;
  want = false;
  changing++;
  turning = false;
  clearTimeout(settle);
  parts.root.removeAttribute("data-turning");
  parts.root.removeAttribute("data-loading");
  cancelAnimationFrame(raf);
  clearTimeout(gatherTimer);
  for (const v of parts.videos) release(v);
  live = null;
  const root = document.documentElement;
  const shown = root.hasAttribute("data-film");
  // The film fades off its light; then the light bursts into the name.
  const done = () => {
    if (on) return;
    root.removeAttribute("data-film");
    if (!gathered) return;
    gathered = false;
    root.removeAttribute("data-gather");
    dispatchEvent(new CustomEvent<Gather>(GATHER, { detail: instant ? "now" : "back" }));
  };
  // The sky wakes first, still holding the light, under the fading film.
  dispatchEvent(new CustomEvent(FILM, { detail: false }));
  if (shown) root.setAttribute("data-film", "");
  if (instant || !shown || matchMedia("(prefers-reduced-motion: reduce)").matches) done();
  else afterFade(done);
  behind(false);
  opener?.focus({ preventScroll: true });
}

// Back: the step before, which is the landing without the film.
export function back() {
  if ((history.state as { film?: boolean } | null)?.film) history.back();
  else close();
}

// On to the tour, in place of the film in the history.
export function skip() {
  playing(false);
  location.replace("/tour/");
}

// Pauses or plays again.
export const toggle = () => playing(!want);

// Turns the captions on or off, kept for the next visit.
export function captions(next: boolean) {
  cc = next;
  // Storage may be blocked, so saving can throw.
  try {
    localStorage.setItem(KEPT, next ? "on" : "off");
  } catch {
    // Without storage the choice lasts until the page closes.
  }
  if (live) caption(live.currentTime);
  return next;
}

// The captions choice from an earlier visit, off by default.
export function kept() {
  // Storage may be blocked, so reading can throw.
  try {
    return localStorage.getItem(KEPT) === "on";
  } catch {
    return false;
  }
}

// How this device goes full screen: the player, the iPhone's, or not.
export function fullWay(): "player" | "video" | null {
  if (document.fullscreenEnabled || doc().webkitFullscreenEnabled) return "player";
  return parts && typeof (parts.videos[0] as Native).webkitEnterFullscreen === "function" ? "video" : null;
}

// Tells the watchers whether the film is full screen now.
function told() {
  const full = native || fullElement() !== null;
  if (!full) leftFull = performance.now();
  for (const watch of watchers) watch(full);
}

// Says when full screen starts and ends; returns the way to stop.
export function watchFull(watch: (full: boolean) => void) {
  watchers.add(watch);
  return () => void watchers.delete(watch);
}

// Leaves full screen, if the film is.
function unfull() {
  if (!fullElement()) return;
  if (document.exitFullscreen) document.exitFullscreen().catch(quiet);
  else doc().webkitExitFullscreen?.();
}

// In the press: full screen on, or off; the iPhone gets its own player.
export function full() {
  if (!parts || !live || !on) return;
  if (fullElement()) return unfull();
  const box = parts.root as Box;
  // Most browsers put the whole player full screen.
  if (fullWay() === "player") {
    if (box.requestFullscreen) box.requestFullscreen({ navigationUI: "hide" }).catch(quiet);
    else box.webkitRequestFullscreen?.();
    return;
  }
  const v = live as Native;
  if (!v.webkitEnterFullscreen) return;
  // Its captions, if on, show in the iPhone's player too.
  const track = v.textTracks[0];
  if (track) track.mode = cc ? "showing" : "disabled";
  v.webkitEnterFullscreen();
}

// The iPhone's player came and went; back inline, the film plays on.
function nativeFull(e: Event) {
  native = e.type === "webkitbeginfullscreen";
  told();
  if (native) return;
  const v = e.target as HTMLVideoElement;
  const track = v.textTracks[0];
  if (track) track.mode = "disabled";
  if (!on || v !== live) return;
  // Same shape and no change waiting: play on if it should.
  if (shape === current() && !later) {
    if (want && v.paused) v.play().catch(() => playing(false));
    return;
  }
  later = false;
  shape = current();
  swap();
}

// A phone turned sideways: the controls show, Full screen glows once.
function beckon() {
  if (!parts || !matchMedia("(pointer: coarse)").matches || shape === "tall") return;
  if (native || fullElement() || !fullWay()) return;
  wake();
  const pill = parts.root.querySelector(".film-full");
  pill?.classList.remove("is-beckon");
  void (pill as HTMLElement | null)?.offsetWidth;
  pill?.classList.add("is-beckon");
}

// Opens the connection to the copies' host early; nothing loads yet.
function reach() {
  if (!/^https?:/.test(MEDIA)) return;
  const origin = new URL(MEDIA).origin;
  if (document.querySelector(`link[rel="preconnect"][href="${origin}"]`)) return;
  document.head.append(Object.assign(document.createElement("link"), { rel: "preconnect", href: origin }));
}

// Finds the player's parts and listens; returns the way to stop.
export function mount(root: HTMLElement) {
  const [a, b] = root.querySelectorAll("video");
  parts = {
    root,
    videos: [a!, b!],
    fill: root.querySelector<HTMLCanvasElement>(".film-fill")!,
    tiny: document.createElement("canvas"),
    caption: root.querySelector<HTMLElement>(".film-caption")!,
  };
  cc = kept();
  reach();
  // Each video carries the captions too, for the iPhone's own player.
  const captionsFile = URL.createObjectURL(new Blob([vtt], { type: "text/vtt" }));
  // Add the captions track to each video, hidden for now.
  for (const v of parts.videos) {
    const track = Object.assign(document.createElement("track"), {
      kind: "captions",
      srclang: "en",
      label: "English",
      src: captionsFile,
    });
    v.append(track);
    track.track.mode = "disabled";
  }
  // A page opened at #film shows the landing, since sound needs a press.
  if (location.hash === "#film") history.replaceState(null, "", location.pathname + location.search);
  let touch = false;
  // A tap on the picture shows the controls, or pauses once they show.
  const tap = (e: Event) => {
    if ((e.target as Element).closest(".pill")) return;
    if (touch && root.hasAttribute("data-idle")) wake();
    else toggle();
  };
  // Escape is Back; the space bar pauses, unless a control has focus.
  const key = (e: Event) => {
    if (!on) return;
    wake();
    const { key: name, target } = e as KeyboardEvent;
    if (name === "Escape" && !fullElement() && performance.now() - leftFull > 400) back();
    if (name !== " " || (target as Element).closest("a, button")) return;
    e.preventDefault();
    toggle();
  };
  // A turn: the film holds at once, and changes once the turn settles.
  const turned = () => {
    if (!on) return;
    // The iPhone's player cannot change copy, so it closes; then it does.
    if (native) return void (shape !== current() && (live as Native | null)?.webkitExitFullscreen?.());
    if (late()) return;
    if (shape !== current()) dip();
    clearTimeout(settle);
    settle = window.setTimeout(settled, 250);
  };
  // Settled: the copy for the shape the screen ended on, and the nudge.
  const settled = () => {
    if (!on || native) return;
    const was = shape;
    shape = current();
    swap();
    if (was === "tall" && shape !== "tall") beckon();
  };
  // The showing copy's end goes on to the tour.
  const ended = (e: Event) => e.target === live && on && skip();
  // A failed copy tries the lite one, then goes on to the tour.
  const failed = (e: Event) => {
    if (!on || e.target !== live) return;
    if (lite) return skip();
    lite = true;
    swap();
  };
  // Every event the player listens to, and what answers it.
  const handlers: [EventTarget, string, (e: Event) => void][] = [
    [window, "popstate", () => on && !(history.state as { film?: boolean } | null)?.film && close()],
    [window, "pageshow", (e) => (e as PageTransitionEvent).persisted && close(true)],
    [window, "resize", fit],
    ...[upright(), long()].map((q): [EventTarget, string, (e: Event) => void] => [q, "change", turned]),
    [document, "fullscreenchange", told],
    [document, "webkitfullscreenchange", told],
    [document, "visibilitychange", () => on && document.hidden && playing(false)],
    [root, "pointermove", (e) => (e as PointerEvent).pointerType === "mouse" && wake()],
    [root, "pointerdown", (e) => (touch = (e as PointerEvent).pointerType !== "mouse")],
    [root, "click", tap],
    [document, "keydown", key],
    ...parts.videos.flatMap((v): [EventTarget, string, (e: Event) => void][] => [
      [v, "ended", ended],
      [v, "error", failed],
      [v, "waiting", stall],
      [v, "playing", stall],
      [v, "seeking", stall],
      [v, "webkitbeginfullscreen", nativeFull],
      [v, "webkitendfullscreen", nativeFull],
    ]),
  ];
  for (const [target, type, handler] of handlers) target.addEventListener(type, handler);
  // Stopping closes the film and unwires every listener.
  return () => {
    close(true);
    for (const [target, type, handler] of handlers) target.removeEventListener(type, handler);
    URL.revokeObjectURL(captionsFile);
    parts = null;
  };
}
