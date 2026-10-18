// pnpm check [all | fix | proof | screens | lighthouse] and options.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import puppeteer from "puppeteer";
import { build, bundle, types } from "./build.ts";
import { bin, run, serve, SITE } from "./lib.ts";
import { screens } from "./screens.ts";

// The website's build, read by the budget, link and device checks.
const DIST = path.join(SITE, "dist");
// What Prettier formats; it skips the data and pictures by its ignore.
const FILES = ["src", "scripts", "vite.config.ts", "knip.ts"];
// Where the one-line comment rule is checked, data and pictures aside.
const COMMENTED = ["src", "scripts", "ad", "vite.config.ts", "knip.ts", ".puppeteerrc.cjs", "pnpm-workspace.yaml"];
// Generated data, film pictures and Python caches, never linted.
const SKIPPED = ["src/data", "src/assets", "__pycache__"];
// The built pages and their budget; the tour's script is phase 3.
const PAGES = ["index.html", "team/index.html", "404.html", "tour/index.html"];
const BUDGET = { script: 110 * 1024, style: 25 * 1024 };
// The pages Lighthouse scores.
const LIGHTHOUSE = ["/", "/team/", "/no-such-page/"];
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
  for (const page of PAGES) {
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
    if (style > BUDGET.style) fail(`${page} loads ${kb(style)} of styles`);
    // The brand links home on every page, so only other links count.
    const links = new Map<string, number>();
    for (const [tag] of html.matchAll(/<a\b[^>]*>/g)) {
      const href = /\bhref="([^"#][^"]*)"/.exec(tag)?.[1];
      if (href && !/class="[^"]*\bbrand\b/.test(tag)) links.set(href, (links.get(href) ?? 0) + 1);
    }
    for (const [href, n] of links) if (n > 1) fail(`${page} links to ${href} ${n} times`);
  }
}

// Puppeteer's Chrome, which the proof and Lighthouse drive.
function chrome() {
  if (!fs.existsSync(puppeteer.executablePath()))
    throw new Error("puppeteer's Chrome is missing, run pnpm exec puppeteer browsers install chrome");
}

// One Lighthouse category's title and score.
interface Category {
  title: string;
  score: number;
}

// Lighthouse as a phone on each page; performance under 90 fails.
async function lighthouse() {
  console.log("Lighthouse, mobile");
  const server = await serve(DIST);
  const env = { ...process.env, CHROME_PATH: puppeteer.executablePath() };
  try {
    for (const at of LIGHTHOUSE) {
      const args = [`${server.url}${at}`, "--form-factor=mobile", "--quiet", "--output=json"];
      // One page's report as JSON, on puppeteer's Chrome, headless.
      const score = () =>
        execFileSync(bin("lighthouse"), [...args, "--chrome-flags=--headless=new"], {
          env,
          maxBuffer: 1 << 28,
          encoding: "utf8",
          stdio: ["ignore", "pipe", "ignore"],
        });
      // Its browser sometimes closes on a busy machine, so a second try.
      let json: string;
      try {
        json = score();
      } catch {
        try {
          json = score();
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
  } finally {
    server.close();
  }
}

// The proof of the tour and the ad, with its own parts and flags.
async function proof(parts: string[]) {
  const { proof } = await import("./proof.ts");
  if (await proof(parts)) fail("the proof found a difference");
}

// The device checks, quick or full, with or without real Safari.
async function devices(full: boolean, sim: boolean) {
  console.log(full ? "every device" : "the quick devices");
  const found = await screens({ full, sim });
  if (found) fail(`${found} problems on devices, see out/screens/index.html`);
}

// A full build first for the parts run on their own.
const built = () => attempt("the build", build);
if (what === "fix") await code(true);
else if (what === "proof") {
  if (await attempt("browsers", chrome)) await proof(rest);
} else if (what === "lighthouse") {
  if ((await attempt("browsers", chrome)) && (await built())) await lighthouse();
} else if (what === "screens") {
  if (await built()) await attempt("devices", () => devices(rest.includes("--full"), rest.includes("--sim")));
} else {
  // check all adds the proof, every device, Safari and Lighthouse.
  const all = what === "all";
  await code(false);
  if (await attempt("the build", bundle)) {
    pages();
    if (all && (await attempt("browsers", chrome))) await proof([]);
    await attempt("devices", () => devices(all, all));
    if (all) await lighthouse();
  }
}
console.log(failures.length ? `\n${failures.length} check(s) failed` : "\nall checks pass");
process.exit(failures.length ? 1 : 0);
