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

The PR ends in a **proof-only commit** — the protocol that makes "the proof names the
merged code" actually satisfiable (a proof committed *into* the code commit would move
the head it has to name):

```text
A = the exact tested code commit        <- verify-fix ran here; the proof's subject
B = a child commit adding ONLY fixproof.json   <- the PR head
```

```bash
# 1. commit the fix — this is commit A, the code under test
git commit -am "fix the transfer handler"

# 2. measure and export: freeze -> verify-fix at A -> the signed proof names A
stepstitch proof export <trace-id> --out fixproof.json

# 3. the proof-only commit — commit B, nothing else in it
git add fixproof.json
git commit -m "fixproof for $(git rev-parse HEAD)"
```

The gate (`stepstitch proof gate <PR-head> --policy proof-policy.json`) enforces the
protocol end to end: the head has exactly one parent, `HEAD^..HEAD` changes nothing but
`fixproof.json`, and the signed proof verifies with its subject bound to `HEAD^` — the
tested code. Code pushed after the proof, or a stowaway file beside it, is refused.

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
(Ed25519, via the `cryptography` library) against the keys **your** policy names, and
trust anchors themselves are validated (a small-order key — against which one forged
signature would verify every message — is refused as an unusable policy). The trust
chain is end-to-end:

- `pull_request_target` runs **both the gate definition and the checkout from the
  protected base branch** — a PR can weaken neither the workflow nor the
  `proof-policy.json` that judges it, and the PR head enters only as fetched git data,
  never as executed code;
- the workflow pins its actions by commit SHA and the verifier by exact version — no
  floating dependency inside the trust boundary;
- the proof's subject commit must be exactly the PR head's parent — the tested code
  under the proof-only-commit protocol.

So the merge is refused when:

- the head is not a proof-only commit: it has more than one parent, changes anything
  besides `fixproof.json`, carries no proof, or has code committed after the proof;
- the document carries no signature, an opaque signature string, forged signature
  bytes, or a valid signature by any key the policy does not trust;
- the proof names a different commit than the tested code (including a genuine proof
  replayed from another PR);
- a load-bearing binding is missing — base commit, failure fingerprint, red signature,
  frozen-test digest, execution-envelope digest, privacy-policy digest, structural
  result (`require_bindings`);
- the original version did not measurably fail, or the fixed version did not pass;
- the evidence grade is caller-asserted where the policy demands measured;
- the privacy requirements (e.g. `schema_status`) are not met;
- the verifier kind or identity is not on the policy's allowlist;
- any byte of the statement was changed after export.

Every one of those refusals is a permanent acceptance test: the six attacks from the
first trust audit in `service/tests/test_fixproof_adversarial.py`, and the full
customer flow — real git repositories, proof-only commits, code-after-proof, stowaway
files, merge heads, forged and small-order keys — in
`service/tests/test_proof_gate.py`.

`stepstitch proof gate <head> --policy proof-policy.json` and `stepstitch proof verify
fixproof.json --policy proof-policy.json --head-sha <sha>` both work on a laptop with
no network. The proof claims one failure was fixed under one frozen test and envelope;
it never claims the program is universally correct.

The reproduction workflow (`STEPSTITCH_REPRO_WORKFLOW`) reports the commit each half
actually ran (`git rev-parse HEAD` from its own checkout) as `base_commit` /
`fixed_commit`. Its outcome is recorded at the **asserted** grade — honest, because the
host did not run it — so a `require_grade: measured` merge policy is satisfied only by
the host's own `freeze` → `verify-fix` path, which is where exported proofs come from.

## Labels

`stepstitch`, `privacy-safe`, `stepstitch:needs-fix`, `stepstitch:repro-ready` /
`stepstitch:needs-data` (by grade), `stepstitch:confirmed-repro` (CI), and
`stepstitch:fix-candidate` (on the PR).
