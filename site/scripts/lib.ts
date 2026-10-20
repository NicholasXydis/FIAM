// What the scripts share: paths, running a command, serving a build.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import type { AddressInfo } from "node:net";
import path from "node:path";
import zlib from "node:zlib";

// The site's folder and the repo around it.
export const SITE = path.resolve(import.meta.dirname, "..");
export const REPO = path.resolve(SITE, "..");

// A tool from the site's own packages.
export const bin = (name: string) => path.join(SITE, "node_modules", ".bin", name);

// The site's pages, each with the status it must answer with.
export const PAGES = [
  ["Landing", "/", 200],
  ["Team", "/team/", 200],
  ["Not found", "/no-such-page/", 404],
] as const;

// Waits in real time, even where a page's own clock is faked.
export const sleep = (ms: number) => new Promise<void>((done) => setTimeout(done, ms));

// Where a command runs, what it adds to its env, and if it shows.
interface Options {
  cwd?: string;
  env?: Record<string, string>;
  show?: boolean;
}

// Runs a command, quiet unless asked, and stops on any failure.
export const run = (cmd: string, args: string[], { cwd = SITE, env = {}, show = false }: Options = {}) =>
  execFileSync(cmd, args, {
    cwd,
    stdio: ["ignore", show ? "inherit" : "ignore", "inherit"],
    env: { ...process.env, ...env },
  });

// Content types by extension, so browsers treat files as Pages would.
const TYPES: Record<string, string> = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".avif": "image/avif",
  ".webp": "image/webp",
  ".webmanifest": "application/manifest+json",
  ".mp4": "video/mp4",
  ".vtt": "text/vtt",
};

// The file an address names inside a build, or null when it cannot.
function locate(base: string, url: string) {
  let name: string;
  try {
    name = decodeURIComponent(new URL(url, "http://localhost").pathname);
  } catch {
    return null;
  }
  const file = path.resolve(base, `.${name}`);
  const inside = path.relative(base, file);
  if (inside === ".." || inside.startsWith(`..${path.sep}`) || path.isAbsolute(inside)) return null;
  return fs.existsSync(file) && fs.statSync(file).isDirectory() ? path.join(file, "index.html") : file;
}

// Serves a build on a free local port, missing pages as 404.html.
export async function serve(root: string) {
  const base = path.resolve(root);
  const server = http.createServer((req, res) => {
    let file = locate(base, req.url ?? "/");
    if (file === null) return void res.writeHead(400).end();
    let status = 200;
    if (!fs.existsSync(file)) {
      file = path.join(base, "404.html");
      status = 404;
      if (!fs.existsSync(file)) return void res.writeHead(404).end();
    }
    // A file that fails mid-read ends the reply instead of the server.
    const stream = fs.createReadStream(file).on("error", () => res.destroy());
    const type = TYPES[path.extname(file)] ?? "application/octet-stream";
    // Text goes gzipped when the browser asks, as the real host sends it.
    const zip = /text|javascript|json|svg|manifest/.test(type) && /\bgzip\b/.test(req.headers["accept-encoding"] ?? "");
    res.writeHead(status, {
      "content-type": type,
      ...(zip && { "content-encoding": "gzip", vary: "accept-encoding" }),
    });
    if (zip) stream.pipe(zlib.createGzip()).pipe(res);
    else stream.pipe(res);
  });
  await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
  const { port } = server.address() as AddressInfo;
  return { url: `http://127.0.0.1:${port}`, close: () => server.close() };
}

// Serves a build while some work runs, and stops even if it fails.
export async function served<T>(root: string, work: (url: string) => Promise<T>) {
  const server = await serve(root);
  try {
    return await work(server.url);
  } finally {
    server.close();
  }
}
