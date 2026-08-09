# GitHub Repair Loop (optional)

The Repair Loop turns a reproduced trace into a labeled GitHub **issue** and a
regression-test **pull request** in your repo — privacy-safe and **human-merged**. It is
off by default, governed (admin + `approved_by`), audited, and never exposed on the
agent/MCP surface. StepStitch holds no repo write credentials in core and never merges.

## Enable it

```python
# pip install "stepstitch-service[github]"
from stepstitch_service.github_bridge import GitHubBridge, GitHubClient, github_token_request
request = github_token_request(GITHUB_TOKEN)            # token lives in the host
bridge = GitHubBridge(GitHubClient(request, repo="acme/app"), base_branch="main")
# build_app(..., github_bridge=bridge)   OR  create_stepstitch_router(..., github_bridge=bridge)
```

## Endpoints (admin only)

- `POST /stepstitch/v1/session/{id}/github/issue` — body `{ "approved_by": "..." }` ->
  ensures labels + creates the issue from the sanitized summary.
- `POST /stepstitch/v1/session/{id}/github/pr?dry_run=true` — body
  `{ "approved_by": "...", "idempotency_key": "..." }` -> dry-run shows the branch + test
  path; `dry_run=false` opens the regression-test PR. **Never merges.**

## CI repro workflow

Copy `STEPSTITCH_REPRO_WORKFLOW` (`stepstitch_service.github_bridge.workflow`) into
`.github/workflows/stepstitch-repro.yml`, set repo secrets `STEPSTITCH_BASE_URL` +
`STEPSTITCH_VERIFY_TOKEN` (an agent token with the narrow `verify` scope, issued from
the console's Agents tab — never the admin token; the template's own tests refuse it),
then dispatch it with a `trace_id` to run the reproduction and
confirm it in CI. Pass the optional `issue_number` input to have the workflow apply the
`stepstitch:confirmed-repro` label to that issue (via `gh`) when the repro run is green.

The workflow also reports the run outcome to the Verified-Fix engine — see
[verified-fix.md](verified-fix.md).

## FixProof merge gate (required check)

> **No AI fix merges without proof.**

After a verification carries a `fixed_commit`, export the proof and commit it with the
fix PR:

```bash
stepstitch proof export <trace-id> --out fixproof.json
```

Set it up once:

1. **Generate the trust anchor.** On the machine that runs your StepStitch host:
   `stepstitch proof keygen` writes a private Ed25519 seed (never printed, never
   committed) and prints the public key. Point `STEPSTITCH_SIGNING_KEY` at the seed
   file — every exported proof is now signed.
2. **Configure the policy.** Start from `examples/proof/proof-policy.json`, paste the
   printed public key into `trusted_keys`, and name your verifier identities in
   `allowed_verifier_identities`. The template deliberately **refuses to run**
   (exit 2, unusable) until the placeholder key is replaced — a gate you forgot to
   configure must never read as green.
3. **Install the gate.** Copy `STEPSTITCH_FIXPROOF_GATE_WORKFLOW`
   (`stepstitch_service.github_bridge.workflow`) into
   `.github/workflows/stepstitch-fixproof-gate.yml`, then mark the `fixproof` job a
   **required status check** in branch protection (Settings → Branches → require
   status checks). That last step is a repository setting — no workflow can grant
   itself required status.

The gate is deliberately offline: **no secrets, no StepStitch host, no trust in the PR
author**. Internal consistency is not enough — a fabricated document with a correctly
recomputed hash is still refused, because the signature is verified cryptographically
(Ed25519 over the canonical statement bytes) against the keys **your** policy names.
Three hardenings make the trust chain end-to-end:

- the policy (trusted keys and requirements) is loaded from the **protected base
  branch**, so a PR that weakens `proof-policy.json` in its own diff is still judged
  by the policy of the branch it wants to enter;
- the workflow pins its actions by commit SHA and the verifier by exact version — no
  floating dependency inside the trust boundary;
- the proof's subject commit must be exactly the PR head.

So the merge is refused when:

- the document carries no signature, an opaque signature string, forged signature
  bytes, or a valid signature by any key the policy does not trust;
- the proof references a different commit than the PR head (including a genuine proof
  replayed from another PR);
- a load-bearing binding is missing — base commit, failure fingerprint, red signature,
  frozen-test digest, execution-envelope digest, privacy-policy digest, structural
  result (`require_bindings`);
- the original version did not measurably fail, or the fixed version did not pass;
- the evidence grade is caller-asserted where the policy demands measured;
- the privacy requirements (e.g. `schema_status`) are not met;
- the verifier kind or identity is not on the policy's allowlist;
- any byte of the statement was changed after export.

Every one of those refusals is a permanent acceptance test
(`service/tests/test_fixproof_adversarial.py` — the six attacks from the trust audit,
each proven refused).

Verification is `stepstitch proof verify fixproof.json --policy proof-policy.json
--head-sha <sha>` — the same command works on a laptop with no network. The proof claims
one failure was fixed under one frozen test and envelope; it never claims the program is
universally correct.

## Labels

`stepstitch`, `privacy-safe`, `stepstitch:needs-fix`, `stepstitch:repro-ready` /
`stepstitch:needs-data` (by grade), `stepstitch:confirmed-repro` (CI), and
`stepstitch:fix-candidate` (on the PR).
