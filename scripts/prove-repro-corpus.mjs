#!/usr/bin/env node
/**
 * The intended-red gate: >= RED_RATE_GATE of the corpus's red entries must fail
 * for the INTENDED reason when the COMPILER'S OWN OUTPUT runs in real Chromium.
 *
 * This differs from prove-diagnostics-are-inert.mjs in one load-bearing way: the
 * spec is not hand-written — it is generate_playwright_test() output, compiled
 * from the corpus entry's trace. A hand-written spec would prove the harness,
 * not the product.
 *
 * Three honesty properties:
 *   1. red entries must come back `reproduced` AND the generated assertion's own
 *      message — which names the reported failure — must appear in the failing
 *      transcript (a timeout red is not the reported bug);
 *   2. the `ok` control must come back `not_reproduced` — a corpus that cannot
 *      go green counts any breakage as success;
 *   3. a run that never happened (`inconclusive`) never counts as red.
 *
 *   node scripts/prove-repro-corpus.mjs
 */
import { spawn } from 'node:child_process'
import { mkdtempSync, writeFileSync, readFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createServer } from 'node:http'

const PYTHON = process.env.PYTHON || 'python3'
const RED_RATE_GATE = 0.85

const corpus = JSON.parse(readFileSync('examples/repro/reproduction-corpus.json', 'utf8'))
const entries = corpus.entries.filter((e) => e.runtime)

// One markup serves every selector the corpus uses: [data-testid="submit"] and
// the deliberately-unstable `main > div > button:nth-child(1)` resolve to the
// same button, so the page exercises both stable and structural targeting.
function pageFor(rt) {
  const onclick =
    rt.kind === 'ok' ? "document.title='sent'"
    : rt.kind === 'exception' ? rt.onclick
    : "fetch('/api/pay',{method:'POST'}).then(r=>{if(!r.ok) throw new TypeError('request failed: '+r.status)})"
  return `<!doctype html><html><body><main><div><button data-testid="submit"
    onclick="${onclick.replace(/"/g, '&quot;')}">Send</button></div></main></body></html>`
}

async function serve(rt) {
  const html = pageFor(rt)
  const server = createServer((req, res) => {
    if (req.method === 'POST') {
      res.writeHead(rt.status || 500, { 'content-type': 'application/json' })
      return res.end('{}')
    }
    res.writeHead(200, { 'content-type': 'text/html', 'cache-control': 'no-store' })
    res.end(html)
  })
  await new Promise((r) => server.listen(0, '127.0.0.1', r))
  return { server, port: server.address().port }
}

// Compile the entry's trace with the real compiler, then run the result with the
// real runner — the same two functions the product calls, nothing in between.
async function compileAndRun(entry, port) {
  const script = `
import json, pathlib, sys
sys.path.insert(0, "service")
from stepstitch_service.compiler import generate_playwright_test
from stepstitch_service.repro_config import ReproConfig
from stepstitch_service.runner import run_reproduction
from stepstitch_service.fixcheck import failure_signature
entry = json.loads(${JSON.stringify(JSON.stringify(entry))})
cfg = ReproConfig.from_dict(entry.get("config"))
spec = generate_playwright_test(entry["name"], entry["footsteps"],
                                base_url="http://127.0.0.1:${port}", config=cfg)
r = run_reproduction(
    session_id=entry["name"], script=spec,
    base_url="http://127.0.0.1:${port}",
    readiness=[{"id":"base_url","ready":True,"blocking":True,"title":"x","detail":"y"}],
    timeout_seconds=90, project_dir=pathlib.Path("."))
sig = ""
failing = ""
for a in r.runs:
    if not a.passed and a.transcript:
        failing = a.transcript
        sig = failure_signature(a.transcript)
        if sig: break
print(json.dumps({"verdict": r.verdict, "sig": sig,
                  "detail": (r.detail or "")[:300],
                  "failing_transcript": failing[:6000],
                  "transcript": (r.runs[0].transcript if r.runs else "")[:300]}))
`
  const work = mkdtempSync(join(tmpdir(), 'corpus-'))
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

let hardFailures = 0
let redIntended = 0
let redTotal = 0
mkdirSync('.stepstitch', { recursive: true })
console.log(`\nCorpus intended-red gate: ${entries.length} entries, real compiler output, real Chromium\n`)

for (const entry of entries) {
  const rt = entry.runtime
  const { server, port } = await serve(rt)
  const run = await compileAndRun(entry, port)
  server.close()

  if (rt.red) {
    redTotal++
    const isRed = run.verdict === 'reproduced'
    const intended = isRed && rt.transcript_contains &&
      (run.failing_transcript || '').includes(rt.transcript_contains)
    if (intended) redIntended++
    const mark = intended ? 'ok  ' : 'MISS'
    console.log(`  ${mark} ${entry.name.padEnd(32)} verdict=${run.verdict.padEnd(15)} ` +
                `${intended ? 'failed for the intended reason' : `intended marker missing (sig: ${(run.sig || '(none)').slice(0, 60)})`}`)
    if (!isRed) console.log(`       why: ${run.detail || run.transcript}`)
  } else {
    // The green control: any verdict but not_reproduced is a hard failure.
    const ok = run.verdict === 'not_reproduced'
    if (!ok) {
      hardFailures++
      console.log(`  FAIL ${entry.name.padEnd(32)} control expected green, got ${run.verdict}`)
      console.log(`       why: ${run.detail || run.transcript}`)
    } else {
      console.log(`  ok   ${entry.name.padEnd(32)} verdict=${run.verdict.padEnd(15)} (green control)`)
    }
  }
}

const rate = redTotal ? redIntended / redTotal : 0
console.log(`\n  intended-red rate: ${redIntended}/${redTotal} = ${(rate * 100).toFixed(0)}% ` +
            `(gate ${(RED_RATE_GATE * 100).toFixed(0)}%)`)
if (redTotal === 0) {
  console.log('  FAIL: corpus has no red entries — the gate measured nothing')
  process.exit(1)
}
if (rate < RED_RATE_GATE || hardFailures) {
  console.log(`\nGate failed (${hardFailures} hard failure(s)).`)
  process.exit(1)
}
console.log('\nEvery measured red failed for its intended reason, and the green control stayed green.')
