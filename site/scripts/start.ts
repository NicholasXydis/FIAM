// From a fresh clone: installs what is missing, builds, opens the site.
import { execFileSync, spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { bin, SITE } from "./lib.ts";

// A command's answer, or null when it is not installed.
const ask = (cmd: string, args: string[]) => {
  try {
    return execFileSync(cmd, args, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return null;
  }
};

// pnpm checks Node before this runs; uv only refreshes data and videos.
console.log(`Node ${process.versions.node}, pnpm ${ask("pnpm", ["--version"])}`);
if (!ask("uv", ["--version"]))
  console.log("uv is missing: only pnpm data and pnpm media video need it (docs.astral.sh/uv).");

// Installs the locked packages when missing or older than the lockfile.
const lock = path.join(SITE, "pnpm-lock.yaml");
const stamp = path.join(SITE, "node_modules", ".modules.yaml");
if (!fs.existsSync(stamp) || fs.statSync(stamp).mtimeMs < fs.statSync(lock).mtimeMs) {
  console.log("installing the locked packages");
  execFileSync("pnpm", ["install", "--frozen-lockfile"], { cwd: SITE, stdio: "inherit" });
}

// Builds, then serves the build and opens it until stopped.
const { build } = await import("./build.ts");
build();
spawn(bin("vite"), ["preview", "--open", "--port", "4173"], { cwd: SITE, stdio: "inherit" });
