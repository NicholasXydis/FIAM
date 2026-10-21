// pnpm check [all | fix | screens | lighthouse] and options.
import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { promisify } from "node:util";
import zlib from "node:zlib";
import puppeteer from "puppeteer";
import sharp from "sharp";
import { build, bundle, types } from "./build.ts";
import { fast } from "./fast.ts";
import { CARD, headersFor, LISTED, ORIGIN, readHeaders } from "./headers.ts";
import { bin, PAGES, run, served, SITE } from "./lib.ts";
import { screens } from "./screens.ts";

// The website's build, read by the budget, link and device checks.
const DIST = path.join(SITE, "dist");
// What Prettier formats; it skips the generated data by its ignore.
const FILES = ["src", "scripts", "vite.config.ts", "knip.ts", "tsconfig.json", "tsconfig.site.json"];
// Where the one-line comment rule is checked, the data aside.
const COMMENTED = ["src", "scripts", "ad", "vite.config.ts", "knip.ts", ".puppeteerrc.cjs", "pnpm-workspace.yaml"];
// Generated data and Python caches, never linted.
const SKIPPED = ["src/data", "__pycache__"];
// The built pages and their budget; the tour's script has none yet.
const BUILT = ["index.html", "team/index.html", "404.html", "tour/index.html"];
// The tour adds phone and tablet layouts, so its styles get 28 KB.
const BUDGET = { script: 110 * 1024, style: 25 * 1024, tourStyle: 28 * 1024 };
// The part asked for, then its options such as --full or --sim.
const [what = "", ...rest] = process.argv.slice(2);
// Every failure so far; the run exits non-zero if there is any.
const failures: string[] = [];

// Notes a failure; the command fails once every check has run.
const fail = (message: string) => {
  failures.push(message);
  console.log(`  FAIL ${message}`);
};

// Runs one step and keeps its error's words; true when it passed.
async function attempt(name: string, work: () => unknown) {
  try {
    await work();
    return true;
  } catch (error) {
    fail(`${name}: ${error instanceof Error ? error.message.trim() : String(error)}`);
    return false;
  }
}

// Every file under the given paths with one of the extensions.
function walk(paths: string[], extensions: RegExp): string[] {
  return paths.flatMap((p) => {
    const at = path.join(SITE, p);
    if (SKIPPED.some((s) => p === s || p.endsWith(`/${s}`)) || !fs.existsSync(at)) return [];
    if (!fs.statSync(at).isDirectory()) return extensions.test(p) ? [p] : [];
    return walk(
      fs.readdirSync(at).map((name) => `${p}/${name}`),
      extensions,
    );
  });
}

// Comments over 72 characters, or longer than one line, fail.
function comments() {
  const found: string[] = [];
  for (const file of walk(COMMENTED, /\.(ts|tsx|mjs|cjs|css|py|yaml)$/)) {
    const hash = /\.(py|yaml)$/.test(file);
    let previous = false;
    let meta = false;
    fs.readFileSync(path.join(SITE, file), "utf8")
      .split("\n")
      .forEach((line, i) => {
        const text = line.trim();
        // uv's script header is data, read by uv, not a comment.
        if (hash && text === "# /// script") meta = true;
        if (meta) {
          if (text === "# ///") meta = false;
          return void (previous = false);
        }
        const comment = hash ? /^#(?!!)/.test(text) : /^(\/\/(?!\/)|\/\*)/.test(text);
        const where = `${file}:${i + 1}`;
        if (comment && text.length > 72) found.push(`${where} is ${text.length} characters`);
        if (comment && previous) found.push(`${where} continues the comment above`);
        if (comment && text.startsWith("/*") && !text.includes("*/")) found.push(`${where} spans lines`);
        previous = comment;
      });
  }
  for (const problem of found.slice(0, 20)) console.log(`  ${problem}`);
  if (found.length) throw new Error(`${found.length} comments break the one-line rule`);
}

// Types, formatting, comments and unused code, or formatting fixed.
async function code(fix: boolean) {
  if (fix) return void run(bin("prettier"), ["--write", ...FILES, "--log-level", "warn"], { show: true });
  console.log("types, formatting, comments and unused code");
  await attempt("types", types);
  await attempt("formatting (pnpm check fix formats it)", () =>
    run(bin("prettier"), ["--check", ...FILES, "--log-level", "warn"], { show: true }),
  );
  await attempt("comments", comments);
  await attempt("unused files, exports or packages", () => run(bin("knip"), [], { show: true }));
}

