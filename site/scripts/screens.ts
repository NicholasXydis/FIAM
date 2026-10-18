// Device checks: every page on real profiles, a sweep, real Safari.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import {
  type Browser,
  type BrowserContextOptions,
  chromium,
  devices,
  firefox,
  type Page,
  webkit,
} from "playwright-core";
import { REPO, serve, SITE, sleep } from "./lib.ts";

// Where the shots and the contact sheet go, and the pages checked.
const OUT = path.join(REPO, "out", "screens");
const PAGES = [
  ["Landing", "/"],
  ["Team", "/team/"],
  ["Not found", "/no-such-page/"],
] as const;
// Playwright's three engines: Safari's, Chrome's and Firefox's.
const ENGINES = { chromium, firefox, webkit };
type Engine = keyof typeof ENGINES;

// Starts an engine, or says how to install it when it is missing.
async function launch(engine: Engine) {
  try {
    return await ENGINES[engine].launch();
  } catch (error) {
    if (!String(error).includes("Executable doesn't exist")) throw error;
    throw new Error(`Playwright's ${engine} is missing, run pnpm exec playwright-core install ${engine}`);
  }
}

// One screen to check: its name, its engine and how it is emulated.
interface Device {
  name: string;
  engine: Engine;
  options?: BrowserContextOptions;
}

// One page shot on one device, and the problems found on it.
interface Result {
  device: Device;
  page: string;
  shot: string;
  problems: string[];
}

// A Playwright device profile, in the engine that device ships.
const profile = (name: string): Device => {
  const options = devices[name]!;
  return { name, engine: options.defaultBrowserType, options };
};
// A plain screen of a size, for laptops, desktops and projectors.
const screen = (name: string, engine: Engine, width: number, height: number, scale = 1): Device => ({
  name,
  engine,
  options: { viewport: { width, height }, deviceScaleFactor: scale },
});

// Thirteen screens that stand for the rest, for the quick check.
const QUICK = [
  profile("iPhone SE"),
  profile("iPhone 17"),
  profile("iPhone 17 Pro Max"),
  profile("Galaxy S24"),
  profile("Pixel 8 Pro"),
  profile("Galaxy Z Fold 7"),
  profile("iPad Mini"),
  profile("iPad Pro 11 landscape"),
  screen("Laptop 1366x768, Chrome", "chromium", 1366, 768),
  screen("MacBook 1440x900, Safari", "webkit", 1440, 900, 2),
  screen("Projector 1920x1080, Firefox", "firefox", 1920, 1080),
  screen("Projector 1024x768, Chrome", "chromium", 1024, 768),
  screen("4K 3840x2160, Chrome", "chromium", 3840, 2160),
];

// Common laptop, desktop, ultrawide and projector sizes.
const SIZES = [
  [1024, 768],
  [1280, 800],
  [1280, 1024],
  [1366, 768],
  [1440, 900],
  [1536, 864],
  [1920, 1080],
  [1920, 1200],
  [2560, 1080],
  [2560, 1440],
  [3440, 1440],
  [3840, 2160],
  [5120, 1440],
] as const;
// Every Playwright profile, then each size in all three engines.
const FULL = [
  ...Object.keys(devices).map(profile),
  ...SIZES.flatMap(([w, h]) => (Object.keys(ENGINES) as Engine[]).map((e) => screen(`${w}x${h}, ${e}`, e, w, h))),
];

// The sweep's shapes as width over height, tall phone to ultrawide.
const SHAPES = [9 / 21, 9 / 16, 3 / 4, 1, 4 / 3, 16 / 10, 16 / 9, 21 / 9, 32 / 9];

