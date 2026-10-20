import { existsSync, readFileSync, statSync } from "node:fs";
import { join, resolve as within } from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { createServer, defineConfig, type Plugin, type UserConfig, type ViteDevServer } from "vite";
import { encode, QrCodeDataType } from "uqr";
import { viteSingleFile } from "vite-plugin-singlefile";
import { QR_TEXT } from "./src/content/credits.ts";

// The website; --mode offline makes the one-file USB tour, film the ad.

// Fills each page with the shared head and its React tree as HTML.
const pages = (): Plugin => {
  // The dev server, or a build-time renderer made from the same config.
  let dev: ViteDevServer | undefined;
  let renderer: Promise<ViteDevServer> | undefined;
  let configFile: string | false = false;
  return {
    name: "pages",
    // Remembers the config file and, in dev, the server to render with.
    configResolved: (config) => void (configFile = config.configFile ?? false),
    configureServer: (server) => void (dev = server),
    transformIndexHtml: {
      order: "pre",
      // Fills the head, the app and the Back slot; any left over throws.
      async handler(html, ctx) {
        html = html.replace("<!-- @head -->", readFileSync("partials/head.html", "utf8").trim());
        const page = /data-page="(\w+)"><!-- @app -->/.exec(html)?.[1];
        const back = html.includes("<!-- @back -->");
        // Renders via Vite's SSR: the dev server, or one started for the build.
        if (page || back) {
          const server =
            dev ??
            (await (renderer ??= createServer({
              configFile,
              appType: "custom",
              logLevel: "error",
              server: { middlewareMode: true, hmr: false, watch: null },
            })));
          const site = await server.ssrLoadModule("/src/site/render.tsx");
          // The tour's page gets only the site's Back pill, rendered here.
          if (back) html = html.replace("<!-- @back -->", site["back"]());
          if (page) {
            html = html.replace("<!-- @app -->", site["render"](page));
            // The words the page hydrates with, beside its tree, not in it.
            const json = `<script type="application/json" id="words">${site["words"](page)}</script>`;
            html = html.replace("</body>", `  ${json}\n  </body>`);
          }
        }
        if (html.includes("<!-- @")) throw new Error(`${ctx.path}: a placeholder has nothing to fill it`);
        return html;
      },
    },
    // Closes the build's renderer once the bundle is written.
    closeBundle: async () => {
      await (await renderer)?.close();
      renderer = undefined;
    },
  };
};

// The preview answers a missing page with 404.html, as the host does.
const missing = (): Plugin => ({
  name: "missing",
  configurePreviewServer(server) {
    const root = within(server.config.root, server.config.build.outDir);
    server.middlewares.use((req, res, next) => {
      let path = "/";
      try {
        path = decodeURIComponent(new URL(req.url ?? "/", "http://site").pathname);
      } catch {
        // A malformed address is missing like any other.
      }
      const file = join(root, path);
      const page = existsSync(file) && (!statSync(file).isDirectory() || existsSync(join(file, "index.html")));
      if (file.startsWith(root) && page) return next();
      res.statusCode = 404;
      res.setHeader("content-type", "text/html; charset=utf-8");
      res.end(readFileSync(join(root, "404.html")));
    });
  },
});

// Icon tags for every page: files on the website, inlined SVG offline.
const icons = (inline: boolean): Plugin => ({
  name: "icons",
  transformIndexHtml: (html) =>
    html.replace(
      "<!-- icons -->",
      inline
        ? `<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,${readFileSync("public/favicon.svg").toString("base64")}" />`
        : [
            '<link rel="icon" href="/favicon.ico" sizes="32x32" />',
            '<link rel="icon" type="image/svg+xml" href="/favicon.svg" />',
            '<link rel="apple-touch-icon" href="/apple-touch-icon.png" />',
            '<link rel="manifest" href="/manifest.webmanifest" />',
          ].join("\n    "),
    ),
});

// Encodes the finale's QR at build, so pages get its modules, not uqr.
const qr = (): Plugin => ({
  name: "qr",
  // \0 is Rollup's virtual-module mark, so no plugin looks for a file.
  resolveId: (id) => (id === "virtual:qr" ? "\0virtual:qr" : undefined),
  // virtual:qr's source, encoded at error correction level H, no border.
  load(id) {
    if (id !== "\0virtual:qr") return;
    const code = encode(QR_TEXT, { ecc: "H", border: 0 });
    // The favicon's mark for the centre; a changed favicon fails here.
    const mark = /<g class="t">(.*?)<\/g><g class="m">/s.exec(readFileSync("public/favicon.svg", "utf8"))?.[1];
    if (!mark?.includes("#2a0839")) throw new Error("public/favicon.svg no longer has the mark the QR needs");
    // One string per row: 1 for a dark module, plus 2 inside an eye.
    const rows = code.data.map((row, y) =>
      row.map((dark, x) => Number(dark) + (code.types[y]![x] === QrCodeDataType.Position ? 2 : 0)).join(""),
    );
    // Its dark hole takes the code's centre disc colour, not the favicon's.
    const centre = mark.replaceAll("#2a0839", "#1b1240");
    return `export default ${JSON.stringify(rows)};\nexport const MARK = ${JSON.stringify(centre)};`;
  },
});

// One offline file: all inlined, no public/, its folder not emptied.
const single = (input: string, outDir: string, css: boolean): UserConfig => ({
  plugins: [pages(), icons(true), qr(), ...(css ? [tailwindcss()] : []), viteSingleFile()],
  publicDir: false,
  build: {
    outDir,
    emptyOutDir: false,
    target: "es2022",
    assetsInlineLimit: 100_000_000,
    chunkSizeWarningLimit: 4000,
    rolldownOptions: { input },
  },
});

// The @/ alias, so site code imports from src/ by one path.
const resolve = { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } };

// Which build: the split website, the offline tour or the ad's page.
export default defineConfig(({ mode }) => {
  if (mode === "offline") return single("fiam.html", "../out/site", true);
  if (mode === "film") return single("film.html", "../out/film", false);
  // The website: four pages, three.js and gsap in chunks of their own.
  return {
    plugins: [pages(), icons(false), qr(), tailwindcss(), missing()],
    resolve,
    build: {
      outDir: "dist",
      emptyOutDir: true,
      target: "es2022",
      chunkSizeWarningLimit: 800,
      modulePreload: { polyfill: false },
      rolldownOptions: {
        input: { index: "index.html", tour: "tour/index.html", team: "team/index.html", missing: "404.html" },
        output: {
          codeSplitting: {
            groups: [
              { name: "three", test: /node_modules[\\/]three[\\/]/ },
              { name: "gsap", test: /node_modules[\\/]gsap[\\/]/ },
            ],
          },
        },
      },
    },
  };
});
