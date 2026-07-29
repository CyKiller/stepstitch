# TinyTransfer

A deliberately broken money-transfer app, wired to StepStitch. It exists to make the privacy
claims checkable rather than assertable: it asks for the three things you would most regret
leaking — an account number, an amount, an email — sends them over a request carrying a
synthetic query parameter, and fails with a 500.

Then you look at what StepStitch actually received.

```
public/          the app (plain HTML + the real @stepstitch/tracker module)
server.mjs       node:http — the 500, the fix switch, and the ingest proxy
e2e/             the privacy proofs, run against the bytes that left the browser
verify.mjs       the red→green loop, against a real StepStitch host
```

## Install

The example depends on `@stepstitch/tracker` at `file:../..`, and `dist/` is built by the
repository root's `prepare` script — so **install the root first**:

```bash
npm ci                       # in the repository root: builds dist/
cd examples/tiny-transfer
npm install
npx playwright install chromium
```

## Run

```bash
npm start                    # http://localhost:4173
```

Open it and:

1. Notice the consent box is **unticked**. Send a transfer — it fails, and nothing is
   recorded. That is the SDK's real default, not a demo affordance.
2. Tick consent, send again. The failure is reported, and the exact payload that left the
   browser is printed on the page.
3. Compare that payload to the form. The account number, amount and email are absent; so is
   `?sessionRef=FAKE-QUERY-SECRET-123`; the endpoint reads `/api/accounts/:id/transfer`
   rather than the concrete id.
4. Press **Apply fix** and send again — HTTP 200. That difference is what a verified fix is.

By default it forwards to a StepStitch host at `http://localhost:8000` (`docker compose up`
in the repository root). Override with `STEPSTITCH_HOST` and `STEPSTITCH_INGEST_TOKEN`.

## Test

```bash
npm run test:e2e
```

Thirteen hermetic tests — no Python service, no database, no network. A stub host records
every payload, and the assertions run against that raw JSON:

- consent starts off, and nothing is captured before it is granted
- revoking consent clears the buffer
- no value from any form field appears in the captured evidence
- the query parameter is stripped, and the route is templated
- input footsteps record `{interacted: true}` and never a value
- no screenshots, page text, bodies, headers, cookies or stacks
- the ingest token never reaches page JavaScript
- applying the fix turns 500 into 200

One test deliberately asserts the *opposite* of what you might expect:
`free text the user typed is left for the SERVER to scrub`. The explanation field arrives
intact, account number and all. That is correct. A client-side scrubber is bypassed by
anyone willing to POST their own JSON, so redaction happens server-side in `scrubber.py`,
on every payload, before storage. That is what "final trust boundary" means.

### What the default policy does and does not redact

Report a failure against a real host, then read the stored row. The explanation comes back:

```
Tried to send $250.00 to account [redacted:card] from [redacted:email] and it
failed. My SSN is [redacted:ssn] if that matters.
```

The account number, email and SSN are gone. **`$250.00` is not** — it is five digits, below
the built-in generic threshold, and a bare amount is not an identifier. Whether that matters
is a policy question, not a code one, so it is the operator's call rather than a default we
impose. Make it their call in one request:

```bash
curl -X PUT -H "Authorization: Bearer $ADMIN" -H 'Content-Type: application/json' \
  -d '{"extra_redactions":[["amount","\\$[0-9][0-9,]*(\\.[0-9]{2})?"]],"extra_forbidden_keys":[]}' \
  "$HOST/admin/config/scrub"
```

Now it reads `[redacted:custom:amount]`. Overrides can only ever tighten the base profile —
there is no request that makes StepStitch store more.

## The full loop

With a real host running (`docker compose up --build` in the repository root):

```bash
# 1. issue a narrow CI credential — console → Agents → scope "verify"
# 2. report a failure in the app, and copy the trace id it prints
STEPSTITCH_HOST=http://localhost:8000 \
STEPSTITCH_VERIFY_TOKEN=ssa_… \
TRACE_ID=trc_… \
npm run verify
```

`verify.mjs` fetches the generated reproduction, runs it against the bug (expects red),
applies the fix, runs it again (expects green), and posts **both measured outcomes**.
StepStitch derives `confirmed_fixed`, and the failure shape moves to Fixed on the board.

Both runs really happen. Neither is assumed.

## Teardown

```bash
# in this directory
rm -rf node_modules test-results .verify-run
# in the repository root, if you started the host
docker compose down -v
```

Revoke the `verify` agent token in the console when you are done with it. Nothing here writes
outside this directory, and there are no real credentials anywhere in it — every value in the
form is fake, and the tokens are the compose file's throwaway dev ones.
