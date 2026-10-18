// Proves the tour and ad unchanged: pnpm check proof [parts] [--fresh].
import { execFileSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import puppeteer, { type Browser, type Page } from "puppeteer";
import sharp from "sharp";
import { REPO, run, serve, SITE, sleep } from "./lib.ts";

// What the pages hand the proof: the fake clock and the ad's recorder.
declare global {
  interface Window {
    __advance(ms: number): void;
    __ready?: boolean;
    __length: number;
    __cues: Record<string, unknown>;
    __camera(t: number): unknown;
    __draw(t: number, subframes: number, fps: number, shutter: number): void;
  }
}

// Where the approved site and the current builds are captured.
const BASE = path.join(REPO, "out", "proof", "base");
const NOW = path.join(REPO, "out", "proof", "now");
// The commit that holds the tour and the ad as approved.
const BASELINE = "d63a2eb";
// The two finished films and their checksums as approved.
const VIDEOS = {
  "deck/QUARCC_Purple_FIAM_trailer.mp4": "96ccbb9e9cdc1b581e4b89691d67b831e93321b7617bbb6f550d46d0957c91ec",
  "deck/QUARCC_Purple_FIAM_trailer_vertical.mp4": "25f0a399b5e88dadb4a84a9787fee6c804756b9a52536a72d547304555a51929",
};
// The ad's moments in seconds, and the two sizes each is shot at.
const MOMENTS = [0.5, 3, 6, 9.5, 11, 12.5, 13.5, 15, 17.8, 20, 22.5, 26, 30, 33, 37, 41, 44, 47.5, 52, 58];
const SIZES = [
  [640, 360],
  [270, 480],
] as const;

// A fake clock run before the page's scripts; time moves on __advance.
function clock() {
  const FRAME = 1000 / 60;
  let frame = 0;
  let now = 0;
  let seed = 1234567;
  let next = 1;
  let frames: { id: number; callback: FrameRequestCallback }[] = [];
  let timers: { id: number; at: number; every: number; callback: () => void }[] = [];

  // mulberry32, so every run draws the same numbers.
  Math.random = () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };

  // Clocks that read virtual time.
  const epoch = Date.UTC(2026, 9, 28);
  performance.now = () => now;
  Date.now = () => epoch + now;

  // Animation frames run only when the proof advances time.
  window.requestAnimationFrame = (callback) => {
    frames.push({ id: next, callback });
    return next++;
  };
  window.cancelAnimationFrame = (id) => {
    frames = frames.filter((f) => f.id !== id);
  };

  // Timers fire in virtual time, in the order they fall due.
  const add = (callback: TimerHandler, ms: unknown, every: number, args: unknown[]) => {
    // The timer's work with its arguments, as setTimeout passes them.
    const call = () => (callback as (...a: unknown[]) => void)(...args);
    timers.push({ id: next, at: now + Math.max(0, Number(ms) || 0), every, callback: call });
    return next++;
  };
  window.setTimeout = ((callback: TimerHandler, ms?: number, ...args: unknown[]) =>
    add(callback, ms, 0, args)) as typeof setTimeout;
  window.setInterval = ((callback: TimerHandler, ms?: number, ...args: unknown[]) =>
    add(callback, ms, Math.max(1, Number(ms) || 0), args)) as typeof setInterval;
  window.clearTimeout = window.clearInterval = (id) => {
    timers = timers.filter((t) => t.id !== id);
  };

  // Steps whole frames: the timers that fall due, then animation frames.
  window.__advance = (ms) => {
    const end = frame + Math.round(ms / FRAME);
    while (frame < end) {
      now = ++frame * FRAME;
      for (;;) {
        const due = timers.filter((t) => t.at <= now).sort((a, b) => a.at - b.at || a.id - b.id)[0];
        if (!due) break;
        if (due.every) due.at += due.every;
        else timers = timers.filter((t) => t !== due);
        due.callback();
      }
      const ran = frames;
      frames = [];
      for (const f of ran) f.callback(now);
    }
  };
}

// Polls the page in real time, since the page's own timers are frozen.
async function until(tab: Page, test: () => boolean, what: string, seconds = 60) {
  for (let i = 0; i < seconds * 10; i++) {
    if (await tab.evaluate(test)) return;
    await sleep(100);
  }
  throw new Error(`timed out waiting for ${what}`);
}

// An empty folder, so no shot from an earlier run is left behind.
function empty(dir: string) {
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
}

// A tab that keeps page errors, so a broken build fails loudly.
async function open(browser: Browser, width: number, height: number) {
  const tab = await browser.newPage();
  const errors: string[] = [];
  tab.on("pageerror", (e) => errors.push(e instanceof Error ? e.message : String(e)));
  await tab.setViewport({ width, height, deviceScaleFactor: 1 });
  return { tab, errors };
}

