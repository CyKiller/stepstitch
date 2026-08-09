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

Copy `STEPSTITCH_FIXPROOF_GATE_WORKFLOW` (`stepstitch_service.github_bridge.workflow`)
into `.github/workflows/stepstitch-fixproof-gate.yml`, add a `proof-policy.json` (start
from `examples/proof/proof-policy.json`), then mark the `fixproof` job a **required
status check** in branch protection (Settings → Branches → require status checks). That
last step is a repository setting — no workflow can grant itself required status.

The gate is deliberately offline: **no secrets, no StepStitch host, no trust in the PR
author**. It recomputes the statement hash and holds the proof to your policy, including
that the proof's subject commit is exactly the PR head — so the merge is refused when:

- the proof references a different commit than the PR head;
- the original version did not measurably fail, or the fixed version did not pass;
- the frozen test or execution envelope digests are altered;
- the evidence grade is caller-asserted where the policy demands measured;
- the privacy requirements (e.g. `schema_status`) are not met;
- the verifier kind is not on the policy's allowlist;
- any byte of the statement was changed after export.

Verification is `stepstitch proof verify fixproof.json --policy proof-policy.json
--head-sha <sha>` — the same command works on a laptop with no network. The proof claims
one failure was fixed under one frozen test and envelope; it never claims the program is
universally correct.

## Labels

`stepstitch`, `privacy-safe`, `stepstitch:needs-fix`, `stepstitch:repro-ready` /
`stepstitch:needs-data` (by grade), `stepstitch:confirmed-repro` (CI), and
`stepstitch:fix-candidate` (on the PR).
