// How pills and faces answer the pointer; plain DOM, so the tour can.

// A press shows for a beat before the action, unless motion is reduced.
const PRESS_MS = 140;
// The event a pill sends as it takes the visitor to another page.
export const LEAVE = "site:leave";
// Sent by a hovered control, so the dust can swirl round it.
export const ATTRACT = "site:attract";
// Sent as the film covers the sky and leaves it, so the sky can rest.
export const FILM = "site:film";
// Sent as the film opens, the light to gather to, and as it goes.
export const GATHER = "site:gather";
// Where the dust gathers: a point and its size, or back to the name.
export type Gather = { x: number; y: number; r: number } | "back" | "now";

// Runs an action once the press has shown; says where it is going.
export function afterPress(action: () => void, to?: string) {
  if (to) dispatchEvent(new CustomEvent(LEAVE, { detail: to }));
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) action();
  else setTimeout(action, PRESS_MS);
}

// Floods the ink in from a point, out to its farthest corner.
function inkIn(ink: HTMLElement, x: number, y: number) {
  const r = ink.getBoundingClientRect();
  const px = x - r.left;
  const py = y - r.top;
  const reach = Math.hypot(Math.max(px, r.width - px), Math.max(py, r.height - py)) + 2;
  ink.style.transition = "none";
  ink.style.clipPath = `circle(0px at ${px}px ${py}px)`;
  void ink.offsetWidth;
  ink.style.transition = "";
  ink.style.clipPath = `circle(${reach}px at ${px}px ${py}px)`;
}

// Drains the ink back out toward the point where the pointer left.
function inkOut(ink: HTMLElement, x: number, y: number) {
  const r = ink.getBoundingClientRect();
  ink.style.clipPath = `circle(0px at ${x - r.left}px ${y - r.top}px)`;
}

// The middle of an element, for focus from the keyboard.
const middle = (el: Element): [number, number] => {
  const r = el.getBoundingClientRect();
  return [r.left + r.width / 2, r.top + r.height / 2];
};

// A pointer event's position on the screen.
const xy = (e: Event): [number, number] => [(e as PointerEvent).clientX, (e as PointerEvent).clientY];

// A ring of light that leaves the shape once, as it is reached.
const RIPPLE = [{ boxShadow: "0 0 0 0 rgb(244 241 250 / 0.35)" }, { boxShadow: "0 0 0 14px rgb(244 241 250 / 0)" }];

// One of the pill's eases, read from the stylesheet that defines it.
const ease = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "ease-out";

// After a cache restore, the old pointer's replayed hovers are stale.
let stale = false;
// Whether the restore watch has started yet.
let watching = false;

// Starts watching for restores, once, from the first control wired.
function watch() {
  if (watching) return;
  watching = true;
  addEventListener("pageshow", (e) => (stale ||= e.persisted));
  addEventListener("pointermove", () => (stale = false), { capture: true });
}

// Tells the sky where a hovered shape is, or that none is any more.
function attract(shape: HTMLElement | null) {
  const r = shape?.getBoundingClientRect();
  const ring = r && { x: r.left, y: r.top, w: r.width, h: r.height, r: Math.min(r.width, r.height) / 2 };
  dispatchEvent(new CustomEvent(ATTRACT, { detail: ring ?? null }));
}

// A plain click: not opened in a new tab, a new window or a download.
export const plain = (e: Pick<MouseEvent, "metaKey" | "ctrlKey" | "shiftKey" | "altKey" | "button">) =>
  !(e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0);

// Wires a pill once it is in the page, and unwires it when it goes.
export const wire = (el: HTMLElement | null) => (el ? wirePill(el) : undefined);

