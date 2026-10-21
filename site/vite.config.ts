import { createHash } from "node:crypto";
import { createReadStream, existsSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { extname, join, sep, resolve as within } from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { type Connect, createServer, defineConfig, type Plugin, type UserConfig, type ViteDevServer } from "vite";
import { encode, QrCodeDataType } from "uqr";
import { viteSingleFile } from "vite-plugin-singlefile";
import { CARD, headersFile, LISTED, localHeadersFor, ORIGIN, readHeaders } from "./scripts/headers.ts";
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

// The film's copies from out/media at /media, in ranges, as R2 serves.
const media = (): Plugin => {
  const root = fileURLToPath(new URL("../out/media", import.meta.url));
  const types: Record<string, string> = { ".mp4": "video/mp4" };
  const serve = (server: { middlewares: Connect.Server }) => {
    server.middlewares.use("/media", (req, res, next) => {
      const file = join(root, decodeURIComponent(new URL(req.url ?? "/", "http://site").pathname));
      if (!file.startsWith(root + sep) || !existsSync(file) || statSync(file).isDirectory()) return next();
      const size = statSync(file).size;
      // A video asks for parts; a range past the end is refused.
      const asked = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range ?? "");
      const from = asked?.[1] ? Number(asked[1]) : asked?.[2] ? size - Number(asked[2]) : 0;
      const to = asked?.[1] && asked[2] ? Math.min(Number(asked[2]), size - 1) : size - 1;
      if (asked && (from > to || from >= size)) {
        res.writeHead(416, { "content-range": `bytes */${size}` });
        return void res.end();
      }
      res.writeHead(asked ? 206 : 200, {
        "content-type": types[extname(file)] ?? "application/octet-stream",
        "content-length": to - from + 1,
        "accept-ranges": "bytes",
        // Every name carries its print, so a copy may be kept forever.
        "cache-control": "public, max-age=31536000, immutable",
        ...(asked && { "content-range": `bytes ${from}-${to}/${size}` }),
      });
      createReadStream(file, { start: from, end: to })
        .on("error", () => res.destroy())
        .pipe(res);
    });
  };
  return { name: "media", configureServer: serve, configurePreviewServer: serve };
};

// The page fade opt-in. Chrome reads it as the body starts, so inline.
const FADE = "<style>@media (prefers-reduced-motion: no-preference) { @view-transition { navigation: auto; } }</style>";

// Previews, robots, the sitemap and the headers the live site needs.
const launch = (): Plugin => {
  let outDir = "";
  return {
    name: "launch",
    configResolved: (config) => void (outDir = within(config.root, config.build.outDir)),
    // Every page opts in to the fade; listed ones get a share card too.
    transformIndexHtml: {
      order: "post",
      handler(html, ctx) {
        const address = ctx.path.replace(/index\.html$/, "");
        html = html.replace("</head>", `  ${FADE}\n  </head>`);
        if (!LISTED.includes(address)) {
          return html.replace("</head>", '  <meta name="robots" content="noindex" />\n  </head>');
        }
        const title = /<title>([^<]*)<\/title>/.exec(html)?.[1] ?? "";
        const words = /<meta\s+name="description"\s+content="([^"]*)"/.exec(html)?.[1] ?? "";
        const [url, image] = [ORIGIN + address, ORIGIN + CARD.path];
        const tags = [
          `<link rel="canonical" href="${url}" />`,
          '<meta property="og:type" content="website" />',
          '<meta property="og:site_name" content="QUARCC Purple" />',
          '<meta property="og:locale" content="en_CA" />',
          `<meta property="og:title" content="${title}" />`,
          `<meta property="og:description" content="${words}" />`,
          `<meta property="og:url" content="${url}" />`,
          `<meta property="og:image" content="${image}" />`,
          `<meta property="og:image:width" content="${CARD.width}" />`,
          `<meta property="og:image:height" content="${CARD.height}" />`,
          `<meta property="og:image:alt" content="${CARD.alt}" />`,
          '<meta name="twitter:card" content="summary_large_image" />',
          `<meta name="twitter:title" content="${title}" />`,
          `<meta name="twitter:description" content="${words}" />`,
          `<meta name="twitter:image" content="${image}" />`,
          `<meta name="twitter:image:alt" content="${CARD.alt}" />`,
        ];
        return html.replace("</head>", `  ${tags.join("\n    ")}\n  </head>`);
      },
    },
    // After the build: headers with each inline script's hash, robots, map.
    writeBundle() {
      const hashes = new Set<string>();
      for (const page of readdirSync(outDir, { recursive: true }).map(String)) {
        if (!page.endsWith(".html")) continue;
        for (const m of readFileSync(join(outDir, page), "utf8").matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
          if (/\bsrc=|application\/json/.test(m[1] ?? "")) continue;
          hashes.add(
            `'sha256-${createHash("sha256")
              .update(m[2] ?? "")
              .digest("base64")}'`,
          );
        }
      }
      writeFileSync(join(outDir, "_headers"), headersFile([...hashes].sort()));
      writeFileSync(join(outDir, "robots.txt"), `User-agent: *\nAllow: /\n\nSitemap: ${ORIGIN}/sitemap.xml\n`);
      const day = new Date().toISOString().slice(0, 10);
      const urls = LISTED.map((p) => `  <url><loc>${ORIGIN}${p}</loc><lastmod>${day}</lastmod></url>`);
      const map = `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join("\n")}\n</urlset>`;
      writeFileSync(join(outDir, "sitemap.xml"), `<?xml version="1.0" encoding="UTF-8"?>\n${map}\n`);
    },
    // The preview serves the headers the live site will, for real tests.
    configurePreviewServer(server) {
      server.middlewares.use((req, res, next) => {
        const file = join(outDir, "_headers");
        if (existsSync(file)) {
          const pathname = new URL(req.url ?? "/", "http://site").pathname;
          for (const [name, value] of localHeadersFor(readHeaders(readFileSync(file, "utf8")), pathname)) {
            res.setHeader(name, value);
          }
        }
        next();
      });
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
    plugins: [pages(), icons(false), qr(), tailwindcss(), launch(), media(), missing()],
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