// Everything checked on one page at one size, run inside the page.
function inspect() {
  const vw = innerWidth;
  const problems: string[] = [];
  // An element's label or text, short enough to quote in a problem.
  const words = (el: Element) =>
    (el.getAttribute("aria-label") || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 40);
  // On screen with a size, and neither faded out nor made invisible.
  const shown = (el: Element) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return (
      r.width > 0 &&
      r.height > 0 &&
      s.visibility !== "hidden" &&
      +s.opacity > 0 &&
      r.right > 0 &&
      r.left < vw &&
      r.bottom > 0
    );
  };
  // A text node with words in it, not only spaces between tags.
  const texty = (n: Node) => n.nodeType === 3 && !!n.textContent?.trim();
  const scroll = document.documentElement.scrollWidth - vw;
  if (scroll > 1) problems.push(`scrolls sideways by ${scroll}px`);
  const texts = [...document.body.querySelectorAll("*")].filter((el) => [...el.childNodes].some(texty) && shown(el));
  for (const el of texts) {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    if (r.left < -1 || r.right > vw + 1) problems.push(`text off screen: "${words(el)}"`);
    if (el.scrollWidth > el.clientWidth + 1 && s.overflowX !== "visible") problems.push(`text clipped: "${words(el)}"`);
    if (parseFloat(s.fontSize) < 11) problems.push(`text under 11px: "${words(el)}"`);
  }
  // Each line of each text as a tight box, so wide blocks do not overlap.
  const lines: { el: Element; r: DOMRect }[] = [];
  for (const el of texts) {
    for (const node of el.childNodes) {
      if (!texty(node)) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      for (const r of range.getClientRects()) if (r.width > 1 && r.height > 1) lines.push({ el, r });
    }
  }
  for (let i = 0; i < lines.length; i++) {
    for (let j = i + 1; j < lines.length; j++) {
      const [a, b] = [lines[i]!, lines[j]!];
      if (a.el === b.el || a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const x = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
      const y = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
      if (x > 2 && y > 0.3 * Math.min(a.r.height, b.r.height))
        problems.push(`text overlaps: "${words(a.el)}" and "${words(b.el)}"`);
    }
  }
  if (matchMedia("(pointer: coarse)").matches) {
    for (const el of document.querySelectorAll("a[href], button, input, select, [role=button]")) {
      const r = el.getBoundingClientRect();
      if (shown(el) && (r.width < 44 || r.height < 44))
        problems.push(`target under 44px (${Math.round(r.width)}x${Math.round(r.height)}): "${words(el)}"`);
    }
  }
  const links = new Map<string, number>();
  for (const a of document.querySelectorAll<HTMLAnchorElement>("a[href]")) {
    if (!shown(a) || a.getAttribute("href")?.startsWith("#") || a.classList.contains("brand")) continue;
    const href = new URL(a.href).pathname;
    links.set(href, (links.get(href) ?? 0) + 1);
  }
  for (const [href, n] of links) if (n > 1) problems.push(`link to ${href} shown ${n} times`);
  return [...new Set(problems)];
}

// Loads a page and waits for its fonts and pictures.
async function load(tab: Page, url: string) {
  await tab.goto(url, { waitUntil: "load" });
  await tab.evaluate(async () => {
    await document.fonts.ready;
    const waiting = [...document.images].filter((i) => !i.complete);
    await Promise.all(waiting.map((i) => new Promise((r) => (i.onload = i.onerror = r))));
  });
  await sleep(250);
}

// A file name for a shot from its parts.
const named = (...parts: string[]) =>
  parts
    .map((p) => p.replace(/\W+/g, "-"))
    .join("-")
    .toLowerCase();

// Every page on every device: a full-page shot each, and its problems.
async function onDevices(list: Device[], base: string) {
  const results: Result[] = [];
  const browsers: Partial<Record<Engine, Browser>> = {};
  for (const device of list) {
    const browser = (browsers[device.engine] ??= await launch(device.engine));
    const context = await browser.newContext({ ...device.options, reducedMotion: "reduce" });
    for (const [page, at] of PAGES) {
      const tab = await context.newPage();
      const errors: string[] = [];
      tab.on("pageerror", (e) => errors.push(`page error: ${e.message}`));
      await load(tab, base + at);
      const shot = `${named(device.name, page)}.jpg`;
      await tab.screenshot({ path: path.join(OUT, shot), type: "jpeg", quality: 72, fullPage: true });
      results.push({ device, page, shot, problems: [...errors, ...(await tab.evaluate(inspect))] });
      await tab.close();
    }
    await context.close();
  }
  for (const b of Object.values(browsers)) await b.close();
  return results;
}

