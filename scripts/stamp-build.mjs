#!/usr/bin/env node
/**
 * Stamp the COMPILED build with the current git short SHA (§5b incident forensics).
 *
 * Operates on `dist/` only — source `src/buildinfo.ts` always stays `BUILD_HASH = "dev"`
 * so git never carries a stale hash. Run after `tsc` (see `npm run release`). Idempotent;
 * on a non-git checkout it leaves the value as "dev". Zero dependencies (Node built-ins).
 */
import { execSync } from "node:child_process"
import { existsSync, readFileSync, writeFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { dirname, join } from "node:path"

const here = dirname(fileURLToPath(import.meta.url))
const dist = join(here, "..", "dist")

let hash = "dev"
try {
  hash = execSync("git rev-parse --short HEAD", { stdio: ["ignore", "pipe", "ignore"] })
    .toString()
    .trim() || "dev"
} catch {
  // not a git checkout — keep "dev"
}

// Stamp every emitted module flavor (ESM .js, optional CJS .cjs).
const targets = ["buildinfo.js", "buildinfo.cjs"].map((f) => join(dist, f))
let stamped = 0
for (const target of targets) {
  if (!existsSync(target)) continue
  const src = readFileSync(target, "utf8")
  const next = src.replace(
    /BUILD_HASH\s*=\s*"[^"]*"/,
    `BUILD_HASH = "${hash}"`,
  )
  if (next !== src) {
    writeFileSync(target, next)
    stamped++
  }
}

if (stamped === 0) {
  console.warn("stamp-build: no dist/buildinfo.* found — run `tsc` first")
} else {
  console.log(`stamp-build: BUILD_HASH = ${hash} (${stamped} file(s))`)
}
