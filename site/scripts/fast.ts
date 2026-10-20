// Quick checks of the build: addresses, words, keys, and the tour.
import fs from "node:fs";
import path from "node:path";
import { type Browser, chromium, type Page, webkit } from "playwright-core";
import { PAGES, served, SITE, sleep } from "./lib.ts";

// The website's build, and the tour's thirteen slides.
const DIST = path.join(SITE, "dist");
const SLIDES = 13;
// Marks the on-screen copy never uses: long dashes, colons, semicolons.
const BANNED = /[—–:;]/;

// Every file under a folder, as paths inside it.
const files = (dir: string): string[] =>
  fs
    .readdirSync(dir, { withFileTypes: true })
    .flatMap((e) => (e.isDirectory() ? files(path.join(dir, e.name)) : [path.join(dir, e.name)]));

// Every local address in pages, styles, scripts and manifest exists.
function addresses() {
  const problems: string[] = [];
  const all = files(DIST);
  // Pages and the manifest name files by src or href; styles by url().
  const patterns: [RegExp, RegExp][] = [
    [/\.html$/, /(?:src|href)="(\/[^"#?]*)"/g],
    [/\.css$/, /url\((?:"|')?(\/[^)"'#?]+)/g],
    [/\.js$/, /"(\/(?:assets|people)\/[^"#?]+)"/g],
    [/\.webmanifest$/, /"src":\s*"(\/[^"]+)"/g],
  ];
  for (const file of all) {
    const pattern = patterns.find(([ext]) => ext.test(file))?.[1];
    if (!pattern) continue;
    for (const [, at] of fs.readFileSync(file, "utf8").matchAll(pattern)) {
      if (at!.startsWith("//")) continue;
      const target = path.join(DIST, at!.endsWith("/") ? `${at}index.html` : at!);
      if (!fs.existsSync(target)) problems.push(`${path.relative(DIST, file)} names ${at}, which is missing`);
    }
  }
  return problems;
}

// Visible text with a banned mark, in a slide's own boxes or the page.
function marks({ banned, slide }: { banned: string; slide: number | null }) {
  const rule = new RegExp(banned);
  const found: string[] = [];
  const roots =
    slide === null
      ? [document.body]
      : [document.querySelectorAll(".panel")[slide]!, document.querySelectorAll(".controls")[slide]!];
  for (const root of roots) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const el = n.parentElement;
      const text = n.textContent ?? "";
      if (!el || !rule.test(text) || el.closest("script, style, [hidden]")) continue;
      const s = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      if (s.visibility === "hidden" || s.display === "none" || !r.width) continue;
      found.push(text.trim().slice(0, 50));
    }
  }
  return found;
}

// Waits, up to five seconds, for a slide's story to finish rising in.
async function settle(page: Page, slide: number) {
  for (let i = 0; i < 50; i++) {
    const still = await page.evaluate((n) => {
      const panel = document.querySelectorAll<HTMLElement>(".panel")[n];
      const s = panel && getComputedStyle(panel);
      return (
        !!s &&
        panel.classList.contains("on") &&
        s.opacity === "1" &&
        ["none", "matrix(1, 0, 0, 1, 0, 0)"].includes(s.transform)
      );
    }, slide);
    if (still) return;
    await sleep(100);
  }
}

// A page with its errors collected, for each check to read.
async function tab(browser: Browser, options: Parameters<Browser["newContext"]>[0]) {
  const page = await (await browser.newContext(options)).newPage();
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`page error: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().startsWith("Failed to load resource")) errors.push(`console: ${m.text()}`);
  });
  return { page, errors };
}

// The site's pages and each profile: banned marks, then the keyboard.
async function site(browser: Browser, base: string) {
  const problems: string[] = [];
  const { page, errors } = await tab(browser, { viewport: { width: 1280, height: 800 }, reducedMotion: "reduce" });
  const people = [] as string[];
  for (const [name, at] of PAGES) {
    await page.goto(base + at);
    await sleep(300);
    for (const m of await page.evaluate(marks, { banned: BANNED.source, slide: null }))
      problems.push(`${name} shows "${m}"`);
    if (at === "/team/")
      people.push(...(await page.$$eval("[data-slug]", (els) => els.map((e) => e.dataset["slug"]!))));
    problems.push(...(await keys(page, name)));
  }
  for (const slug of people) {
    await page.goto(`${base}/team/#${slug}`);
    await sleep(300);
    for (const m of await page.evaluate(marks, { banned: BANNED.source, slide: null }))
      problems.push(`${slug} shows "${m}"`);
  }
  return [...problems, ...errors.map((e) => `site ${e}`)];
}

// Tab walks every control on a page, each showing a focus ring.
async function keys(page: Page, name: string) {
  const problems: string[] = [];
  const seen: string[] = [];
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    const now = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return null;
      // A ring is an outline on the control or on a part of it.
      const ringed = [el, ...el.querySelectorAll("*")].some((x) => getComputedStyle(x).outlineStyle !== "none");
      const r = el.getBoundingClientRect();
      const words = (el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 30);
      return { id: `${el.tagName}:${words}`, ringed, inside: r.bottom > 0 && r.top < innerHeight };
    });
    if (!now) continue;
    if (seen[0] === now.id) break;
    seen.push(now.id);
    if (!now.ringed) problems.push(`${name}: no focus ring on "${now.id}"`);
    if (!now.inside) problems.push(`${name}: focused "${now.id}" is off screen`);
  }
  if (!seen.length) problems.push(`${name}: Tab reaches no control`);
  return problems;
}

