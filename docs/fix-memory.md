# Fix Memory

**Privacy-safe institutional memory: "you've fixed this shape before."**

Bugs recur. Engineers — and increasingly agents — re-solve the same failures because the
knowledge of *how a class of bug was fixed* lives in people's heads or in tickets full of PII
nobody can safely feed an LLM. Fix Memory turns StepStitch's verified-fix corpus into a
structural, scrubbed knowledge base you can query and that compounds over time.

## How it works

Every time CI reports a confirmed **red→green** fix (`POST /session/{id}/verify` with
`pre_passed=false, post_passed=true`), StepStitch reduces the trace to a **structural
fingerprint** and stores it alongside the verdict:

- route template (`/accounts/:id/transfer`), diagnostic type (`api_error`), failing HTTP status,
  exception type, diagnostic endpoint, and the terminal selector.

The fingerprint is persisted at verify-time, so it **survives body purge** — a confirmed fix stays
matchable long after the trace body is retention-expired. Fingerprints are **structure-derived** by
construction: routes are templated and selectors are structural (the server-side scrubber already
guaranteed this at ingest).

When a new bug comes in, its fingerprint is matched against the corpus by weighted structural
similarity. Matching is **deterministic, dependency-free, and explainable** — every match reports
the fields that agreed.

## Use it

```bash
# Match a trace against the verified-fix corpus
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$BASE_URL/api/stepstitch/v1/session/$TRACE_ID/similar-fixes"
```

```json
{
  "fingerprint": { "route": "/accounts/:id/transfer", "diagnostic_type": "api_error", "failing_status": 500, "...": "..." },
  "similar_fixes": [
    { "trace_id": "…", "fix_ref": "PR#42", "run_url": "https://ci/…", "similarity": 1.0,
      "reasons": ["same route", "same diagnostic_type", "same failing_status"] }
  ]
}
```

- **MCP tool:** `match_verified_fixes` — agents get "you've fixed this before" with the prior fix
  reference, without ever seeing raw data.
- **Dashboard:** a *Seen before? — Fix Memory* card on the trace detail.

## Configure

Match weights are tunable per deployment via `STEPSTITCH_FIX_MEMORY_WEIGHTS` (JSON mapping
fingerprint fields to weights). The defaults weight the route most heavily. Source:
`service/stepstitch_service/fix_memory.py`.