// A shot once two agree, as Chrome composites on its own clock.
async function settled(tab: Page) {
  let last = Buffer.from(await tab.screenshot());
  for (let i = 0; i < 6; i++) {
    await sleep(150);
    const next = Buffer.from(await tab.screenshot());
    if (next.equals(last)) return next;
    last = next;
  }
  throw new Error("the frame never settled");
}

// Advances virtual time and shoots when the step is named.
type Step = (ms: number, name?: string) => Promise<void>;

// The tour on the software renderer and the fake clock, for the steps.
async function session(url: string, dir: string, steps: (tab: Page, step: Step) => Promise<void>) {
  empty(dir);
  const browser = await puppeteer.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  try {
    const { tab, errors } = await open(browser, 1280, 720);
    await tab.evaluateOnNewDocument(clock);
    await tab.goto(url);
    await until(tab, () => document.fonts.status === "loaded" && !!document.querySelector(".topbar"), "the tour");
    // Labels drawn in the page, as Chrome offsets moving layers at random.
    await tab.addStyleTag({ content: ".label3d { will-change: auto !important; }" });
    // CSS transitions run on the browser's clock, so each step ends them.
    const step: Step = async (ms, name) => {
      await tab.evaluate((ms) => {
        window.__advance(ms);
        for (const a of document.getAnimations()) if (a.effect?.getComputedTiming().endTime !== Infinity) a.finish();
      }, ms);
      if (name) fs.writeFileSync(path.join(dir, `${name}.png`), await settled(tab));
    };
    await steps(tab, step);
    if (errors.length) throw new Error(`the tour threw: ${errors.join("; ")}`);
  } finally {
    await browser.close();
  }
}

// The 13 scenes: scene 0 at 3 s, then 4 s after each ArrowRight.
const tour = (url: string, dir: string) =>
  session(url, dir, async (tab, step) => {
    await step(3000, "scene-00");
    for (let s = 1; s < 13; s++) {
      await tab.keyboard.press("ArrowRight");
      await step(4000, `scene-${String(s).padStart(2, "0")}`);
    }
  });

// Clicks a selector's match, or the scene's button starting with words.
const press = (tab: Page, target: string) =>
  tab.evaluate((target) => {
    const buttons = [...document.querySelectorAll<HTMLElement>(".controls.on button, aside.card:not([hidden]) button")];
    const found = target.startsWith(".")
      ? document.querySelector<HTMLElement>(target)
      : buttons.find((b) => b.textContent?.trim().startsWith(target));
    if (!found) throw new Error(`nothing to press for ${target}`);
    found.click();
  }, target);