// One slide's title and body lines, and the slide the address names.
function lines(slide: number) {
  const panel = document.querySelectorAll(".panel")[slide];
  const head = panel?.querySelector<HTMLElement>(".headline");
  const body = panel?.querySelector<HTMLElement>(".body");
  // Lines from a box's height over its line height.
  const count = (el: HTMLElement | null | undefined, ratio?: number) => {
    if (!el || !el.getBoundingClientRect().height) return 0;
    const s = getComputedStyle(el);
    const line = ratio ? parseFloat(s.fontSize) * ratio : parseFloat(s.lineHeight);
    return Math.round(el.getBoundingClientRect().height / line);
  };
  return {
    hash: location.hash,
    title: count(head, 0.98),
    body: count(body),
    wide: !!head && head.scrollWidth > head.clientWidth + 1,
  };
}

// The tour by arrow keys on desktops: one-line titles, two-line bodies.
async function desk(browser: Browser, base: string, width: number, height: number) {
  const problems: string[] = [];
  const { page, errors } = await tab(browser, { viewport: { width, height } });
  await page.goto(`${base}/tour/#0`);
  await sleep(1500);
  for (let s = 0; s < SLIDES; s++) {
    if (s) await page.keyboard.press("ArrowRight");
    await sleep(250);
    const got = await page.evaluate(lines, s);
    const at = `${width}x${height} slide ${s + 1}`;
    if (got.hash !== `#${s}`) problems.push(`${at}: the arrow key reached ${got.hash}`);
    if (got.title > 1 || got.wide) problems.push(`${at}: the title takes ${got.title} lines`);
    if (got.body > 2) problems.push(`${at}: the paragraph takes ${got.body} lines`);
    if (width === 1280)
      for (const m of await page.evaluate(marks, { banned: BANNED.source, slide: s }))
        problems.push(`${at} shows "${m}"`);
  }
  return [...problems, ...errors.map((e) => `${width}x${height} ${e}`)];
}