// Each built page against its budget, and each link shown once.
function pages() {
  console.log("pages: what each loads, and each link once");
  for (const page of BUILT) {
    const html = fs.readFileSync(path.join(DIST, page), "utf8");
    const files = [...new Set([...html.matchAll(/(?:src|href)="(\/assets\/[^"]+\.(?:js|css))"/g)].map((m) => m[1]!))];
    // Bytes the page loads of one kind, as the measure counts them.
    const size = (ext: string, measure: (b: Buffer) => number) =>
      files.filter((f) => f.endsWith(ext)).reduce((n, f) => n + measure(fs.readFileSync(path.join(DIST, f))), 0);
    const script = size(".js", (b) => zlib.gzipSync(b, { level: 9 }).length);
    const style = size(".css", (b) => b.length);
    // Sizes in KB to one decimal, as the budgets are written.
    const kb = (n: number) => `${(n / 1024).toFixed(1)} KB`;
    console.log(`  ${page.padEnd(16)} script ${kb(script)} gzipped, styles ${kb(style)}`);
    if (page !== "tour/index.html" && script > BUDGET.script) fail(`${page} loads ${kb(script)} of script`);
    const most = page === "tour/index.html" ? BUDGET.tourStyle : BUDGET.style;
    if (style > most) fail(`${page} loads ${kb(style)} of styles`);
    // The brand links home on every page, so only other links count.
    const links = new Map<string, number>();
    for (const [tag] of html.matchAll(/<a\b[^>]*>/g)) {
      const href = /\bhref="([^"#][^"]*)"/.exec(tag)?.[1];
      if (href && !/class="[^"]*\bbrand\b/.test(tag)) links.set(href, (links.get(href) ?? 0) + 1);
    }
    for (const [href, n] of links) if (n > 1) fail(`${page} links to ${href} ${n} times`);
  }
}

// Share cards, robots, the sitemap and the headers the host serves.
async function extras() {
  console.log("share cards, robots, the sitemap and the headers");
  const read = (file: string) => fs.readFileSync(path.join(DIST, file), "utf8");
  const headers = headersFor(readHeaders(read("_headers")), "/");
  const csp = headers.find(([name]) => name === "Content-Security-Policy")?.[1] ?? "";
  for (const name of ["Content-Security-Policy", "Strict-Transport-Security", "X-Content-Type-Options"]) {
    if (!headers.some(([n]) => n === name)) fail(`_headers sets no ${name}`);
  }
  for (const page of BUILT) {
    const html = read(page);
    // Every inline script the page runs must be allowed by its hash.
    for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
      if (/\bsrc=|application\/json/.test(m[1] ?? "")) continue;
      const hash = createHash("sha256")
        .update(m[2] ?? "")
        .digest("base64");
      if (!csp.includes(`'sha256-${hash}'`)) fail(`${page} runs an inline script the policy blocks`);
    }
    // The fade's opt-in sits in the head, read before any stylesheet loads.
    const head = html.slice(0, html.indexOf("<body"));
    if (!/<style>[^<]*@view-transition \{ navigation: auto; \}/.test(head)) fail(`${page} does not opt in to the fade`);
    // A listed page has its card and address; the rest stay unlisted.
    const address = `/${page.replace(/index\.html$/, "")}`;
    if (!LISTED.includes(address)) {
      if (!html.includes('<meta name="robots" content="noindex"')) fail(`${page} is not marked noindex`);
      continue;
    }
    const tag = (key: string) => new RegExp(`(?:property|name)="${key}" content="([^"]*)"`).exec(html)?.[1];
    if (tag("og:url") !== ORIGIN + address) fail(`${page} has og:url ${tag("og:url")}`);
    if (tag("og:image") !== ORIGIN + CARD.path) fail(`${page} has og:image ${tag("og:image")}`);
    if (tag("twitter:card") !== "summary_large_image") fail(`${page} has no large X card`);
    for (const key of ["og:title", "og:description", "twitter:title", "twitter:description"])
      if (!tag(key)) fail(`${page} has no ${key}`);
  }
  // The card is 1200 by 630 and under the 300 KB WhatsApp takes.
  const card = path.join(DIST, CARD.path);
  const { width, height } = await sharp(card).metadata();
  if (width !== CARD.width || height !== CARD.height) fail(`the share card is ${width}x${height}`);
  if (fs.statSync(card).size > 300 * 1024) fail("the share card is over 300 KB");
  if (!read("robots.txt").includes(`Sitemap: ${ORIGIN}/sitemap.xml`)) fail("robots.txt names no sitemap");
  for (const address of LISTED)
    if (!read("sitemap.xml").includes(`<loc>${ORIGIN}${address}</loc>`)) fail(`the sitemap misses ${address}`);
}

