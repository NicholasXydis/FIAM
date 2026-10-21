// The live site's address, policy and headers, for build and checks.

// Where the site lives, and where the film's copies stream from.
export const ORIGIN = "https://quarccpurple.ca";
export const MEDIA_ORIGIN = "https://media.quarccpurple.ca";
// The addresses search engines may list; the 404 page is not one.
export const LISTED = ["/", "/tour/", "/team/"];
// The share card every page shows when its link is posted.
export const CARD = {
  path: "/og.jpg",
  width: 1200,
  height: 630,
  alt: "QUARCC Purple. A market neutral strategy hedged by AI.",
};

// The content policy: only the site itself, plus R2 for the film.
export function policy(scripts: string[]) {
  return [
    "default-src 'self'",
    `script-src 'self' ${scripts.join(" ")}`.trim(),
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    `media-src 'self' blob: ${MEDIA_ORIGIN}`,
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'none'",
    "frame-ancestors 'none'",
  ].join("; ");
}

// The _headers file Cloudflare reads: safety, and caching for prints.
export function headersFile(scripts: string[]) {
  const all = [
    `Content-Security-Policy: ${policy(scripts)}`,
    "Strict-Transport-Security: max-age=63072000; includeSubDomains",
    "X-Content-Type-Options: nosniff",
    "X-Frame-Options: DENY",
    "Referrer-Policy: strict-origin-when-cross-origin",
    "Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=(), fullscreen=(self)",
    "Cross-Origin-Opener-Policy: same-origin",
  ];
  // Built files and posters carry fingerprints, so they keep forever.
  const forever = "Cache-Control: public, max-age=31536000, immutable";
  return ["/*", ...all.map((h) => `  ${h}`), "/assets/*", `  ${forever}`, "/film/*", `  ${forever}`, ""].join("\n");
}

// Each rule of a _headers file: the paths it covers and its headers.
export function readHeaders(text: string) {
  const rules: { match: RegExp; headers: [string, string][] }[] = [];
  for (const line of text.split("\n")) {
    if (!line.trim() || line.trim().startsWith("#")) continue;
    // An unindented line starts a rule; * matches any run of characters.
    if (!/^\s/.test(line)) {
      const pattern = line
        .trim()
        .replace(/[.+?^${}()|[\]\\]/g, "\\$&")
        .replaceAll("*", ".*");
      rules.push({ match: new RegExp(`^${pattern}$`), headers: [] });
      continue;
    }
    const at = line.indexOf(":");
    rules.at(-1)?.headers.push([line.slice(0, at).trim(), line.slice(at + 1).trim()]);
  }
  return rules;
}

// The headers a path gets, every matching rule in order.
export const headersFor = (rules: ReturnType<typeof readHeaders>, pathname: string) =>
  rules.filter((r) => r.match.test(pathname)).flatMap((r) => r.headers);

// The same for local http servers, minus HTTPS only, which phones keep.
export const localHeadersFor = (rules: ReturnType<typeof readHeaders>, pathname: string) =>
  headersFor(rules, pathname).filter(([name]) => name !== "Strict-Transport-Security");
