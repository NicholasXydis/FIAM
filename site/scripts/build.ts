// Builds the website into dist/ and the offline tour into out/site/.
import { bin, run } from "./lib.ts";

// Both type checks: the tour's side, then the stricter site.
export function types() {
  run(bin("tsc"), ["--noEmit"], { show: true });
  run(bin("tsc"), ["--noEmit", "-p", "tsconfig.site.json"], { show: true });
}

// The website, then the offline tour, without the type checks.
export function bundle() {
  run(bin("vite"), ["build", "--logLevel", "warn"], { show: true });
  run(bin("vite"), ["build", "--mode", "offline", "--logLevel", "warn"], { show: true });
}

// pnpm build: a type error stops it before anything is written.
export function build() {
  types();
  bundle();
}

// Run as a script: build both and say where they went.
if (process.argv[1] === import.meta.filename) {
  build();
  console.log("built dist/ and out/site/fiam.html");
}