// Back after following a link returns to the page it left, per engine.
async function back(base: string) {
  const problems: string[] = [];
  for (const engine of Object.keys(ENGINES) as Engine[]) {
    const browser = await launch(engine);
    const tab = await browser.newPage({ reducedMotion: "reduce" });
    await load(tab, `${base}/`);
    const link = tab.locator('a[href="/team/"]').first();
    if (!(await link.count())) problems.push(`${engine}: no link to the team page`);
    else {
      await link.click();
      await tab.waitForURL("**/team/");
      await tab.goBack();
      if (new URL(tab.url()).pathname !== "/") problems.push(`${engine}: Back from the team page did not return home`);
    }
    await browser.close();
  }
  return problems;
}

// One problem from the sweep, and the sizes it showed at.
interface Swept {
  problem: string;
  sizes: string[];
}

// Every page from 280 to 3840 wide in steps of 40, in each shape.
async function sweep(base: string): Promise<Swept[]> {
  const found = new Map<string, string[]>();
  const browser = await launch("chromium");
  const tab = await browser.newPage({ reducedMotion: "reduce" });
  for (const [page, at] of PAGES) {
    await load(tab, base + at);
    for (const shape of SHAPES) {
      for (let w = 280; w <= 3840; w += 40) {
        const h = Math.round(w / shape);
        if (h < 280 || h > 2400) continue;
        await tab.setViewportSize({ width: w, height: h });
        for (const p of await tab.evaluate(inspect)) {
          const key = `${page}: ${p}`;
          found.set(key, [...(found.get(key) ?? []), `${w}x${h}`]);
        }
      }
    }
  }
  await browser.close();
  return [...found].map(([problem, sizes]) => ({ problem, sizes }));
}