// The phone rules on a slide: boxes apart, text on screen, legible.
function phone(slide: number) {
  const problems: string[] = [];
  // Shown with a size, and not faded or hidden by any parent.
  const shows = (el: Element | null): el is HTMLElement => {
    if (!el || el.closest("[hidden]")) return false;
    for (let e: Element | null = el; e && e !== document.body; e = e.parentElement) {
      const s = getComputedStyle(e);
      if (s.display === "none" || s.visibility === "hidden" || +s.opacity < 0.05) return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const hit = (a: DOMRect, b: DOMRect) =>
    a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
  const story = document.querySelectorAll(".panel")[slide] ?? null;
  const controls = document.querySelectorAll(".controls")[slide] ?? null;
  const named = (
    [
      ["story", story],
      ["controls", controls],
      ["dock", document.querySelector(".dock")],
      ["header", document.querySelector(".topbar")],
      ["Back", document.querySelector(".tour-back")],
    ] as const
  ).flatMap(([n, el]) => (shows(el) ? [[n, el.getBoundingClientRect()] as const] : []));
  for (let i = 0; i < named.length; i++)
    for (let j = i + 1; j < named.length; j++)
      if (hit(named[i]![1], named[j]![1])) problems.push(`the ${named[i]![0]} meets the ${named[j]![0]}`);
  const head = story?.querySelector<HTMLElement>(".headline");
  if (head && head.scrollWidth > head.clientWidth + 1) problems.push("the title is cut");
  // Text in a scrolling row, panel or the dock may run past the edge.
  const walker = document.createTreeWalker(document.querySelector(".ui")!, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement;
    if (!n.textContent?.trim() || !shows(el) || el.closest(".sheet, .label3d, .row, .where, .dots")) continue;
    // Another slide's boxes, still fading out, are not this slide's.
    const box = el.closest(".panel, .controls");
    if (box && box !== story && box !== controls) continue;
    const range = document.createRange();
    range.selectNodeContents(n);
    const r = range.getBoundingClientRect();
    const scroller = el.closest(".panel, .controls, .card");
    const clipped = scroller && scroller.scrollHeight > scroller.clientHeight + 1;
    if (!clipped && (r.left < -1 || r.right > innerWidth + 1 || r.top < -1 || r.bottom > innerHeight + 1))
      problems.push(`"${n.textContent.trim().slice(0, 24)}" runs off screen`);
    if (parseFloat(getComputedStyle(el).fontSize) < 11)
      problems.push(`"${n.textContent.trim().slice(0, 24)}" is under 11px`);
  }
  for (const el of document.querySelectorAll(".ui button, .ui input, .ui [role=button], .tour-back")) {
    const box = el.closest(".panel, .controls");
    if (!shows(el) || el.closest(".sheet, .dots, .label3d") || (box && box !== story && box !== controls)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 43.5 || r.height < 43.5) problems.push(`a ${Math.round(r.width)}x${Math.round(r.height)} target`);
  }
  return [...new Set(problems)];
}

// The tour on a phone, upright or sideways, by the phone rules.
async function phones(browser: Browser, base: string, width: number, height: number) {
  const problems: string[] = [];
  const { page, errors } = await tab(browser, { viewport: { width, height }, isMobile: true, hasTouch: true });
  await page.goto(`${base}/tour/#0`);
  await sleep(1500);
  for (let s = 0; s < SLIDES; s++) {
    await page.evaluate((n) => (location.hash = `#${n}`), s);
    await settle(page, s);
    // The camera fits the band once the story lands, then labels place.
    await sleep(300);
    for (const p of await page.evaluate(phone, s)) problems.push(`${width}x${height} slide ${s + 1}: ${p}`);
  }
  return [...problems, ...errors.map((e) => `${width}x${height} ${e}`)];
}

// Runs every quick check at once, prints and returns what they found.
export async function fast() {
  console.log("addresses, marks, keys, and the tour on desktops and phones");
  const found = addresses();
  // Chrome draws the tour's WebGL in software, as a laptop GPU would.
  const gpu = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"];
  const [blink, safari] = await Promise.all([chromium.launch({ args: gpu }), webkit.launch()]);
  try {
    await served(DIST, async (base) => {
      const parts = await Promise.all([
        site(blink, base),
        desk(blink, base, 1280, 720),
        desk(blink, base, 1440, 900),
        desk(blink, base, 1920, 1080),
        phones(safari, base, 393, 852),
        phones(safari, base, 852, 393),
      ]);
      found.push(...parts.flat());
    });
  } finally {
    await Promise.all([blink.close(), safari.close()]);
  }
  for (const problem of found.slice(0, 30)) console.log(`  ${problem}`);
  return found;
}