// Sets a slider or a search box as if dragged or typed.
const enter = (tab: Page, selector: string, value: string | number) =>
  tab.evaluate(
    (selector, value) => {
      const input = document.querySelector<HTMLInputElement>(selector)!;
      input.value = String(value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    },
    selector,
    value,
  );

// Every scene's controls in turn, then the overview and the help.
const controls = (url: string, dir: string) =>
  session(url, dir, async (tab, step) => {
    // The next scene, then time for it to open.
    const next = async (ms: number) => {
      await tab.keyboard.press("ArrowRight");
      await step(ms);
    };
    // A key the tour answers, then time, and a shot when named.
    const key = async (name: "o" | "Escape" | "?", ms: number, shot?: string) => {
      await tab.keyboard.press(name);
      await step(ms, shot);
    };
    await step(3000);
    await next(4000);
    await enter(tab, "#month", 30);
    await step(1500, "universe-month");
    await enter(tab, ".controls.on .search", "NV");
    await step(300);
    await press(tab, ".controls.on .search + div button");
    await step(1500, "universe-card");
    await press(tab, "Close");
    await next(2000);
    await press(tab, "4 Ranked");
    await step(2500, "idea-ranked");
    await press(tab, "6 Balanced");
    await step(2500, "idea-balanced");
    await press(tab, "Replay");
    await step(6000, "idea-replay");
    await next(4000);
    await press(tab, "2022");
    await step(2500, "race-2022");
    await press(tab, "All years");
    await step(2500);
    await press(tab, "Draw again");
    await step(7000, "race-drawn");
    await next(4000);
    await enter(tab, "#beta-month", 20);
    await step(1500, "neutral-month");
    await next(6000);
    await step(0, "costs-fallen");
    await press(tab, "Break-even");
    await step(2000, "costs-break-even");
    await enter(tab, "#cost-multiple", 2.5);
    await step(500, "costs-slider");
    await next(9000);
    await step(0, "edge-landed");
    await press(tab, "Drop them again");
    await step(3000, "edge-dropped");
    await next(8000);
    await step(0, "capacity-swept");
    await enter(tab, "#capital", 8.5);
    await step(500, "capacity-slider");
    await press(tab, "Sweep");
    await step(2500, "capacity-sweeping");
    await next(4000);
    await press(tab, "Momentum");
    await step(2000, "crowd-momentum");
    await next(4000);
    await next(4000);
    await press(tab, ".controls.on .chip");
    await step(1500, "september-card");
    await press(tab, "Close");
    await next(4000);
    await press(tab, "Shippable");
    await step(2000, "honesty-shippable");
    await next(6000);
    await step(0, "finale-printed");
    await press(tab, "Show the particles");
    await step(1000, "finale-particles");
    await key("o", 1200, "overview");
    await key("Escape", 600);
    await key("?", 600, "help");
    await key("Escape", 600, "closed");
  });

// The ad in record mode on the GPU: cues, camera path, then 40 stills.
async function ad(file: string, dir: string) {
  empty(dir);
  const browser = await puppeteer.launch({ args: ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"] });
  // One tab per size, sized before the page loads, as the recorder does.
  const load = async (width: number, height: number) => {
    const opened = await open(browser, width, height);
    await opened.tab.goto(`file://${file}?record`);
    await until(opened.tab, () => window.__ready === true, "the ad");
    return opened;
  };
  try {
    const { tab, errors } = await load(1280, 720);
    const cues = await tab.evaluate(() => ({ length: window.__length, ...window.__cues }));
    fs.writeFileSync(path.join(dir, "cues.json"), JSON.stringify(cues, null, 1));
    const camera = await tab.evaluate(() =>
      Array.from({ length: Math.round(window.__length * 60) }, (_, f) => window.__camera(f / 60)),
    );
    fs.writeFileSync(path.join(dir, "camera.json"), JSON.stringify(camera));
    for (const [width, height] of SIZES) {
      const still = await load(width, height);
      for (const t of MOMENTS) {
        await still.tab.evaluate((t) => window.__draw(t, 16, 60, 0.5), t);
        await still.tab.screenshot({ path: path.join(dir, `still-${width}x${height}-${t}.png`) });
      }
      errors.push(...still.errors);
    }
    if (errors.length) throw new Error(`the ad threw: ${errors.join("; ")}`);
  } finally {
    await browser.close();
  }
}

// The approved site, extracted from git and installed once.
function baseSite() {
  const site = path.join(BASE, "site");
  if (fs.existsSync(path.join(site, "node_modules"))) return site;
  empty(BASE);
  const archive = execFileSync("git", ["archive", BASELINE, "site"], { cwd: REPO, maxBuffer: 1 << 30 });
  execFileSync("tar", ["-x", "-C", BASE], { input: archive });
  fs.symlinkSync(path.join(REPO, "cache"), path.join(BASE, "cache"));
  console.log(`installing the ${BASELINE} site in out/proof/base`);
  run("pnpm", ["install", "--frozen-lockfile", "--prefer-offline", "--ignore-scripts"], {
    cwd: site,
    env: { PUPPETEER_SKIP_DOWNLOAD: "1" },
  });
  return site;
}

// Builds a site in a mode into a folder, leaving out/ and dist/ alone.
function build(site: string, mode: string, dir: string) {
  const args = ["build", ...(mode ? ["--mode", mode] : []), "--outDir", dir, "--emptyOutDir", "--logLevel", "error"];
  run(path.join(site, "node_modules", ".bin", "vite"), args, { cwd: site });
}

// The ad's score and voice mix, from a site's own score.py and voice.
function score(site: string, cues: string, dir: string) {
  fs.mkdirSync(dir, { recursive: true });
  run("uv", ["run", "--quiet", path.join(site, "ad", "score.py"), cues, path.join(site, "ad", "voice"), dir], {
    cwd: REPO,
  });
}

// The pixels two shots differ by, with a mask of them when any do.
async function differ(a: string, b: string, mask: string) {
  if (!fs.existsSync(b)) return "missing";
  const [x, y] = await Promise.all(
    [a, b].map((f) => sharp(f).ensureAlpha().raw().toBuffer({ resolveWithObject: true })),
  );
  if (!x || !y || x.info.width !== y.info.width || x.info.height !== y.info.height) return "another size";
  const marks = Buffer.alloc(x.info.width * x.info.height);
  let count = 0;
  for (let i = 0; i < marks.length; i++) {
    if (x.data.readUInt32BE(i * 4) !== y.data.readUInt32BE(i * 4)) {
      marks[i] = 255;
      count++;
    }
  }
  if (!count) return 0;
  await sharp(marks, { raw: { width: x.info.width, height: x.info.height, channels: 1 } })
    .png()
    .toFile(mask);
  return `${count} px`;
}

// Whether two files hold the same bytes.
const same = (a: string, b: string) => fs.existsSync(b) && fs.readFileSync(a).equals(fs.readFileSync(b));

// Runs the parts asked for, all when none; returns how many differ.
export async function proof(args: string[]) {
  const fresh = args.includes("--fresh");
  const parts = args.filter((f) => !f.startsWith("--"));
  // Naming no part runs every part.
  const want = (part: string) => parts.length === 0 || parts.includes(part);
  const failures: string[] = [];

  // Prints one check's outcome and keeps a failure.
  const report = (name: string, ok: boolean, detail = "") => {
    console.log(`${ok ? "same     " : "DIFFERENT"}  ${name}${detail ? `  (${detail})` : ""}`);
    if (!ok) failures.push(name);
  };

  // Compares every baseline shot with the same shot now.
  const shots = async (name: string, baseDir: string, nowDir: string) => {
    const files = fs.readdirSync(baseDir).filter((f) => f.endsWith(".png") && !f.startsWith("diff-"));
    const changed: string[] = [];
    for (const file of files.sort()) {
      const result = await differ(path.join(baseDir, file), path.join(nowDir, file), path.join(nowDir, `diff-${file}`));
      if (result) changed.push(`${file} ${result}`);
    }
    report(`${name}, ${files.length} shots`, files.length > 0 && !changed.length, changed.join(", "));
  };

  // Times one part of the proof.
  const timed = async (name: string, work: () => Promise<void>) => {
    const start = Date.now();
    console.log(`\n${name}`);
    await work();
    console.log(`  ${Math.round((Date.now() - start) / 1000)} s`);
  };

  // The approved offline file against the offline file and /tour/ now.
  if (want("tour"))
    await timed("tour", async () => {
      const results = path.join(BASE, "results", "tour");
      if (fresh || !fs.existsSync(path.join(results, "scene-12.png"))) {
        build(baseSite(), "", path.join(BASE, "out", "site"));
        await tour(`file://${path.join(BASE, "out", "site", "fiam.html")}#0`, results);
      }
      build(SITE, "offline", path.join(NOW, "site"));
      await tour(`file://${path.join(NOW, "site", "fiam.html")}#0`, path.join(NOW, "tour-offline"));
      await shots("tour, offline file", results, path.join(NOW, "tour-offline"));
      build(SITE, "", path.join(NOW, "dist"));
      const server = await serve(path.join(NOW, "dist"));
      try {
        await tour(`${server.url}/tour/#0`, path.join(NOW, "tour-web"));
      } finally {
        server.close();
      }
      await shots("tour, website", results, path.join(NOW, "tour-web"));
    });

  // The approved offline file against now, through every control.
  if (want("controls"))
    await timed("controls", async () => {
      const results = path.join(BASE, "results", "controls");
      const base = path.join(BASE, "out", "site", "fiam.html");
      if (fresh || !fs.existsSync(path.join(results, "closed.png"))) {
        if (fresh || !fs.existsSync(base)) build(baseSite(), "", path.dirname(base));
        await controls(`file://${base}#0`, results);
      }
      build(SITE, "offline", path.join(NOW, "site"));
      await controls(`file://${path.join(NOW, "site", "fiam.html")}#0`, path.join(NOW, "controls"));
      await shots("controls, offline file", results, path.join(NOW, "controls"));
    });

  // The ad: cues, camera and stills, then the score made from the cues.
  if (want("ad"))
    await timed("ad", async () => {
      const results = path.join(BASE, "results", "ad");
      if (fresh || !fs.existsSync(path.join(results, "score", "music.wav"))) {
        const site = baseSite();
        build(site, "film", path.join(BASE, "out", "film"));
        await ad(path.join(BASE, "out", "film", "film.html"), results);
        score(site, path.join(results, "cues.json"), path.join(results, "score"));
      }
      const now = path.join(NOW, "ad");
      build(SITE, "film", path.join(NOW, "film"));
      await ad(path.join(NOW, "film", "film.html"), now);
      for (const file of ["cues.json", "camera.json"])
        report(`ad, ${file}`, same(path.join(results, file), path.join(now, file)));
      await shots("ad, stills", results, now);
      score(SITE, path.join(now, "cues.json"), path.join(now, "score"));
      for (const file of ["mix.wav", "music.wav"])
        report(`ad, ${file}`, same(path.join(results, "score", file), path.join(now, "score", file)));
    });

  // The two finished films, byte for byte.
  if (want("videos"))
    await timed("videos", async () => {
      for (const [file, sum] of Object.entries(VIDEOS)) {
        const at = path.join(REPO, file);
        if (!fs.existsSync(at)) {
          report(file, false, "missing");
          continue;
        }
        const hash = crypto.createHash("sha256");
        for await (const chunk of fs.createReadStream(at)) hash.update(chunk);
        report(file, hash.digest("hex") === sum);
      }
    });

  console.log(failures.length ? `\n${failures.length} check(s) differ` : "\nall the same");
  return failures.length;
}
