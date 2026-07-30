#!/usr/bin/env node
/**
 * The runner, proven against real Playwright — not a fake subprocess.
 *
 * service/tests/test_runner.py proves the security properties with a stand-in runner, so
 * they hold on any machine. This proves the other half: that runner.py actually drives
 * Playwright, and that the verdict it derives matches reality on a page that is really
 * broken and then really fixed.
 *
 *   1. Serve a fixture whose button does NOT update the page (the bug).
 *   2. Compile a reproduction from structural footsteps, freeze it.
 *   3. Run it -> must be `reproduced`.
 *   4. Serve the FIXED fixture, rerun the byte-identical frozen script -> `not_reproduced`.
 *   5. Try to rerun an edited script -> must be refused.
 *
 * Step 5 is the referee property: an agent may change the app, never the test.
 */
import { execFileSync, spawn } from "node:child_process"
import { mkdirSync, writeFileSync, rmSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const here = dirname(fileURLToPath(import.meta.url))
const repo = join(here, "..")
const servicePath = join(repo, "service")
const python = process.env.PYTHON || "python3"
const PORT = Number(process.env.STEPSTITCH_RUNNER_PROOF_PORT || 41739)
const baseUrl = `http://127.0.0.1:${PORT}`

const footsteps = [
  { timestamp: "2026-07-30T00:00:00Z", type: "navigation", route: "/", label: "[masked]" },
  { timestamp: "2026-07-30T00:00:01Z", type: "click", route: "/", target: "#go", label: "[masked]" },
]

const work = join(repo, ".stepstitch-runner-proof")
const fixtureDir = join(work, "fixture")
rmSync(work, { recursive: true, force: true })
mkdirSync(fixtureDir, { recursive: true })

const page = (broken) => `<!doctype html>
<html><head><meta charset="utf-8"><title>StepStitch fixture</title></head>
<body>
  <h1 id="title">StepStitch fixture</h1>
  <button id="go" onclick="${broken ? "/* the bug: nothing happens */" : "document.getElementById('title').textContent='clicked'"}">Go</button>
</body></html>
`

function writeFixture(broken) {
  writeFileSync(join(fixtureDir, "index.html"), page(broken))
}

// A test that asserts the WORKING behavior: it fails while the bug is present.
const spec = `import { test, expect } from "@playwright/test"

test("the button updates the page", async ({ page }) => {
  await page.goto("${baseUrl}/index.html")
  await page.click("#go")
  await expect(page.locator("#title")).toHaveText("clicked", { timeout: 3000 })
})
`

function runViaRunner({ script, expected }) {
  // Load runner.py directly, WITHOUT executing stepstitch_service/__init__.py (which
  // imports the FastAPI router). That is not a workaround: the runner is designed to work
  // in an environment that has Node and Playwright but no web stack, and loading it this
  // way proves it — this script runs under a bare python3 with no fastapi installed.
  const code = [
    "import importlib.util, json, pathlib, sys, types",
    `pkg_dir = pathlib.Path(${JSON.stringify(join(servicePath, "stepstitch_service"))})`,
    "pkg = types.ModuleType('stepstitch_service'); pkg.__path__ = [str(pkg_dir)]",
    "sys.modules['stepstitch_service'] = pkg",
    "spec = importlib.util.spec_from_file_location('stepstitch_service.runner', pkg_dir / 'runner.py')",
    "mod = importlib.util.module_from_spec(spec)",
    "sys.modules['stepstitch_service.runner'] = mod",
    "spec.loader.exec_module(mod)",
    "run_reproduction = mod.run_reproduction",
    "RunnerError = mod.RunnerError",
    "script = sys.stdin.read()",
    "expected = sys.argv[1] or None",
    "try:",
    "    r = run_reproduction(session_id='proof', script=script,",
    `        base_url=${JSON.stringify(baseUrl)}, expected_sha256=expected,`,
    "        readiness=[{'id':'base_url','ready':True,'title':'base','detail':'ok'}],",
    `        timeout_seconds=60, project_dir=${JSON.stringify(repo)})`,
    "    print(json.dumps({'ok': True, 'result': r.as_dict()}))",
    "except RunnerError as exc:",
    "    print(json.dumps({'ok': False, 'refused': str(exc)}))",
  ].join("\n")
  const out = execFileSync(python, ["-c", code, expected || ""], {
    input: script, encoding: "utf8", cwd: repo,
  })
  return JSON.parse(out)
}

// A no-store fixture server. `python -m http.server` honors If-Modified-Since, and the
// broken and fixed pages are written within the same second, so Chromium would be handed
// a 304 and "verify the fix" would silently re-test the bug.
const serverPy = join(work, "serve.py")
writeFileSync(
  serverPy,
  `import functools, http.server, sys

class NoStore(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def send_header(self, key, value):
        if key.lower() == "last-modified":
            return
        super().send_header(key, value)

    def log_message(self, *args):
        pass

handler = functools.partial(NoStore, directory=sys.argv[2])
http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), handler).serve_forever()
`,
)

let server
function serve() {
  server = spawn(python, [serverPy, String(PORT), fixtureDir], { stdio: "ignore" })
}

async function waitForServer() {
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch(`${baseUrl}/index.html`)
      if (res.ok) return
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 250))
  }
  throw new Error("fixture server never came up")
}

function assert(condition, message) {
  if (!condition) throw new Error(`FAILED: ${message}`)
  console.log(`  ok  ${message}`)
}

try {
  writeFixture(true)
  serve()
  await waitForServer()

  const frozen = execFileSync(python, [
    "-c",
    `import hashlib,sys; sys.stdout.write(hashlib.sha256(sys.stdin.read().encode()).hexdigest())`,
  ], { input: spec, encoding: "utf8" })

  console.log("1. the bug is present:")
  const red = runViaRunner({ script: spec, expected: frozen })
  assert(red.ok, "the runner executed Playwright")
  assert(red.result.verdict === "reproduced",
         `verdict is 'reproduced' (got '${red.result.verdict}')`)
  assert(red.result.script_sha256 === frozen, "the digest matches the frozen script")

  console.log("2. the app is fixed, same frozen script:")
  writeFixture(false)
  const green = runViaRunner({ script: spec, expected: frozen })
  assert(green.ok, "the runner executed the byte-identical script again")
  assert(green.result.verdict === "not_reproduced",
         `verdict is 'not_reproduced' (got '${green.result.verdict}')`)

  console.log("3. an edited test is refused:")
  const weakened = spec.replace('toHaveText("clicked"', 'toHaveText(/.*/ ')
  const refused = runViaRunner({ script: weakened, expected: frozen })
  assert(!refused.ok, "the runner refused a script that is not the frozen one")
  assert(/frozen reproduction/.test(refused.refused), "the refusal says why")

  console.log("\n✅ runner: red on the bug, green on the fix, and it cannot be talked out of it.")
} finally {
  if (server) server.kill()
  rmSync(work, { recursive: true, force: true })
}
