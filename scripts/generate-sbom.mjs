#!/usr/bin/env node
/**
 * Emit a CycloneDX SBOM for the SDK (§5b vendor sign-off artifact).
 *
 * The SDK has ZERO runtime dependencies, so the SBOM is intentionally a single
 * component: the package itself. This is the whole point — a one-line bill of materials
 * is the smallest possible CVE/audit surface. Zero dependencies here too (Node built-ins
 * only), so generating the SBOM cannot itself introduce supply-chain risk.
 *
 * Output: sbom.cdx.json (CycloneDX 1.5).
 */
import { execSync } from "node:child_process"
import { readFileSync, writeFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { dirname, join } from "node:path"

const here = dirname(fileURLToPath(import.meta.url))
const root = join(here, "..")
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"))

let commit = "unknown"
try {
  commit = execSync("git rev-parse HEAD", { stdio: ["ignore", "pipe", "ignore"] })
    .toString()
    .trim() || "unknown"
} catch {
  /* not a git checkout */
}

const runtimeDeps = Object.keys(pkg.dependencies ?? {})
if (runtimeDeps.length > 0) {
  console.error(
    `generate-sbom: expected ZERO runtime dependencies, found ${runtimeDeps.length}: ` +
      runtimeDeps.join(", "),
  )
  process.exit(1)
}

const purl = `pkg:npm/${pkg.name.replace(/@/g, "%40")}@${pkg.version}`
const sbom = {
  bomFormat: "CycloneDX",
  specVersion: "1.5",
  version: 1,
  metadata: {
    timestamp: new Date().toISOString(),
    tools: [{ vendor: "StepStitch", name: "generate-sbom.mjs" }],
    component: {
      type: "library",
      "bom-ref": purl,
      name: pkg.name,
      version: pkg.version,
      description: pkg.description,
      purl,
      properties: [{ name: "vcs:commit", value: commit }],
    },
  },
  // Zero runtime dependencies → no further components.
  components: [],
  dependencies: [{ ref: purl, dependsOn: [] }],
}

const out = join(root, "sbom.cdx.json")
writeFileSync(out, JSON.stringify(sbom, null, 2) + "\n")
console.log(`generate-sbom: wrote ${out} (${runtimeDeps.length} runtime deps)`)
