import type { KnipConfig } from "knip";

// What knip starts from and may ignore, so it flags only real waste.
const config: KnipConfig = {
  // What no page links: the film, the build's renderer, the scripts.
  entry: ["src/film/main.ts", "src/site/render.tsx", "scripts/*.ts", "ad/record.mjs", "src/*/*.css"],
  project: ["src/**/*.{ts,tsx,css}", "scripts/**/*.ts", "ad/**/*.mjs", "*.ts"],
  // Used where knip cannot look: fonts by CSS url(), Lighthouse by bin().
  ignoreDependencies: [
    "@fontsource-variable/geist",
    "@fontsource-variable/geist-mono",
    "@fontsource/instrument-serif",
    "lighthouse",
  ],
  // Tools the scripts call that come with the system, not with pnpm.
  ignoreBinaries: ["uv", "mdfind"],
};

export default config;
