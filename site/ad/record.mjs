// Records the ad from the built page, one exact frame at a time, and pipes the frames to ffmpeg. Each
// frame is the average of several subframes, for motion blur, depth of field and smooth edges.
//
//   node ad/record.mjs cues out/ad/cues.json
//   node ad/record.mjs camera 60 out/ad/camera.json
//   node ad/record.mjs video 1920x1080 60 16 out/ad/master.mp4
import { spawn } from "node:child_process";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer";

const page = fileURLToPath(new URL("../../out/film/film.html", import.meta.url));
const [mode, ...rest] = process.argv.slice(2);
const browser = await puppeteer.launch({
  headless: true,
  args: ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"],
});
const tab = await browser.newPage();
const [width, height] = mode === "video" ? rest[0].split("x").map(Number) : [1280, 720];
await tab.setViewport({ width, height, deviceScaleFactor: 1 });
const errors = [];
tab.on("pageerror", (e) => errors.push(e.message));
await tab.goto(`file://${page}?record`);
await tab.waitForFunction(() => window.__ready === true, { timeout: 60000 });

if (mode === "camera") {
  const fps = Number(rest[0]);
  const length = await tab.evaluate(() => window.__length);
  const path = await tab.evaluate(
    (length, fps) => Array.from({ length: Math.round(length * fps) }, (_, f) => window.__camera(f / fps)),
    length,
    fps,
  );
  fs.writeFileSync(rest[1], JSON.stringify(path));
} else if (mode === "cues") {
  const cues = await tab.evaluate(() => ({ length: window.__length, ...window.__cues }));
  fs.writeFileSync(rest[0], JSON.stringify(cues, null, 1));
} else {
  const [, fpsArg, subArg, out] = rest;
  const fps = Number(fpsArg);
  const length = await tab.evaluate(() => window.__length);
  const cdp = await tab.createCDPSession();
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
  for (let f = 0; f < total; f++) {
    await tab.evaluate((t, n, fps) => window.__draw(t, n, fps, 0.5), f / fps, Number(subArg), fps);
    const { data } = await cdp.send("Page.captureScreenshot", { format: "jpeg", quality: 95, optimizeForSpeed: true });
    if (!ff.stdin.write(Buffer.from(data, "base64"))) await new Promise((r) => ff.stdin.once("drain", r));
    if (f % (fps * 10) === 0)
      console.log(`${width}x${height}: frame ${f} of ${total}, ${Math.round((Date.now() - start) / 1000)}s`);
  }
  ff.stdin.end();
  await new Promise((r) => ff.on("close", r));
  console.log(`${width}x${height}: ${total} frames in ${Math.round((Date.now() - start) / 1000)}s`);
}
await browser.close();
if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
