// pnpm media [page | icons | video]: the film's page, icons and videos.
import fs from "node:fs";
import path from "node:path";
import sharp from "sharp";
import { bin, REPO, run, SITE } from "./lib.ts";

// The icons' drawing size, and the PurpleFunds purple behind the mark.
const S = 512;
const BG = "#2a0839";
// Detail per size: ray counts and widths, ray start, disc and pupil.
const LEVELS = {
  full: { left: 24, right: 25, wl: 0.018, wr: 0.0105, start: 0.1, disc: 0.068, dot: 0.025 },
  small: { left: 11, right: 13, wl: 0.034, wr: 0.026, start: 0.125, disc: 0.085, dot: 0.032 },
  tiny: { left: 7, right: 8, wl: 0.05, wr: 0.042, start: 0.14, disc: 0.1, dot: 0.04 },
  micro: { left: 5, right: 5, wl: 0.078, wr: 0.07, start: 0.17, disc: 0.125, dot: 0.05 },
};
// One of the four levels, fullest at 512 px to boldest at 16 px.
type Level = keyof typeof LEVELS;
// How much of a square icon the burst spans, edge to edge.
const FILL = 0.84;

// The ad's live page, built into out/film/ beside its soundtrack.
function page() {
  run(bin("vite"), ["build", "--mode", "film", "--logLevel", "warn"], { show: true });
}

// The burst around its eye at the origin, with each corner it draws.
function burst(level: Level) {
  const L = LEVELS[level];
  const rays: [number, number, number][] = [];
  for (let k = 0; k < L.left; k++) rays.push([((98 + (k * 164) / (L.left - 1)) * Math.PI) / 180, 0.255, L.wl]);
  for (let k = 0; k < L.right; k++) {
    const a = ((90 - (k * 180) / (L.right - 1)) * Math.PI) / 180;
    rays.push([a, 0.36 + 0.03 * Math.cos(a), L.wr]);
  }
  const corners = [-1, 1].flatMap((i) => [-1, 1].map((j) => [i * L.disc, j * L.disc] as const));
  const lines = rays.map(([a, r, w]) => {
    const [c, s] = [Math.cos(a), Math.sin(a)];
    for (const q of [L.start, r])
      for (const side of [-1, 1]) corners.push([q * c + (side * w * s) / 2, -q * s + (side * w * c) / 2]);
    return `<line x1="${L.start * c}" y1="${-L.start * s}" x2="${r * c}" y2="${-r * s}" stroke-width="${w}"/>`;
  });
  const body = `<g stroke="#fff">${lines.join("")}</g><circle r="${L.disc}" fill="#fff"/><circle r="${L.dot}" fill="${BG}"/>`;
  return { body, corners };
}

// A square icon on the purple around the layers inside it.
const square = (inner: string) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${S} ${S}"><rect width="${S}" height="${S}" fill="${BG}"/>${inner}</svg>`;

// A burst centred on its outline, or kept in the maskable safe circle.
function centred(level: Level, fill: number, safe = false) {
  const { body, corners } = burst(level);
  const xs = corners.map(([x]) => x);
  const ys = corners.map(([, y]) => y);
  const [mx, my] = [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2];
  const reach = Math.max(...corners.map(([x, y]) => Math.hypot(x - mx, y - my)));
  const k = safe ? 0.39 / reach : fill / Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
  return `<g transform="translate(${(0.5 - k * mx) * S} ${(0.5 - k * my) * S}) scale(${k * S})">${body}</g>`;
}

// The tab icon at 32 px, swapped for the boldest one at 16 px.
const tab = square(
  `<style>.m{display:none}@media (max-width:24px){.t{display:none}.m{display:inline}}</style><g class="t">${centred("tiny", FILL)}</g><g class="m">${centred("micro", FILL)}</g>`,
);

// An ICO file holding PNGs of several sizes.
function ico(pngs: [number, Buffer][]) {
  const head = Buffer.alloc(6 + 16 * pngs.length);
  head.writeUInt16LE(1, 2);
  head.writeUInt16LE(pngs.length, 4);
  let offset = head.length;
  pngs.forEach(([size, data], i) => {
    const e = 6 + 16 * i;
    head.writeUInt8(size % 256, e);
    head.writeUInt8(size % 256, e + 1);
    head.writeUInt16LE(1, e + 4);
    head.writeUInt16LE(32, e + 6);
    head.writeUInt32LE(data.length, e + 8);
    head.writeUInt32LE(offset, e + 12);
    offset += data.length;
  });
  return Buffer.concat([head, ...pngs.map(([, data]) => data)]);
}

// An SVG drawn at an exact pixel size, so small icons stay crisp.
const png = (source: string, size: number) =>
  sharp(Buffer.from(source), { density: (72 * size) / S })
    .resize(size, size)
    .png()
    .toBuffer();

// Every favicon, app icon and the manifest, into public/.
async function icons() {
  const out = path.join(SITE, "public");
  // Each icon lands in public/, which Vite copies to dist/ as is.
  const write = (name: string, data: string | Buffer) => fs.writeFileSync(path.join(out, name), data);
  fs.mkdirSync(out, { recursive: true });
  write("favicon.svg", tab);
  write(
    "favicon.ico",
    ico([
      [16, await png(square(centred("micro", FILL)), 16)],
      [32, await png(square(centred("tiny", FILL)), 32)],
      [48, await png(square(centred("small", FILL)), 48)],
    ]),
  );
  write("apple-touch-icon.png", await png(square(centred("full", FILL)), 180));
  for (const size of [192, 512]) write(`icon-${size}.png`, await png(square(centred("full", FILL)), size));
  write("icon-maskable-512.png", await png(square(centred("full", FILL, true)), 512));
  const manifest = {
    name: "QUARCC Purple",
    short_name: "QUARCC Purple",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    theme_color: BG,
    background_color: BG,
    display: "browser",
  };
  write("manifest.webmanifest", JSON.stringify(manifest, null, 2) + "\n");
  console.log("  favicon.svg, favicon.ico, apple-touch-icon.png, icon-192/512, icon-maskable-512, manifest");
}

// The part asked for; the page and the icons when none is.
const [what = "all", ...rest] = process.argv.slice(2);
if (what === "page" || what === "all") page();
if (what === "icons" || what === "all") await icons();
if (what === "video") run("uv", ["run", path.join("site", "ad", "make.py"), ...rest], { cwd: REPO, show: true });
if (!["all", "page", "icons", "video"].includes(what)) {
  console.log("pnpm media [page | icons | video [--preview]]");
  process.exit(1);
}