// The iOS Simulator's tool through any installed Xcode, or null.
function simulator() {
  let found = "";
  try {
    found = execFileSync("mdfind", ["kMDItemCFBundleIdentifier == 'com.apple.dt.Xcode'"], { encoding: "utf8" });
  } catch {}
  const dirs = [process.env["DEVELOPER_DIR"], ...found.split("\n").map((x) => x && `${x}/Contents/Developer`)];
  for (const dir of dirs.filter((d): d is string => !!d)) {
    const env = { ...process.env, DEVELOPER_DIR: dir };
    try {
      execFileSync("xcrun", ["simctl", "help"], { env, stdio: "ignore" });
      return (...args: string[]) =>
        execFileSync("xcrun", ["simctl", ...args], { env, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
    } catch {}
  }
  return null;
}

// One simulated device as simctl lists it.
interface Simulated {
  name: string;
  udid: string;
  state: string;
}

// Real Safari on simulated iPhones and iPads, each page shot.
async function onSimulators(base: string) {
  const simctl = simulator();
  if (!simctl) return { results: [], note: "No Xcode, so no iOS Simulator shots" };
  const lists: Record<string, Simulated[]> = JSON.parse(simctl("list", "devices", "available", "-j")).devices;
  const available = Object.values(lists).flat();
  const results: Result[] = [];
  for (const want of ["iPhone 17e", "iPhone 17 Pro Max", "iPad mini", "iPad Pro 13"]) {
    const sim = available.find((d) => d.name.startsWith(want));
    if (!sim) continue;
    if (sim.state !== "Booted") simctl("boot", sim.udid);
    simctl("bootstatus", sim.udid, "-b");
    for (const [page, at] of PAGES) {
      simctl("openurl", sim.udid, base + at);
      await sleep(5000);
      const shot = `${named("safari", sim.name, page)}.png`;
      simctl("io", sim.udid, "screenshot", path.join(OUT, shot));
      results.push({ device: { name: `${sim.name}, Safari (Simulator)`, engine: "webkit" }, page, shot, problems: [] });
    }
    if (sim.state !== "Booted") simctl("shutdown", sim.udid);
  }
  return { results, note: "" };
}

// The contact sheet: each device's shots in a row, problems below.
function sheet(results: Result[], swept: Swept[], backs: string[], note: string) {
  // Escapes text for the contact sheet's HTML.
  const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  const rows = new Map<string, Result[]>();
  for (const r of results) rows.set(r.device.name, [...(rows.get(r.device.name) ?? []), r]);
  const count = results.reduce((n, r) => n + r.problems.length, 0) + swept.length + backs.length;
  const body = [...rows]
    .map(([name, shots]) => {
      const first = shots[0]!.device;
      const v = first.options?.viewport;
      const size = v ? ` · ${v.width}x${v.height}` : "";
      const cells = shots
        .map(
          (s) =>
            `<figure><a href="${s.shot}"><img src="${s.shot}" loading="lazy" alt="${esc(s.page)}"></a><figcaption>${esc(s.page)}</figcaption>${s.problems.map((p) => `<p class="bad">${esc(p)}</p>`).join("")}</figure>`,
        )
        .join("");
      return `<section><h2>${esc(name)} <small>${first.engine}${size}</small></h2><div class="row">${cells}</div></section>`;
    })
    .join("");
  // How many sizes beyond the six the sheet lists.
  const more = (n: number) => (n > 6 ? ` and ${n - 6} more` : "");
  const sweepList = swept.map(
    (s) => `<li>${esc(s.problem)} <small>at ${s.sizes.slice(0, 6).join(", ")}${more(s.sizes.length)}</small></li>`,
  );
  const html = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Device checks</title>
<style>body{margin:0;padding:24px max(16px,env(safe-area-inset-left));background:#0b0a10;color:#e9e6f2;font:14px/1.5 system-ui,sans-serif}h1{font-weight:600}h2{font-size:15px;margin:28px 0 8px}small{color:#9b96ab;font-weight:400}.row{display:flex;gap:12px;overflow-x:auto;padding-bottom:6px}figure{margin:0;flex:0 0 220px}img{width:220px;border:1px solid #2a2735;border-radius:6px;display:block}figcaption{color:#9b96ab;font-size:12px;margin-top:4px}.bad{color:#ff8a7a;font-size:12px;margin:4px 0 0}.ok{color:#8fe3a8}</style>
<h1>Device checks <small>${new Date().toISOString().slice(0, 16).replace("T", " ")}</small></h1>
<p class="${count ? "bad" : "ok"}">${count ? `${count} problems` : "No problems found"} across ${rows.size} devices.${note ? ` ${esc(note)}.` : ""}</p>
${backs.map((b) => `<p class="bad">${esc(b)}</p>`).join("")}${sweepList.length ? `<h2>Size sweep</h2><ul>${sweepList.join("")}</ul>` : ""}${body}`;
  fs.writeFileSync(path.join(OUT, "index.html"), html);
  return count;
}

// Checks the build in dist/ and writes the sheet; returns the problems.
export async function screens({ full = false, sim = false } = {}) {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  const server = await serve(path.join(SITE, "dist"));
  try {
    const results = await onDevices(full ? FULL : QUICK, server.url);
    const backs = await back(server.url);
    const swept = full ? await sweep(server.url) : [];
    const safari = full || sim ? await onSimulators(server.url) : { results: [], note: "" };
    const count = sheet([...results, ...safari.results], swept, backs, safari.note);
    const shown = new Set(results.map((r) => r.device.name)).size;
    console.log(`${count ? `${count} problems` : "no problems"} on ${shown} devices, out/screens/index.html`);
    return count;
  } finally {
    server.close();
  }
}
