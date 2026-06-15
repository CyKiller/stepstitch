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
`STEPSTITCH_ADMIN_TOKEN`, then dispatch it with a `trace_id` to run the reproduction and
confirm it in CI.

## Labels

`stepstitch`, `privacy-safe`, `stepstitch:needs-fix`, `stepstitch:repro-ready` /
`stepstitch:needs-data` (by grade), `stepstitch:confirmed-repro` (CI), and
`stepstitch:fix-candidate` (on the PR).