// Puppeteer's Chrome, which Lighthouse drives.
function chrome() {
  if (!fs.existsSync(puppeteer.executablePath()))
    throw new Error("puppeteer's Chrome is missing, run pnpm exec puppeteer browsers install chrome");
}

// Runs a command without blocking, so this process can serve meanwhile.
const exec = promisify(execFile);

// One Lighthouse category's title and score.
interface Category {
  title: string;
  score: number;
}

// Lighthouse as a phone on each page; performance under 90 fails.
async function lighthouse() {
  console.log("Lighthouse, mobile");
  const env = { ...process.env, CHROME_PATH: puppeteer.executablePath() };
  await served(DIST, async (base) => {
    for (const [, page, status] of PAGES) {
      // Lighthouse scores no page that answers 404, so it reads the file.
      const at = status === 404 ? "/404.html" : page;
      const args = [`${base}${at}`, "--form-factor=mobile", "--quiet", "--output=json"];
      // One page's report as JSON; never blocking, so the server can answer.
      const score = async () =>
        (await exec(bin("lighthouse"), [...args, "--chrome-flags=--headless=new"], { env, maxBuffer: 1 << 28 })).stdout;
      // Its browser sometimes closes on a busy machine, so a second try.
      let json: string;
      try {
        json = await score();
      } catch {
        try {
          json = await score();
        } catch {
          fail(`Lighthouse could not load ${at}`);
          continue;
        }
      }
      const categories: Category[] = Object.values(JSON.parse(json).categories);
      const scores = categories.map((c) => [c.title, Math.round(c.score * 100)] as const);
      console.log(`  ${at.padEnd(16)} ${scores.map(([t, s]) => `${t} ${s}`).join(" · ")}`);
      const performance = scores.find(([t]) => t === "Performance")?.[1] ?? 0;
      if (performance < 90) fail(`${at} scores ${performance} for performance`);
    }
  });
}

// The device checks, quick or full, with or without real Safari.
async function devices(full: boolean, sim: boolean) {
  console.log(full ? "every device" : "the quick devices");
  const found = await screens({ full, sim });
  if (found) fail(`${found} problems on devices, see out/screens/index.html`);
}

// The quick checks by browser: addresses, marks, keys and the tour.
async function quick() {
  const found = await fast();
  if (found.length) fail(`${found.length} problems in the quick checks`);
}

// A full build first for the parts run on their own.
const built = () => attempt("the build", build);
if (what === "fix") await code(true);
else if (what === "lighthouse") {
  if ((await attempt("browsers", chrome)) && (await built())) await attempt("Lighthouse", lighthouse);
} else if (what === "screens") {
  if (await built()) await attempt("devices", () => devices(rest.includes("--full"), rest.includes("--sim")));
} else {
  // check all adds every device, Safari and Lighthouse.
  const all = what === "all";
  await code(false);
  if (await attempt("the build", bundle)) {
    await attempt("pages", pages);
    await attempt("share cards and headers", extras);
    const browsers = all && (await attempt("browsers", chrome));
    // The devices and the quick checks share the wait, side by side.
    await Promise.all([attempt("devices", () => devices(all, all)), attempt("quick checks", quick)]);
    if (browsers) await attempt("Lighthouse", lighthouse);
  }
}
console.log(failures.length ? `\n${failures.length} check(s) failed` : "\nall checks pass");
process.exit(failures.length ? 1 : 0);
