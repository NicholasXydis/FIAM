import { useEffect, useRef } from "react";
import { type Ring, startSky } from "../sky/engine";
import { cameFrom } from "./back";
import { ATTRACT, FILM, GATHER, type Gather, LEAVE } from "./press";

// How a page's sky opens: the landing's name, or dust everywhere else.
export type Opening = "name" | "dust";

// The sky a page drives once it is laid out.
type Sky = NonNullable<ReturnType<typeof startSky>>;

// Where the landing leaves its name and a picture of it, for the next.
const HANDOFF = "sky:name";
const PICTURE = "sky:frame";

// The name's box as the landing left it, on a screen of the same size.
function handed() {
  try {
    const box = JSON.parse(sessionStorage.getItem(HANDOFF) ?? "null") as Record<string, number> | null;
    if (!box || box["vw"] !== innerWidth || box["vh"] !== innerHeight) return null;
    return new DOMRect(box["x"], box["y"], box["w"], box["h"]);
  } catch {
    return null;
  }
}

// The sky at half size as a JPEG, small enough to keep for one page.
function picture(canvas: HTMLCanvasElement) {
  const small = document.createElement("canvas");
  small.width = Math.round(innerWidth / 2);
  small.height = Math.round(innerHeight / 2);
  small.getContext("2d")?.drawImage(canvas, 0, 0, small.width, small.height);
  return small.toDataURL("image/jpeg", 0.8);
}

// Remembers where the landing's name is and how it looked, as it goes.
function handOff(box: DOMRect, canvas: HTMLCanvasElement | null) {
  const at = { x: box.x, y: box.y, w: box.width, h: box.height, vw: innerWidth, vh: innerHeight };
  try {
    sessionStorage.setItem(HANDOFF, JSON.stringify(at));
    if (canvas) sessionStorage.setItem(PICTURE, picture(canvas));
  } catch {
    // Without storage the next page simply opens on settled dust.
  }
}

// Forgets the hand-off once used, so a reload does not replay it.
function forget() {
  try {
    sessionStorage.removeItem(HANDOFF);
    sessionStorage.removeItem(PICTURE);
  } catch {
    // Nothing was kept, so nothing needs forgetting.
  }
}

// Without the particles: the name's text back, the kept picture gone.
function plain() {
  document.documentElement.removeAttribute("data-lit");
  document.documentElement.removeAttribute("data-carry");
}

// The sky, or null when WebGL2 is missing or fails to start.
function begin(canvas: HTMLCanvasElement) {
  try {
    return startSky(canvas, { stage });
  } catch {
    return null;
  }
}

// The box the name fills: the landing's own, or the one it handed on.
function stage() {
  const el = document.querySelector("[data-stage]");
  return el ? el.getBoundingClientRect() : (handed() ?? new DOMRect(0, 0, innerWidth, innerHeight * 0.72));
}

// How this page was reached: a link, a reload, or Back and Forward.
const arrival = () =>
  (performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined)?.type ?? "navigate";
// Whether this load is a step through history, Back or Forward.
const stepped = () => arrival() === "back_forward";

// Dust that gathers into the name: the way back to the landing.
const gather = (sky: Sky) => {
  sky.shape("dust", true);
  requestAnimationFrame(() => sky.shape("name"));
};

// The landing's name, picked up where it was left, breaking into dust.
const carry = (sky: Sky) => {
  sky.shape("name", true);
  forget();
  // The live name is drawn by now, so the kept picture can go.
  requestAnimationFrame(() => {
    sky.scatter();
    document.documentElement.removeAttribute("data-carry");
  });
};

// Coming back, dust gathers into the name; first, it rises; else dust.
function open(sky: Sky, opening: Opening) {
  const from = cameFrom();
  if (opening === "dust") {
    if (from === "/" && arrival() === "navigate" && handed()) return carry(sky);
    sky.shape("dust", true);
    document.documentElement.removeAttribute("data-carry");
  } else if (stepped() || (from !== null && from !== "/")) gather(sky);
  else sky.shape("name");
}

// The night behind every page: clouds, the particle sky, grain.
export function Sky({ opening }: { opening: Opening }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const el = canvas.current;
    const sky = el && begin(el);
    // The head hid the name's text; without particles it comes back.
    if (!el || !sky) return void plain();
    void sky.ready.then(() => open(sky, opening));
    // A lost GPU context stops the sky and gives the text back.
    const lost = () => (sky.stop(), plain());
    el.addEventListener("webglcontextlost", lost);
    // Restored by Back from the browser's cache, the landing gathers again.
    const restored = (e: PageTransitionEvent) => e.persisted && opening === "name" && gather(sky);
    // Leaving the landing: the team page carries the name on, the tour not.
    const leave = (e: Event) => {
      if (opening !== "name") return;
      const to = String((e as CustomEvent).detail);
      handOff(stage(), to.startsWith("/team") ? sky.frame() : null);
      if (to.startsWith("/tour")) sky.scatter();
    };
    // A hovered control draws the dust round itself.
    const pull = (e: Event) => sky.attract((e as CustomEvent<Ring | null>).detail);
    // Under the film the sky rests, sparing the frames for the picture.
    const covered = (e: Event) => sky.rest((e as CustomEvent<boolean>).detail);
    // The film's first light: the dust gathers to it, then bursts back.
    const light = (e: Event) => {
      const at = (e as CustomEvent<Gather>).detail;
      if (typeof at === "object") sky.gather(at.x, at.y, at.r);
      else sky.release(at === "now");
    };
    addEventListener("pageshow", restored);
    addEventListener(LEAVE, leave);
    addEventListener(ATTRACT, pull);
    addEventListener(FILM, covered);
    addEventListener(GATHER, light);
    return () => {
      el.removeEventListener("webglcontextlost", lost);
      removeEventListener("pageshow", restored);
      removeEventListener(LEAVE, leave);
      removeEventListener(ATTRACT, pull);
      removeEventListener(FILM, covered);
      removeEventListener(GATHER, light);
      sky.stop();
    };
  }, [opening]);
  return (
    <div aria-hidden="true" className="sky">
      <div className="sky-nebula" />
      {opening === "name" && <div className="sky-aura" />}
      <canvas ref={canvas} className="sky-canvas" />
      <div className="sky-carry" />
      <div className="sky-vignette" />
      <div className="sky-grain" />
    </div>
  );
}
