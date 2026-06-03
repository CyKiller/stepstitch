#!/usr/bin/env node
/**
 * End-to-end executable-repro proof (plan §7: "run the generated Playwright locally
 * and confirm it executes").
 *
 * Hermetic — no Postgres, no auth, no Marvox stack:
 *   1. Serve a tiny DOM fixture (a page with the selectors a real trace would target).
 *   2. Run the REAL Python compiler (pure stdlib) on a structural footstep set.
 *   3. Execute the generated Playwright spec in headless Chromium against the fixture.
 *   4. Assert it goes green — proving the SDK→compiler→Playwright chain produces a
 *      runnable reproduction, which is the entire product promise.
 *
 * Zero runtime deps; uses the @playwright/test devDep via its CLI and python3 for the
 * compiler + fixture server.
 */
import { execFileSync } from "node:child_process"
import { mkdirSync, writeFileSync, rmSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const here = dirname(fileURLToPath(import.meta.url))
const repo = join(here, "..")
const servicePath = join(repo, "service")
const python = process.env.PYTHON || "python3"
const PORT = Number(process.env.STEPSTITCH_PROOF_PORT || 41737)
const baseUrl = `http://127.0.0.1:${PORT}`

// A structural trace: navigate, click a button, type into a field. These are exactly
// the footstep types the SDK emits (no values, no text — selectors only).
const footsteps = [
  { timestamp: "2026-06-02T00:00:00Z", type: "navigation", route: "/", label: "[masked]" },
  { timestamp: "2026-06-02T00:00:01Z", type: "click", route: "/", target: "#go", label: "[masked]" },
  { timestamp: "2026-06-02T00:00:02Z", type: "input", route: "/", target: "#name", label: "[masked]" },
]

// Work dir lives UNDER the repo so the generated spec + config resolve the
// `@playwright/test` devDep via normal node_modules walk-up. Gitignored + cleaned up.
const work = join(repo, ".stepstitch-proof")
const fixtureDir = join(work, "fixture")
const testsDir = join(work, "tests")
rmSync(work, { recursive: true, force: true })
mkdirSync(fixtureDir, { recursive: true })
mkdirSync(testsDir, { recursive: true })

writeFileSync(
  join(fixtureDir, "index.html"),
  `<!doctype html>
<html><head><meta charset="utf-8"><title>StepStitch fixture</title></head>
<body>
  <h1 id="title">StepStitch fixture</h1>
  <button id="go" onclick="document.getElementById('title').textContent='clicked'">Go</button>
  <input id="name" aria-label="name" />
</body></html>
`,
)

// 2. Run the real compiler. Load it as a package submodule without executing
// stepstitch_service.__init__ (which imports the optional FastAPI router).
const compilerDir = join(servicePath, "stepstitch_service")
const pyCode = [
  "import importlib.util, json, pathlib, sys, types",
  `pkg_dir = pathlib.Path(${JSON.stringify(compilerDir)})`,
  "pkg = types.ModuleType('stepstitch_service')",
  "pkg.__path__ = [str(pkg_dir)]",
  "sys.modules['stepstitch_service'] = pkg",
  "spec = importlib.util.spec_from_file_location('stepstitch_service.compiler', pkg_dir / 'compiler.py')",
  "mod = importlib.util.module_from_spec(spec)",
  "sys.modules['stepstitch_service.compiler'] = mod",
  "spec.loader.exec_module(mod)",
  "sys.stdout.write(mod.generate_playwright_test('trace-proof', json.loads(sys.argv[1]), sys.argv[2]))",
].join("\n")

const generated = execFileSync(
  python,
  ["-c", pyCode, JSON.stringify(footsteps), baseUrl],
  { encoding: "utf8" },
)
writeFileSync(join(testsDir, "repro.spec.ts"), generated)
console.log("--- generated reproduction ---")
console.log(generated)

// 3. Minimal Playwright config that serves the fixture and runs the generated spec.
const cfgPath = join(work, "repro.config.ts")
writeFileSync(
  cfgPath,
  `import { defineConfig } from "@playwright/test"
export default defineConfig({
  testDir: ${JSON.stringify(testsDir)},
  timeout: 30000,
  use: { headless: true },
  webServer: {
    command: ${JSON.stringify(`${python} -m http.server ${PORT} --bind 127.0.0.1 --directory ${fixtureDir}`)},
    url: ${JSON.stringify(`${baseUrl}/index.html`)},
    reuseExistingServer: false,
    timeout: 60000,
  },
})
`,
)

// 4. Execute. Throws (non-zero exit) if the generated repro fails.
try {
  execFileSync(
    "npx",
    ["playwright", "test", "--config", cfgPath, "--reporter=line"],
    { cwd: repo, stdio: "inherit" },
  )
  console.log("\n✅ The generated Playwright reproduction executed green against the fixture.")
} finally {
  rmSync(work, { recursive: true, force: true })
}
