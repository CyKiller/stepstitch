"""The customer-side CI workflow that runs a StepStitch repro and confirms it.

Customers drop this into ``.github/workflows/stepstitch-repro.yml`` in their repo. It is a
template string (not executed by StepStitch).

**Red is measured, not assumed.** The workflow checks out the pre-fix ref and runs the
reproduction there, then checks out the fix ref and runs it again. Both outcomes are reported,
so ``confirmed_fixed`` means StepStitch actually observed the test fail before the fix and
pass after it. An earlier version of this template hardcoded ``pre_passed: false`` — a verdict
resting on an assumed red half is not evidence.

Secrets the customer sets:
  STEPSTITCH_BASE_URL      the StepStitch host. (Careful: the *host process* reads an env var
                           of the same name meaning the application under test — see
                           docs/DEPLOY.md.)
  STEPSTITCH_VERIFY_TOKEN  an agent token with the narrow ``verify`` scope: it may fetch a
                           reproduction and post a verdict, and nothing else. Issue it from
                           the console's Agents tab. Do not put the admin token here.

Repository variables:
  STEPSTITCH_APP_CMD       command that starts the app under test (default: ``npm run
                           stepstitch:app`` when that script exists)
  STEPSTITCH_APP_URL       where it listens (default http://localhost:3000)
"""

# The repro run is identical in the red and green jobs. It is duplicated rather than factored
# into a composite action so a customer can read the whole thing in one file.
_RUN_REPRO_STEPS = r"""
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - name: Install dependencies
        run: npm ci --no-audit --no-fund || npm install --no-audit --no-fund
      - name: Install Playwright
        run: npm i -D @playwright/test && npx playwright install --with-deps chromium
      - name: Start the application under test
        env:
          APP_CMD: ${{ vars.STEPSTITCH_APP_CMD }}
          APP_URL: ${{ vars.STEPSTITCH_APP_URL || 'http://localhost:3000' }}
        run: |
          if [ -n "$APP_CMD" ]; then
            CMD="$APP_CMD"
          elif npm run 2>/dev/null | grep -qE '^ +stepstitch:app'; then
            CMD="npm run stepstitch:app"
          else
            echo "::error::No start command for the app under test. Add a 'stepstitch:app'"
            echo "::error::npm script, or set the STEPSTITCH_APP_CMD repository variable."
            exit 1
          fi
          echo "Starting the app under test: $CMD"
          nohup sh -c "$CMD" > /tmp/stepstitch-app.log 2>&1 &
          for _ in $(seq 1 60); do
            if curl -fsS -o /dev/null "$APP_URL"; then echo "app is up at $APP_URL"; exit 0; fi
            sleep 2
          done
          echo "::error::the app never became reachable at $APP_URL"
          cat /tmp/stepstitch-app.log || true
          exit 1
      - name: Fetch the StepStitch reproduction
        env:
          BASE: ${{ secrets.STEPSTITCH_BASE_URL }}
          TOKEN: ${{ secrets.STEPSTITCH_VERIFY_TOKEN }}
          TRACE: ${{ github.event.inputs.trace_id }}
        run: |
          mkdir -p tests/stepstitch
          curl -fsS -H "Authorization: Bearer $TOKEN" \
            "$BASE/api/stepstitch/v1/session/$TRACE/playwright" \
            | python -c "import sys,json,os;open('tests/stepstitch/repro_'+os.environ['TRACE']+'.spec.ts','w').write(json.load(sys.stdin)['playwright_code'])"
      - name: Run the reproduction
        id: run
        continue-on-error: true
        run: npx playwright test tests/stepstitch/ --reporter=line
      - name: Record the outcome
        id: result
        run: |
          echo "ran=true" >> "$GITHUB_OUTPUT"
          if [ "${{ steps.run.outcome }}" = "success" ]; then
            echo "passed=true" >> "$GITHUB_OUTPUT"
          else
            echo "passed=false" >> "$GITHUB_OUTPUT"
          fi
"""