// Wires one pill or face to itself only; returns the way to unwire it.
export function wirePill(el: HTMLElement) {
  const ink = el.querySelector<HTMLElement>(".pill-ink");
  if (!ink) return () => undefined;
  watch();
  // The inked shape: the whole pill, or a person's circle.
  const shape = ink.parentElement ?? el;
  const tilts = el.matches(".pill-big, .person");
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  // Sets one of the pill's CSS variables.
  const set = (name: string, value: string) => el.style.setProperty(name, value);
  // A script animation, so a page's entrance animation never restarts.
  const ripple = () => shape.animate(RIPPLE, { duration: 800, easing: ease("--pill-glide") });
  // Lit while the pointer or focus is on it, flooded from where it came.
  const light = (x: number, y: number) => {
    inkIn(ink, x, y);
    el.classList.add("is-lit");
    if (still) return;
    attract(shape);
    ripple();
  };
  // Unlit: the ink drains toward the pointer and the shape rests.
  const dark = (x: number, y: number) => {
    inkOut(ink, x, y);
    el.classList.remove("is-lit", "is-pressing");
    for (const name of ["--tx", "--ty", "--rx", "--ry"]) set(name, name.startsWith("--r") ? "0deg" : "0px");
    set("--pill-near", "0");
    attract(null);
  };
  // Inside it, the shape leans toward the pointer; big ones also tilt.
  const lean = (e: PointerEvent) => {
    if (e.pointerType !== "mouse" || still) return;
    const r = shape.getBoundingClientRect();
    const fx = (e.clientX - r.left) / r.width - 0.5;
    const fy = (e.clientY - r.top) / r.height - 0.5;
    set("--tx", `${(fx * r.width * 0.05).toFixed(2)}px`);
    set("--ty", `${(fy * r.height * 0.09).toFixed(2)}px`);
    if (!tilts) return;
    set("--ry", `${(fx * 14).toFixed(2)}deg`);
    set("--rx", `${(-fy * 14).toFixed(2)}deg`);
    set("--ex", `${(e.clientX - r.left).toFixed(1)}px`);
    set("--ey", `${(e.clientY - r.top).toFixed(1)}px`);
    set("--pill-near", "1");
  };
  // A real move over it lights it, if a stale moment swallowed the enter.
  const pickUp = (e: PointerEvent) => e.pointerType === "mouse" && !el.classList.contains("is-lit") && light(...xy(e));
  // The timer that rests a touched shape after its beat.
  let rest = 0;
  // A finger lifting: the press shows for its beat, then it rests.
  const lift = (e: Event) => {
    el.classList.remove("is-pressing");
    if ((e as PointerEvent).pointerType === "mouse") return;
    clearTimeout(rest);
    rest = window.setTimeout(() => dark(...middle(shape)), PRESS_MS);
  };
  // A press sinks the shape and rings it; a touch lights it first.
  const press = (e: Event) => {
    clearTimeout(rest);
    if (!el.classList.contains("is-lit")) light(...xy(e));
    else if (!still) ripple();
    el.classList.add("is-pressing");
  };
  // Each pointer and focus event the shape answers, and how.
  const handlers: [string, (e: Event) => void][] = [
    ["pointerenter", (e) => (e as PointerEvent).pointerType === "mouse" && !stale && light(...xy(e))],
    ["pointerleave", (e) => (e as PointerEvent).pointerType === "mouse" && dark(...xy(e))],
    ["pointermove", (e) => (pickUp(e as PointerEvent), lean(e as PointerEvent))],
    ["pointerdown", press],
    ["pointerup", lift],
    ["pointercancel", () => dark(...middle(el))],
    ["focus", () => el.matches(":focus-visible") && light(...middle(shape))],
    ["blur", () => dark(...middle(shape))],
  ];
  // Back from the browser's cache it was left lit; it wakes up at rest.
  const wake = (e: PageTransitionEvent) => {
    if (!e.persisted) return;
    const moving = [el, shape, ink];
    for (const part of moving) part.style.transition = "none";
    dark(...middle(shape));
    void ink.offsetWidth;
    for (const part of moving) part.style.transition = "";
  };
  for (const [type, handler] of handlers) el.addEventListener(type, handler);
  addEventListener("pageshow", wake);
  // Unwired while lit, as when its view swaps, it lets the dust go.
  return () => {
    clearTimeout(rest);
    if (el.classList.contains("is-lit")) attract(null);
    for (const [type, handler] of handlers) el.removeEventListener(type, handler);
    removeEventListener("pageshow", wake);
  };
}
