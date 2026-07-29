/**
 * TinyTransfer — a deliberately broken money-transfer app.
 *
 * Its whole job is to be honest about what StepStitch does and does not capture. It takes a
 * recipient account number, an amount and a contact email — the three things you would most
 * regret leaking — sends them over a request carrying a synthetic query parameter, and fails
 * with a 500. What reaches StepStitch is the structure of what happened and nothing else.
 *
 * Node's standard library only. A transfer form and four endpoints do not justify a
 * framework, and the point of this file is that you can read all of it.
 *
 * The ingest token lives HERE, in the server process. The browser posts to /ingest on this
 * same origin; this process forwards to StepStitch with the credential attached. That is the
 * pattern every real integration should use, and it is why the token never reaches page JS.
 */
import { createReadStream, existsSync } from "node:fs"
import { createServer } from "node:http"
import { dirname, extname, join, normalize } from "node:path"
import { fileURLToPath } from "node:url"

const HERE = dirname(fileURLToPath(import.meta.url))
const PUBLIC = join(HERE, "public")
const VENDOR = join(HERE, "node_modules", "@stepstitch", "tracker", "dist")

const PORT = Number(process.env.PORT || 4173)
const STEPSTITCH_HOST = process.env.STEPSTITCH_HOST || "http://localhost:8000"
const INGEST_TOKEN = process.env.STEPSTITCH_INGEST_TOKEN || "dev-ingest"

// The bug, and the switch that fixes it. Starts broken on purpose.
let bugActive = true

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
}

function send(res, status, body, headers = {}) {
  const payload = typeof body === "string" ? body : JSON.stringify(body)
  res.writeHead(status, {
    "Content-Type": typeof body === "string" ? MIME[".html"] : MIME[".json"],
    "Content-Length": Buffer.byteLength(payload),
    ...headers,
  })
  res.end(payload)
}

function sendFile(res, root, relative) {
  // normalize + prefix check: a static server in an example is still a static server.
  const target = join(root, normalize(relative).replace(/^(\.\.[/\\])+/, ""))
  if (!target.startsWith(root) || !existsSync(target)) return send(res, 404, { error: "not found" })
  res.writeHead(200, { "Content-Type": MIME[extname(target)] || "application/octet-stream" })
  createReadStream(target).pipe(res)
}

async function readBody(req) {
  const chunks = []
  for await (const chunk of req) chunks.push(chunk)
  return Buffer.concat(chunks).toString("utf8")
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`)
  const path = url.pathname

  if (req.method === "GET" && (path === "/" || path === "/index.html")) {
    return sendFile(res, PUBLIC, "index.html")
  }
  if (req.method === "GET" && path === "/app.js") {
    return sendFile(res, PUBLIC, "app.js")
  }
  // The real @stepstitch/tracker build, served straight from node_modules. The example uses
  // the published module, not a copy that could drift from it.
  if (req.method === "GET" && path.startsWith("/vendor/")) {
    return sendFile(res, VENDOR, path.slice("/vendor/".length))
  }

  // --- the bug ---------------------------------------------------------------------------
  // POST /api/accounts/:id/transfer — 500 while the bug is active, 200 once it is fixed.
  const transfer = /^\/api\/accounts\/([^/]+)\/transfer$/.exec(path)
  if (req.method === "POST" && transfer) {
    await readBody(req) // consume; the body is never logged or forwarded anywhere
    if (bugActive) {
      return send(res, 500, { error: "TRANSFER_FAILED", detail: "settlement ledger unavailable" })
    }
    return send(res, 200, { status: "ok", reference: "TT-000123" })
  }

  // Apply fix / Reset bug. Also drivable by verify.mjs, which is how CI flips red to green.
  if (path === "/__bug") {
    if (req.method === "GET") return send(res, 200, { active: bugActive })
    if (req.method === "POST") {
      const body = JSON.parse((await readBody(req)) || "{}")
      bugActive = Boolean(body.active)
      return send(res, 200, { active: bugActive })
    }
  }

  // --- same-origin ingest proxy -------------------------------------------------------------
  // The browser never sees STEPSTITCH_INGEST_TOKEN. It posts here; this process adds the
  // credential and forwards. Copy this shape into your own app.
  if (req.method === "POST" && path === "/ingest") {
    const body = await readBody(req)
    try {
      const upstream = await fetch(`${STEPSTITCH_HOST}/api/stepstitch/v1/session`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${INGEST_TOKEN}`, // server-side only
        },
        body,
      })
      const text = await upstream.text()
      res.writeHead(upstream.status, { "Content-Type": MIME[".json"] })
      return res.end(text)
    } catch (err) {
      return send(res, 502, { error: "ingest_unreachable", detail: String(err) })
    }
  }

  send(res, 404, { error: "not found" })
})

server.listen(PORT, () => {
  console.log(`TinyTransfer listening on http://localhost:${PORT}`)
  console.log(`  forwarding traces to ${STEPSTITCH_HOST}`)
  console.log(`  bug is ${bugActive ? "ACTIVE (transfers return 500)" : "fixed"}`)
})
