#!/usr/bin/env node
/**
 * Diagnostics must not change what they measure.
 *
 * A measurement that alters its subject is not a measurement. Turning tracing on adds a
 * browser-level observer to every action, and it would be entirely possible for that to
 * shift timing enough to change a verdict — a flaky test that passes without tracing and
 * fails with it would quietly corrupt every verdict StepStitch issues.
 *
 * So this runs real reproductions against real Chromium, twice each — diagnostics off, then
 * on — and requires three things to be identical:
 *
 *   1. the verdict            (reproduced / not_reproduced)
 *   2. the frozen script hash (instrumentation must live in the config, never the test)
 *   3. the failure fingerprint (it must fail the SAME way, not merely fail)
 *
 * Shapes are drawn from the same taxonomy as scripts/benchmark_problems.py. The full
 * corpus is 30; this executes a representative subset by default because each case costs
 * two real browser runs. Pass --all for the full sweep.
 *
 *   node scripts/prove-diagnostics-are-inert.mjs [--all]
 */
import { spawn } from 'node:child_process'
import { mkdtempSync, writeFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createServer } from 'node:http'

const ALL = process.argv.includes('--all')

// Same convention as prove-repro-executes.mjs. Hardcoding `.venv/bin/python` works on a
// developer laptop and fails everywhere else: CI installs the package with setup-python and
// has no .venv at all, so the gate meant to prove diagnostics are inert died at spawn.
const PYTHON = process.env.PYTHON || 'python3'

// One shape per failure family the compiler emits, plus depth variation. Each is a real
// page that really breaks — no mocks, because the point is that the browser behaves the
// same either way.
const SHAPES = [
  { id: 'exception-TypeError', kind: 'exception',
    onclick: "throw new TypeError('amount is not a function')" },
  { id: 'exception-RangeError', kind: 'exception',
    onclick: "throw new RangeError('index out of range')" },
  { id: 'api-500', kind: 'api', status: 500 },
  { id: 'api-403', kind: 'api', status: 403 },
  { id: 'api-504', kind: 'api', status: 504 },
  { id: 'passing-control', kind: 'ok' },      // must stay green with tracing on
  ...(ALL ? [
    { id: 'exception-ReferenceError', kind: 'exception',
      onclick: "throw new ReferenceError('x is not defined')" },
    { id: 'exception-DOMException', kind: 'exception',
      onclick: "throw new DOMException('bad node')" },
    { id: 'api-400', kind: 'api', status: 400 },
    { id: 'api-409', kind: 'api', status: 409 },
    { id: 'api-429', kind: 'api', status: 429 },
    { id: 'api-502', kind: 'api', status: 502 },
  ] : []),
]

function pageFor(shape) {
  if (shape.kind === 'ok') {
    return `<!doctype html><html><body><button data-testid=submit
      onclick="document.title='sent'">Send</button></body></html>`
  }
  if (shape.kind === 'exception') {
    return `<!doctype html><html><body><button data-testid=submit
      onclick="${shape.onclick}">Send</button></body></html>`
  }
  return `<!doctype html><html><body><button data-testid=submit
    onclick="fetch('/api/pay',{method:'POST'}).then(r=>{if(!r.ok)
    throw new TypeError('request failed')})">Send</button></body></html>`
}

function specFor(shape, port) {
  const assertion = shape.kind === 'ok'
    ? "expect(pageErrors.length, 'no client error expected').toBe(0);"
    : "expect(pageErrors.some((m) => m.includes('Error')), 'must not reproduce').toBe(false);"
  return `import { test, expect } from '@playwright/test';
test('repro', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (e) => pageErrors.push(\`\${e.name}: \${e.message}\`));
  await page.goto('http://127.0.0.1:${port}/index.html');
  await page.locator('[data-testid=submit]').click();
  await page.waitForTimeout(300);
  ${assertion}
});
`
}

async function serve(shape) {
  const html = pageFor(shape)
  const server = createServer((req, res) => {
    if (req.method === 'POST') {
      res.writeHead(shape.status || 500, { 'content-type': 'application/json' })
      return res.end('{}')
    }
    res.writeHead(200, { 'content-type': 'text/html', 'cache-control': 'no-store' })
    res.end(html)
  })
  await new Promise((r) => server.listen(0, '127.0.0.1', r))
  return { server, port: server.address().port }
}

