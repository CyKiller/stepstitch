"""The customer-side CI workflow that runs a StepStitch repro and confirms it.

Customers drop this into ``.github/workflows/stepstitch-repro.yml`` in their repo. It is a
template string (not executed by StepStitch). Secrets STEPSTITCH_BASE_URL +
STEPSTITCH_ADMIN_TOKEN are set by the customer.
"""

STEPSTITCH_REPRO_WORKFLOW = r"""# .github/workflows/stepstitch-repro.yml
name: stepstitch-repro
on:
  workflow_dispatch:
    inputs:
      trace_id:
        description: StepStitch trace id
        required: true
      issue_number:
        description: GitHub issue to label on a confirmed repro (optional)
        required: false
      fix_ref:
        description: Fix reference (PR/commit) recorded with the verdict; defaults to the commit SHA
        required: false
permissions:
  contents: read
  issues: write
jobs:
  repro:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm i -D @playwright/test && npx playwright install --with-deps chromium
      - name: Fetch the StepStitch reproduction
        env:
          BASE: ${{ secrets.STEPSTITCH_BASE_URL }}
          TOKEN: ${{ secrets.STEPSTITCH_ADMIN_TOKEN }}
          TRACE: ${{ github.event.inputs.trace_id }}
        run: |
          mkdir -p tests/stepstitch
          curl -fsS -H "Authorization: Bearer $TOKEN" \
            "$BASE/api/stepstitch/v1/session/$TRACE/playwright" \
            | python -c "import sys,json;open('tests/stepstitch/repro_'+'${{ github.event.inputs.trace_id }}'+'.spec.ts','w').write(json.load(sys.stdin)['playwright_code'])"
      - name: Run the reproduction
        id: run
        run: npx playwright test tests/stepstitch/ --reporter=line
      - name: Report the repro result to StepStitch (post-fix outcome)
        # Only when the repro step actually ran (success/failure) — skip if CI setup failed,
        # so a broken pipeline never records a spurious not_fixed verdict.
        if: ${{ steps.run.outcome == 'success' || steps.run.outcome == 'failure' }}
        env:
          BASE: ${{ secrets.STEPSTITCH_BASE_URL }}
          TOKEN: ${{ secrets.STEPSTITCH_ADMIN_TOKEN }}
          TRACE: ${{ github.event.inputs.trace_id }}
          RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
          FIX_REF: ${{ github.event.inputs.fix_ref || github.sha }}
        run: |
          if [ "${{ steps.run.outcome }}" = "success" ]; then PASSED=true; else PASSED=false; fi
          curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            "$BASE/api/stepstitch/v1/session/$TRACE/verify" \
            -d "{\"pre_passed\": false, \"post_passed\": $PASSED, \"fix_ref\": \"$FIX_REF\", \"run_url\": \"$RUN_URL\"}"
      - name: Label the issue stepstitch:confirmed-repro (when an issue number is given)
        if: ${{ success() && github.event.inputs.issue_number != '' }}
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: gh issue edit "${{ github.event.inputs.issue_number }}" --add-label "stepstitch:confirmed-repro"
"""
