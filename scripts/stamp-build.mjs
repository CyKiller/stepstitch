#!/usr/bin/env node
/**
 * Stamp src/buildinfo.ts with the current git short SHA (§5b incident forensics).
 *
 * Idempotent: rewrites BUILD_HASH to the resolved hash, leaving the rest untouched. On
 * a non-git checkout (e.g. a published tarball rebuild) it leaves the value as "dev".
 * Zero dependencies — uses only Node built-ins.
 */
import { execSync } from "node:child_process"
import { readFileSync, writeFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { dirname, join } from "node:path"

const here = dirname(fileURLToPath(import.meta.url))
const target = join(here, "..", "src", "buildinfo.ts")

let hash = "dev"
try {
  hash = execSync("git rev-parse --short HEAD", { stdio: ["ignore", "pipe", "ignore"] })
    .toString()
    .trim() || "dev"
} catch {
  // not a git checkout — keep "dev"
}

const src = readFileSync(target, "utf8")
const next = src.replace(
  /export const BUILD_HASH = "[^"]*"/,
  `export const BUILD_HASH = "${hash}"`,
)
if (next !== src) {
  writeFileSync(target, next)
  console.log(`stamp-build: BUILD_HASH = ${hash}`)
} else {
  console.log(`stamp-build: BUILD_HASH already ${hash}`)
}
