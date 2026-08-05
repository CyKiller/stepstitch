# Evidence Attestation

**Signed, portable troubleshooting evidence anyone can verify — without trusting you.**

As AI agents and humans act on evidence, the unanswered question becomes: *what produced this
evidence, was it tampered with, and what did it contain?* Session replays live in a vendor's
cloud — not portable, not deterministic, not independently verifiable. Evidence Attestation is the
SLSA/in-toto idea applied to bug reproductions: a canonical, tamper-evident, optionally-signed
bundle a regulator, customer, or another company can verify on their own.

## How it works

`GET /session/{id}/attestation` composes facts that already exist — the **scrub report** (what was
redacted, under which policy), the **replayability** score, the **verification verdict**
(red→green), and the **SDK build** that captured the trace — into a **canonical bundle**
(deterministic JSON, sorted keys) and a **`sha256` integrity hash** anyone can recompute with no
tooling.

Signing is **tenant-controlled**. If you set `STEPSTITCH_SIGNING_KEY`, the host signs the canonical
bytes with **your** key via the `cosign` CLI — the StepStitch service core never holds a key. If
unset, the bundle is returned unsigned; the hash is always tamper-evident regardless.

The bundle is **structure-derived** — it only composes already-sanitized reads.

## Verify independently (no StepStitch account)

1. Recompute `sha256` of the canonical bundle (sorted keys, no whitespace) and compare to
   `bundle_sha256`.
2. If a signature is present, verify it with the tenant's public key:
   ```bash
   cosign verify-blob --key tenant.pub --signature attestation.sig bundle.json
   ```

## Use it

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$BASE_URL/api/stepstitch/v1/session/$TRACE_ID/attestation"
```

- **MCP tool:** `get_attestation`.
- **Dashboard:** a *Signed evidence* action on the trace detail (bundle + hash + verify recipe).

## Configure

`STEPSTITCH_SIGNING_KEY` — a `cosign` key reference (file or KMS URI) the deployer owns. Tie it to
your AI-Act / Reg S-P recordkeeping. Source: `service/stepstitch_service/attestation.py`,
`server/signing.py`.