/**
 * Drive the real runner through Python — the same entry point the product uses.
 *
 * ASYNC on purpose. spawnSync blocks Node's event loop, which means the little HTTP server
 * above cannot answer the browser while the child runs: every page load times out, every
 * verdict comes back `inconclusive`, and the proof passes vacuously because both sides
 * were equally broken. That is exactly the failure this script exists to catch, so it is
 * worth stating plainly rather than quietly awaiting.
 */
async function runOnce(spec, port, diagnostics) {
  const script = `
import json, pathlib, sys
sys.path.insert(0, "service")
from stepstitch_service.runner import run_reproduction
from stepstitch_service.fixcheck import failure_signature
r = run_reproduction(
    session_id="inert", script=${JSON.stringify(spec)},
    base_url="http://127.0.0.1:${port}",
    readiness=[{"id":"base_url","ready":True,"blocking":True,"title":"x","detail":"y"}],
    diagnostics=${diagnostics ? 'True' : 'False'}, timeout_seconds=90,
    project_dir=pathlib.Path("."))
sig = ""
for a in r.runs:
    if not a.passed and a.transcript:
        sig = failure_signature(a.transcript)
        if sig: break
print(json.dumps({"verdict": r.verdict, "sha": r.script_sha256, "sig": sig,
                  "has_diagnostics": bool(r.diagnostics)}))
`
  const work = mkdtempSync(join(tmpdir(), 'inert-'))
  const file = join(work, 'run.py')
  writeFileSync(file, script)
  const { stdout, stderr } = await new Promise((resolve, reject) => {
    const child = spawn(PYTHON, [file])
    let out = '', err = ''
    child.stdout.on('data', (d) => { out += d })
    child.stderr.on('data', (d) => { err += d })
    child.on('error', reject)
    child.on('close', () => resolve({ stdout: out, stderr: err }))
  })
  const line = stdout.trim().split('\n').filter(Boolean).pop()
  if (!line) {
    console.error(stdout, stderr)
    throw new Error('runner produced no result')
  }
  return JSON.parse(line)
}

let failures = 0
mkdirSync('.stepstitch', { recursive: true })
console.log(`\nProving diagnostics are inert across ${SHAPES.length} shapes ` +
            `(${SHAPES.length * 2} real browser runs)\n`)

for (const shape of SHAPES) {
  const { server, port } = await serve(shape)
  const spec = specFor(shape, port)
  const off = await runOnce(spec, port, false)
  const on = await runOnce(spec, port, true)
  server.close()

  const same = off.verdict === on.verdict && off.sha === on.sha && off.sig === on.sig
  if (!same) failures++

  // A run that never happened agrees with itself perfectly. Without this, a broken harness
  // (a blocked event loop, a dead server, a missing browser) reports "inert" while proving
  // nothing at all — which is how the first version of this script passed.
  const expected = shape.kind === 'ok' ? 'not_reproduced' : 'reproduced'
  if (off.verdict !== expected || on.verdict !== expected) {
    console.log(`  FAIL ${shape.id.padEnd(26)} expected ${expected}, got ` +
                `off=${off.verdict} on=${on.verdict} — nothing was measured`)
    failures++
    continue
  }
  const mark = same ? 'ok  ' : 'FAIL'
  console.log(`  ${mark} ${shape.id.padEnd(26)} ${off.verdict.padEnd(15)} ` +
              `hash ${off.sha === on.sha ? 'same' : 'MOVED'}  ` +
              `fingerprint ${off.sig === on.sig ? 'same' : 'CHANGED'}`)
  if (!same) {
    console.log(`       off: ${JSON.stringify(off)}`)
    console.log(`       on : ${JSON.stringify(on)}`)
  }
  // A failing run with diagnostics on must actually have produced them, or this proof is
  // vacuous — it would be trivially "inert" if it collected nothing at all.
  if (on.verdict === 'reproduced' && !on.has_diagnostics) {
    console.log(`  FAIL ${shape.id}: diagnostics were requested but none were collected`)
    failures++
  }
}

if (failures) {
  console.log(`\n${failures} shape(s) behaved differently with diagnostics on.`)
  process.exit(1)
}
console.log('\nDiagnostics are inert: same verdict, same frozen hash, same failure ' +
            'fingerprint,\nand real diagnostics were collected on every failing run.')