STEPSTITCH_REPRO_WORKFLOW = (
    r"""# .github/workflows/stepstitch-repro.yml
name: stepstitch-repro
on:
  workflow_dispatch:
    inputs:
      trace_id:
        description: StepStitch trace id
        required: true
      pre_ref:
        description: "Ref where the bug still exists (default: the commit before HEAD)"
        required: false
      fix_ref:
        description: "Ref containing the fix (default: the dispatched commit)"
        required: false
      issue_number:
        description: GitHub issue to label on a confirmed fix (optional)
        required: false
permissions:
  contents: read
  issues: write
jobs:
  # RED: the reproduction must FAIL here, or there was never a bug to fix.
  red:
    runs-on: ubuntu-latest
    outputs:
      passed: ${{ steps.result.outputs.passed }}
      ran: ${{ steps.result.outputs.ran }}
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: Check out the pre-fix ref
        run: |
          REF="${{ github.event.inputs.pre_ref }}"
          if [ -z "$REF" ]; then REF="$(git rev-parse HEAD^)"; fi
          echo "Pre-fix ref: $REF"
          git checkout --detach "$REF"
"""
    + _RUN_REPRO_STEPS
    + r"""
  # GREEN: the same reproduction must PASS on the fix.
  green:
    runs-on: ubuntu-latest
    outputs:
      passed: ${{ steps.result.outputs.passed }}
      ran: ${{ steps.result.outputs.ran }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          ref: ${{ github.event.inputs.fix_ref || github.sha }}
"""
    + _RUN_REPRO_STEPS
    + r"""
  report:
    needs: [red, green]
    if: always()
    runs-on: ubuntu-latest
    steps:
      # Report ONLY when both reproductions actually executed. A broken pipeline (bad ref, app
      # failed to boot) must record nothing rather than a spurious verdict.
      - name: Report the measured red -> green result to StepStitch
        if: ${{ needs.red.outputs.ran == 'true' && needs.green.outputs.ran == 'true' }}
        env:
          BASE: ${{ secrets.STEPSTITCH_BASE_URL }}
          TOKEN: ${{ secrets.STEPSTITCH_VERIFY_TOKEN }}
          TRACE: ${{ github.event.inputs.trace_id }}
          PRE: ${{ needs.red.outputs.passed }}
          POST: ${{ needs.green.outputs.passed }}
          RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
          FIX_REF: ${{ github.event.inputs.fix_ref || github.sha }}
        run: |
          echo "measured: pre_passed=$PRE post_passed=$POST"
          curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            "$BASE/api/stepstitch/v1/session/$TRACE/verify" \
            -d "{\"pre_passed\": $PRE, \"post_passed\": $POST, \"fix_ref\": \"$FIX_REF\", \"run_url\": \"$RUN_URL\"}"
      - name: Explain why nothing was reported
        if: ${{ !(needs.red.outputs.ran == 'true' && needs.green.outputs.ran == 'true') }}
        run: |
          echo "::warning::A reproduction run did not complete, so no verdict was recorded."
          echo "::warning::StepStitch stores only measured results."
      # Two distinct facts, now that both halves are measured:
      #   the reproduction really failed on the buggy ref  -> confirmed-repro
      #   ...and really passed on the fix                  -> confirmed-fix
      - name: Label the issue stepstitch:confirmed-repro
        if: ${{ needs.red.outputs.passed == 'false' && github.event.inputs.issue_number != '' }}
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: gh issue edit "${{ github.event.inputs.issue_number }}" --add-label "stepstitch:confirmed-repro"
      - name: Label the issue stepstitch:confirmed-fix
        if: ${{ needs.red.outputs.passed == 'false' && needs.green.outputs.passed == 'true' && github.event.inputs.issue_number != '' }}
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: gh issue edit "${{ github.event.inputs.issue_number }}" --add-label "stepstitch:confirmed-fix"
"""
)


# The FixProof merge gate. Customers drop this into
# ``.github/workflows/stepstitch-fixproof-gate.yml`` and mark the job a REQUIRED status
# check in branch protection (Settings -> Branches -> require status checks -> "fixproof").
# Branch protection itself is a repository setting; no workflow can turn it on.
#
# The check is deliberately OFFLINE: it needs no secret, no StepStitch host, and no trust
# in whoever produced the PR. The PR carries its proof (fixproof.json, exported by
# `stepstitch proof export` after verification); the gate cryptographically verifies the
# proof's signature against the trusted keys in the repo's policy and holds it to every
# other requirement — including that the proof's subject is EXACTLY the PR head commit,
# so a proof about some other code cannot ride in.
#
# Three trust-audit hardenings, each load-bearing:
#   - the policy (keys + requirements) is read from the PROTECTED BASE COMMIT, never
#     from the PR's checkout — a PR that weakens proof-policy.json in its own diff is
#     still judged by the policy of the branch it wants to enter;
#   - actions are pinned by commit SHA and the verifier by exact version — a floating
#     dependency inside a trust gate is a moving trust boundary;
#   - `github.event.pull_request.head.sha`, not `github.sha`: on pull_request events
#     github.sha is the ephemeral MERGE commit, which no exported proof can ever name.
_GATE_VERSION = "0.11.0"  # x-release-please-version

STEPSTITCH_FIXPROOF_GATE_WORKFLOW = r"""name: stepstitch fixproof gate

on:
  pull_request:

# Read-only by construction: checking out the PR and reading the base branch's policy
# need `contents: read`; nothing in this gate ever writes.
permissions:
  contents: read

jobs:
  fixproof:
    name: no AI fix merges without proof
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7
        with:
          # The PR head itself — the commit the proof must be about.
          ref: ${{ github.event.pull_request.head.sha }}
      - name: Load the trusted policy from the protected base branch
        # The PR's own proof-policy.json is attacker-editable in the same diff. The
        # trusted keys and requirements must come from the branch the PR wants to
        # enter, so no PR can weaken the policy that judges it.
        run: |
          git fetch --depth=1 origin "${{ github.event.pull_request.base.sha }}"
          git show "${{ github.event.pull_request.base.sha }}:proof-policy.json" \
            > "${{ runner.temp }}/trusted-proof-policy.json"
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with: { python-version: "3.11" }
      - name: Install the pinned verifier
        run: pip install stepstitch-service==__STEPSTITCH_VERSION__
      - name: Verify the proof against this PR's head
        run: |
          stepstitch proof verify fixproof.json \
            --policy "${{ runner.temp }}/trusted-proof-policy.json" \
            --head-sha "${{ github.event.pull_request.head.sha }}"
""".replace("__STEPSTITCH_VERSION__", _GATE_VERSION)
