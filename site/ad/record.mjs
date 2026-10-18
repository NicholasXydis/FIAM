// Drives the built ad in puppeteer for its cues, camera path or video.
import { spawn } from "node:child_process";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer";

// The page pnpm media page builds, and this run's mode and arguments.
const page = fileURLToPath(new URL("../../out/film/film.html", import.meta.url));
const [mode, ...rest] = process.argv.slice(2);
// Headless Chrome with ANGLE on Metal and the GPU blocklist ignored.
const browser = await puppeteer.launch({
  headless: true,
  args: ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"],
});
// One tab at video's WxH, or 1280x720 for cues and camera, at scale 1.
const tab = await browser.newPage();
const [width, height] = mode === "video" ? rest[0].split("x").map(Number) : [1280, 720];
await tab.setViewport({ width, height, deviceScaleFactor: 1 });
// Page errors are kept, and fail the run once it is done.
const errors = [];
tab.on("pageerror", (e) => errors.push(e.message));
// ?record makes the page expose its hooks; __ready may take up to 60 s.
await tab.goto(`file://${page}?record`);
await tab.waitForFunction(() => window.__ready === true, { timeout: 60000 });

if (mode === "camera") {
  // camera FPS FILE: the camera's position at every frame, for review.py.
  const fps = Number(rest[0]);
  const length = await tab.evaluate(() => window.__length);
  const path = await tab.evaluate(
    (length, fps) => Array.from({ length: Math.round(length * fps) }, (_, f) => window.__camera(f / fps)),
    length,
    fps,
  );
  fs.writeFileSync(rest[1], JSON.stringify(path));
} else if (mode === "cues") {
  // cues FILE: the length and the voice and sound cues, for score.py.
  const cues = await tab.evaluate(() => ({ length: window.__length, ...window.__cues }));
  fs.writeFileSync(rest[0], JSON.stringify(cues, null, 1));
} else {
  // video WxH FPS SUBFRAMES FILE: frame by frame into ffmpeg.
  const [, fpsArg, subArg, out] = rest;
  const fps = Number(fpsArg);
  const length = await tab.evaluate(() => window.__length);
  // Screenshots straight through CDP, as JPEG at quality 95.
  const cdp = await tab.createCDPSession();
  // Full-range BT.601 JPEGs to BT.709 TV range, x264 at CRF 10.
  const ff = spawn(
    process.env.FFMPEG ?? "ffmpeg",
    [
      ...["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "mjpeg", "-i", "-"],
      ...["-vf", "scale=in_range=full:out_range=tv:in_color_matrix=bt601:out_color_matrix=bt709,format=yuv420p"],
      ...["-c:v", "libx264", "-preset", "slow", "-crf", "10", "-r", String(fps), out],
    ],
    { stdio: ["pipe", "inherit", "inherit"] },
  );
  const total = Math.round(length * fps);
  const start = Date.now();
  // Each frame the mean of SUBFRAMES samples, shutter open half a frame.
  for (let f = 0; f < total; f++) {
    await tab.evaluate((t, n, fps) => window.__draw(t, n, fps, 0.5), f / fps, Number(subArg), fps);
    const { data } = await cdp.send("Page.captureScreenshot", { format: "jpeg", quality: 95, optimizeForSpeed: true });
    // Waits for ffmpeg to drain whenever its input pipe is full.
    if (!ff.stdin.write(Buffer.from(data, "base64"))) await new Promise((r) => ff.stdin.once("drain", r));
    // A progress line every 10 s of film.
    if (f % (fps * 10) === 0)
      console.log(`${width}x${height}: frame ${f} of ${total}, ${Math.round((Date.now() - start) / 1000)}s`);
  }
  // Ends the pipe and waits for ffmpeg to finish the file.
  ff.stdin.end();
  await new Promise((r) => ff.on("close", r));
  console.log(`${width}x${height}: ${total} frames in ${Math.round((Date.now() - start) / 1000)}s`);
}
// Any page error fails the run, after the browser has closed.
await browser.close();
if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
