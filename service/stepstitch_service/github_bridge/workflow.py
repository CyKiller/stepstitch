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
      - name: Label issue confirmed on green-then-red repro
        if: success()
        run: echo "stepstitch:confirmed-repro (wire to your issue via gh CLI)"
"""
