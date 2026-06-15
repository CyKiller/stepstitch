# Verified-Fix Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make StepStitch the neutral oracle that certifies a candidate fix actually resolves a reproduced bug (red→green) and accumulates every reproduced failure + its certified fix as a queryable **regression corpus**.

**Architecture:** StepStitch does NOT execute code — the customer's CI runs the deterministic repro (in their sandbox) and reports the result back. StepStitch derives a verdict from the pre-fix run (should fail) and post-fix run (should pass), stores it, and surfaces a corpus. Pure verdict logic in a new `verification/` package; governed admin endpoints in the existing router; a new `stepstitch_verifications` table in the host; the CI workflow reports results. No NPI: rows carry trace ids, pass/fail booleans, and a fix reference only.

**Tech Stack:** Python 3.10+, FastAPI router factory (injected `execute`/`fetchone`/`fetchall`), pytest.

**Scope:** verdict logic + record/read endpoints + corpus + DDL + CI reporting + docs. **Out of scope:** auto-generating the fix (that's the consumer's agent), and any code execution by StepStitch.

**Reference patterns:** `service/stepstitch_service/github_bridge/content.py` (pure module + tests), `router.py` `post_deliver`/`get_summary_by_correlation` (endpoint + audit shape), `server/db.py` (DDL + the `stepstitch_audit` table added recently), `server/tests/test_observability.py` (DB-fake test style).

---

## File Structure

- Create `service/stepstitch_service/verification/__init__.py` — exports `derive_verdict`, the `VERDICT_*` constants, `VerificationResult`.
- Create `service/stepstitch_service/verification/verdict.py` — pure verdict logic. No I/O.
- Modify `service/stepstitch_service/router.py` — `VerifyPayload` model, a `_verification_row` helper, and three endpoints: `POST /session/{id}/verify`, `GET /session/{id}/verifications`, `GET /corpus`.
- Modify `service/pyproject.toml` — add the `verification` package + the two verification modules to the import-linter `source_modules`.
- Modify `server/db.py` — add the `stepstitch_verifications` table to `SCHEMA_SQL`.
- Modify `service/stepstitch_service/github_bridge/workflow.py` — add an optional `phase` input + a step that reports the run result to `/verify`.
- Create `docs/integrations/verified-fix.md`; link it from `docs/integrations/github.md`.
- Tests: `service/tests/test_verdict.py`, `service/tests/test_verification_endpoints.py`.

---

## Task 1: Pure verdict logic + package

**Files:**
- Create: `service/stepstitch_service/verification/__init__.py`, `service/stepstitch_service/verification/verdict.py`
- Test: `service/tests/test_verdict.py`
- Modify: `service/pyproject.toml`

- [ ] **Step 1: Write the failing test**

```python
# service/tests/test_verdict.py
"""Verdict logic: red->green is the only 'confirmed_fixed'."""
from stepstitch_service.verification.verdict import (
    VERDICT_CONFIRMED_FIXED, VERDICT_NOT_FIXED, VERDICT_NOT_REPRODUCED,
    VERDICT_REPRODUCED_UNFIXED, VerificationResult, derive_verdict,
)


def test_pre_passed_means_not_reproduced():
    # The pre-fix repro should FAIL. If it passed, the repro is not valid.
    assert derive_verdict(pre_passed=True, post_passed=None) == VERDICT_NOT_REPRODUCED
    assert derive_verdict(pre_passed=True, post_passed=False) == VERDICT_NOT_REPRODUCED


def test_pre_failed_no_post_is_reproduced_unfixed():
    assert derive_verdict(pre_passed=False, post_passed=None) == VERDICT_REPRODUCED_UNFIXED


def test_red_then_green_is_confirmed_fixed():
    assert derive_verdict(pre_passed=False, post_passed=True) == VERDICT_CONFIRMED_FIXED


def test_red_then_red_is_not_fixed():
    assert derive_verdict(pre_passed=False, post_passed=False) == VERDICT_NOT_FIXED


def test_result_as_dict_roundtrips():
    r = VerificationResult(trace_id="t1", pre_passed=False, post_passed=True,
                           verdict=VERDICT_CONFIRMED_FIXED, fix_ref="PR#9", run_url="u")
    d = r.as_dict()
    assert d["trace_id"] == "t1" and d["verdict"] == "confirmed_fixed"
    assert d["pre_passed"] is False and d["post_passed"] is True
    assert d["fix_ref"] == "PR#9" and d["run_url"] == "u"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd service && /tmp/ss-venv/bin/python -m pytest tests/test_verdict.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'stepstitch_service.verification'`

- [ ] **Step 3: Write `verdict.py`**

```python
# service/stepstitch_service/verification/verdict.py
"""Pure verification verdict logic.

StepStitch never runs code; the customer's CI runs the deterministic repro and reports
pass/fail. The verdict is derived from the pre-fix run (the repro should FAIL — the bug is
present) and the post-fix run (it should PASS — the bug is gone). Only red->green is a
confirmed fix.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

VERDICT_NOT_REPRODUCED = "not_reproduced"          # pre-fix run passed -> repro is invalid
VERDICT_REPRODUCED_UNFIXED = "reproduced_unfixed"  # pre failed, no post yet
VERDICT_NOT_FIXED = "not_fixed"                     # pre failed, post still failed
VERDICT_CONFIRMED_FIXED = "confirmed_fixed"         # pre failed -> post passed (red->green)


def derive_verdict(pre_passed: bool, post_passed: Optional[bool]) -> str:
    """Map a (pre-fix, post-fix) repro outcome to a verdict."""
    if pre_passed:
        return VERDICT_NOT_REPRODUCED
    if post_passed is None:
        return VERDICT_REPRODUCED_UNFIXED
    return VERDICT_CONFIRMED_FIXED if post_passed else VERDICT_NOT_FIXED


@dataclass(frozen=True)
class VerificationResult:
    trace_id: str
    pre_passed: bool
    post_passed: Optional[bool]
    verdict: str
    fix_ref: Optional[str] = None
    run_url: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "pre_passed": self.pre_passed,
            "post_passed": self.post_passed,
            "verdict": self.verdict,
            "fix_ref": self.fix_ref,
            "run_url": self.run_url,
        }
```

- [ ] **Step 4: Write `__init__.py`**

```python
# service/stepstitch_service/verification/__init__.py
"""StepStitch Verified-Fix engine — certify red->green and accumulate a regression corpus."""
from .verdict import (
    VERDICT_CONFIRMED_FIXED,
    VERDICT_NOT_FIXED,
    VERDICT_NOT_REPRODUCED,
    VERDICT_REPRODUCED_UNFIXED,
    VerificationResult,
    derive_verdict,
)

__all__ = [
    "derive_verdict",
    "VerificationResult",
    "VERDICT_CONFIRMED_FIXED",
    "VERDICT_NOT_FIXED",
    "VERDICT_NOT_REPRODUCED",
    "VERDICT_REPRODUCED_UNFIXED",
]
```

- [ ] **Step 5: Register the package + import-linter coverage in `service/pyproject.toml`**

In `[tool.setuptools] packages`, add `"stepstitch_service.verification"`.
In the `[[tool.importlinter.contracts]] source_modules` list, add `"stepstitch_service.verification.verdict"`.

- [ ] **Step 6: Run test + boundary**

Run: `cd service && /tmp/ss-venv/bin/python -m pytest tests/test_verdict.py -q && /tmp/ss-venv/bin/lint-imports`
Expected: 5 passed; `Contracts: 1 kept, 0 broken.`

- [ ] **Step 7: Commit**

```bash
git add service/stepstitch_service/verification/ service/tests/test_verdict.py service/pyproject.toml
git commit -m "feat(verified-fix): pure verdict logic (red->green = confirmed_fixed)"
```

---

## Task 2: Verify/record + corpus endpoints + DDL

**Files:**
- Modify: `server/db.py` (add `stepstitch_verifications` table)
- Modify: `service/stepstitch_service/router.py` (model + helper + 3 endpoints + import)
- Test: `service/tests/test_verification_endpoints.py`

- [ ] **Step 1: Write the failing test**

```python
# service/tests/test_verification_endpoints.py
"""Verify endpoint computes the verdict; corpus lists confirmed fixes; all audited."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import create_stepstitch_router, generate_playwright_test

_PFX = "/api/stepstitch/v1"


class _DB:
    def __init__(self):
        self.traces = {}
        self.verifications = []
        self.audits = []

    async def execute(self, query, params=()):
        q = " ".join(query.split())
        if q.startswith("INSERT INTO stepstitch_traces"):
            self.traces[params[0]] = {"footsteps": params[5], "project_id": params[2]}
        elif q.startswith("INSERT INTO stepstitch_verifications"):
            self.verifications.append({
                "trace_id": params[1], "pre_passed": params[2], "post_passed": params[3],
                "verdict": params[4], "fix_ref": params[5], "run_url": params[6],
                "created_at": params[7],
            })

    async def fetchone(self, query, params=()):
        q = " ".join(query.split())
        if q.startswith("SELECT footsteps, project_id"):
            row = self.traces.get(params[0])
            return (row["footsteps"], row["project_id"]) if row else None
        return None

    async def fetchall(self, query, params=()):
        q = " ".join(query.split())
        if "FROM stepstitch_verifications WHERE trace_id" in q:
            rows = [v for v in self.verifications if v["trace_id"] == params[0]]
        elif "FROM stepstitch_verifications WHERE verdict" in q:
            rows = [v for v in self.verifications if v["verdict"] == params[0]]
        else:
            return []
        return [(v["trace_id"], v["pre_passed"], v["post_passed"], v["verdict"],
                 v["fix_ref"], v["run_url"], v["created_at"]) for v in rows]


def _build():
    db = _DB()

    async def audit(action, actor, detail):
        db.audits.append((action, detail))

    router = create_stepstitch_router(
        get_user_id=lambda: "u", require_admin=lambda: {"user_id": "admin"},
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        audit=audit, generate_playwright_test=generate_playwright_test,
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app), db


def _ingest(client):
    return client.post(f"{_PFX}/session", json={
        "app_id": "a", "footsteps": [
            {"timestamp": "t", "type": "api_error", "route": "/x",
             "label": "[masked]", "metadata": {"status": 500}}],
        "metadata": {"sdk_version": "0.4.0"},
    }).json()["trace_id"]


def test_verify_missing_trace_404():
    client, _ = _build()
    assert client.post(f"{_PFX}/session/nope/verify",
                       json={"pre_passed": False}).status_code == 404


def test_verify_red_then_green_is_confirmed_and_audited():
    client, db = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/verify",
                    json={"pre_passed": False, "post_passed": True, "fix_ref": "PR#9"})
    assert r.status_code == 200
    assert r.json()["verdict"] == "confirmed_fixed"
    assert any(a[0] == "stepstitch.verify" for a in db.audits)


def test_verify_pre_only_is_reproduced_unfixed():
    client, _ = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/verify", json={"pre_passed": False})
    assert r.json()["verdict"] == "reproduced_unfixed"


def test_verifications_list_for_trace():
    client, _ = _build()
    tid = _ingest(client)
    client.post(f"{_PFX}/session/{tid}/verify",
                json={"pre_passed": False, "post_passed": True})
    r = client.get(f"{_PFX}/session/{tid}/verifications")
    assert r.status_code == 200
    items = r.json()["verifications"]
    assert len(items) == 1 and items[0]["verdict"] == "confirmed_fixed"


def test_corpus_lists_only_confirmed_fixed_by_default():
    client, _ = _build()
    tid = _ingest(client)
    client.post(f"{_PFX}/session/{tid}/verify",
                json={"pre_passed": False, "post_passed": True})   # confirmed_fixed
    client.post(f"{_PFX}/session/{tid}/verify",
                json={"pre_passed": False, "post_passed": False})  # not_fixed
    r = client.get(f"{_PFX}/corpus")
    entries = r.json()["entries"]
    assert all(e["verdict"] == "confirmed_fixed" for e in entries)
    assert len(entries) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd service && /tmp/ss-venv/bin/python -m pytest tests/test_verification_endpoints.py -q`
Expected: FAIL (404 path returns 404 only after the endpoint exists; the verify/corpus routes don't exist yet → 404/405 mismatch on the success cases). Confirm RED before implementing.

- [ ] **Step 3: Add the table to `server/db.py`**

In `SCHEMA_SQL`, after the `stepstitch_audit` block, append:

```sql
-- Verified-Fix corpus: each reproduced failure + its certified fix (red->green).
-- Carries trace ids, pass/fail booleans, and a fix reference only — never NPI.
CREATE TABLE IF NOT EXISTS stepstitch_verifications (
    id           TEXT PRIMARY KEY,
    trace_id     TEXT NOT NULL,
    pre_passed   BOOLEAN NOT NULL,
    post_passed  BOOLEAN,
    verdict      TEXT NOT NULL,
    fix_ref      TEXT,
    run_url      TEXT,
    created_at   TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_stepstitch_verif_trace   ON stepstitch_verifications (trace_id);
CREATE INDEX IF NOT EXISTS ix_stepstitch_verif_verdict ON stepstitch_verifications (verdict, created_at DESC);
```

- [ ] **Step 4: Edit `service/stepstitch_service/router.py`**

(a) Add import near the other package imports:
```python
from .verification.verdict import derive_verdict
```

(b) Add the payload model next to `GitHubPrPayload`:
```python
class VerifyPayload(BaseModel):
    pre_passed: bool
    post_passed: Optional[bool] = None
    fix_ref: Optional[str] = None
    run_url: Optional[str] = None
```

(c) Add a module-level helper next to `_recommended_next_step` (at the bottom of the file):
```python
def _verification_row(r: Any) -> Dict[str, Any]:
    return {
        "trace_id": r[0],
        "pre_passed": r[1],
        "post_passed": r[2],
        "verdict": r[3],
        "fix_ref": r[4],
        "run_url": r[5],
        "created_at": r[6].isoformat() if hasattr(r[6], "isoformat") else r[6],
    }
```

(d) Insert these three endpoints immediately before `@router.get("/session/{trace_id}/playwright")`:
```python
    @router.post("/session/{trace_id}/verify")
    async def post_verify(
        trace_id: str,
        payload: VerifyPayload,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        # CI reports the repro outcome; StepStitch derives + stores the verdict. StepStitch
        # never runs code itself. Red->green is the only confirmed fix.
        row = await fetchone(
            "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        verdict = derive_verdict(payload.pre_passed, payload.post_passed)
        await execute(
            "INSERT INTO stepstitch_verifications (id, trace_id, pre_passed, post_passed, "
            "verdict, fix_ref, run_url, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()), trace_id, payload.pre_passed, payload.post_passed,
                verdict, payload.fix_ref, payload.run_url, datetime.now(timezone.utc),
            ),
        )
        await _audit("stepstitch.verify", _actor_id(admin), {
            "trace_id": trace_id, "verdict": verdict, "fix_ref": payload.fix_ref,
        })
        return {
            "status": "ok", "trace_id": trace_id, "verdict": verdict,
            "pre_passed": payload.pre_passed, "post_passed": payload.post_passed,
            "fix_ref": payload.fix_ref,
        }

    @router.get("/session/{trace_id}/verifications")
    async def get_verifications(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        rows = await fetchall(
            "SELECT trace_id, pre_passed, post_passed, verdict, fix_ref, run_url, "
            "created_at FROM stepstitch_verifications WHERE trace_id = ? "
            "ORDER BY created_at DESC",
            (trace_id,),
        )
        await _audit("stepstitch.verifications", _actor_id(admin), {"trace_id": trace_id})
        return {"status": "ok", "trace_id": trace_id,
                "verifications": [_verification_row(r) for r in rows]}

    @router.get("/corpus")
    async def get_corpus(
        admin: Any = Depends(require_admin),
        verdict: str = Query("confirmed_fixed"),
        limit: int = Query(50, ge=1, le=500),
    ) -> Dict[str, Any]:
        # The regression corpus: every reproduced failure with the given verdict.
        rows = await fetchall(
            "SELECT trace_id, pre_passed, post_passed, verdict, fix_ref, run_url, "
            "created_at FROM stepstitch_verifications WHERE verdict = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (verdict, limit),
        )
        await _audit("stepstitch.corpus", _actor_id(admin), {"verdict": verdict})
        return {"status": "ok", "verdict": verdict,
                "entries": [_verification_row(r) for r in rows]}
```

Verify `uuid`, `datetime`, `timezone`, `Query`, `HTTPException`, `Depends`, `Optional`, `BaseModel`, `_audit`, `_actor_id`, `_loads` are already imported/available in router.py (they are used by existing endpoints — confirm by reading).

- [ ] **Step 5: Run tests**

Run: `cd service && /tmp/ss-venv/bin/python -m pytest tests/test_verification_endpoints.py tests/test_mcp_surface.py -q`
Expected: PASS (the new routes don't touch `COPILOT_SAFE_OPERATIONS`, so the 3-way parity in test_mcp_surface still holds). Then full suite: `/tmp/ss-venv/bin/python -m pytest tests -q`.

- [ ] **Step 6: Commit**

```bash
git add server/db.py service/stepstitch_service/router.py service/tests/test_verification_endpoints.py
git commit -m "feat(verified-fix): verdict/verifications/corpus endpoints + DDL"
```

---

## Task 3: CI reporting + docs

**Files:**
- Modify: `service/stepstitch_service/github_bridge/workflow.py` (report run result to `/verify`)
- Create: `docs/integrations/verified-fix.md`
- Modify: `docs/integrations/github.md` (link), `service/tests/test_github_content.py` (assert the workflow reports verify)

- [ ] **Step 1: Write the failing test (append to `service/tests/test_github_content.py`)**

```python
def test_repro_workflow_reports_verify_result():
    from stepstitch_service.github_bridge.workflow import STEPSTITCH_REPRO_WORKFLOW
    t = STEPSTITCH_REPRO_WORKFLOW
    assert "/verify" in t            # CI reports the repro outcome back to StepStitch
    assert "post_passed" in t        # the run result is posted as the post-fix outcome
```

Run: `cd service && /tmp/ss-venv/bin/python -m pytest tests/test_github_content.py::test_repro_workflow_reports_verify_result -q` → RED.

- [ ] **Step 2: Update `service/stepstitch_service/github_bridge/workflow.py`**

Replace the final step (the `Label the issue ...` step) with two steps — report the verify result, then label:

```yaml
      - name: Report the repro result to StepStitch (post-fix outcome)
        if: ${{ always() && github.event.inputs.issue_number != '' }}
        env:
          BASE: ${{ secrets.STEPSTITCH_BASE_URL }}
          TOKEN: ${{ secrets.STEPSTITCH_ADMIN_TOKEN }}
          TRACE: ${{ github.event.inputs.trace_id }}
        run: |
          PASSED=${{ steps.run.outcome == 'success' }}
          curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            "$BASE/api/stepstitch/v1/session/$TRACE/verify" \
            -d "{\"pre_passed\": false, \"post_passed\": $PASSED, \"run_url\": \"$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID\"}"
      - name: Label the issue stepstitch:confirmed-repro (when an issue number is given)
        if: ${{ success() && github.event.inputs.issue_number != '' }}
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: gh issue edit "${{ github.event.inputs.issue_number }}" --add-label "stepstitch:confirmed-repro"
```

(The `Run the reproduction` step already has `id: run`, so `steps.run.outcome` is available.)

- [ ] **Step 3: Create `docs/integrations/verified-fix.md`**

```markdown
# Verified-Fix engine

StepStitch certifies that a candidate fix actually resolves a reproduced bug and remembers
it. StepStitch never runs code — your CI runs the deterministic repro and reports the
outcome; StepStitch derives the verdict and banks it in a regression corpus.

## Verdicts

`derive_verdict(pre_passed, post_passed)` — the pre-fix repro should FAIL (bug present), the
post-fix repro should PASS (bug gone):

| pre | post | verdict |
|---|---|---|
| passed | any | `not_reproduced` (invalid repro) |
| failed | (none) | `reproduced_unfixed` |
| failed | failed | `not_fixed` |
| failed | passed | `confirmed_fixed` (red→green) |

## Endpoints (admin only, audited)

- `POST /stepstitch/v1/session/{id}/verify` — body
  `{ "pre_passed": bool, "post_passed": bool|null, "fix_ref": "...", "run_url": "..." }` →
  stores the derived verdict. (Your CI calls this; the StepStitch repro workflow does it for you.)
- `GET /stepstitch/v1/session/{id}/verifications` — all verdicts for a trace.
- `GET /stepstitch/v1/corpus?verdict=confirmed_fixed&limit=50` — the regression corpus.

## Why it is the moat

Only an **executable** repro can certify a fix red→green — a session recording cannot. The
corpus compounds: every reproduced failure + its certified fix becomes permanent regression
evidence, and StepStitch is the neutral verifier regardless of which agent wrote the fix.
```

- [ ] **Step 4: Link from `docs/integrations/github.md`** — add this line under the "CI repro workflow" section:

```markdown
The workflow also reports the run outcome to the Verified-Fix engine — see
[verified-fix.md](verified-fix.md).
```

- [ ] **Step 5: Run + commit**

Run: `cd service && /tmp/ss-venv/bin/python -m pytest tests/test_github_content.py -q` → all pass.
```bash
git add service/stepstitch_service/github_bridge/workflow.py docs/integrations/verified-fix.md docs/integrations/github.md service/tests/test_github_content.py
git commit -m "feat(verified-fix): CI reports repro outcome to /verify + docs"
```

---

## Self-Review

- **Coverage:** verdict logic (T1), record/read/corpus endpoints + DDL (T2), CI reporting + docs (T3). The moat statement (certify red→green + corpus) is realized by T1+T2; T3 wires the customer loop.
- **No code execution by StepStitch:** verdicts come from CI-reported booleans; StepStitch only derives + stores. ✓
- **Privacy:** rows carry trace_id, booleans, verdict, fix_ref, run_url — no NPI; consistent with the audit table. ✓
- **No placeholders; complete code in every step.** ✓
- **Type consistency:** `derive_verdict(pre_passed, post_passed)`, `VERDICT_*` constants, `VerifyPayload(pre_passed, post_passed, fix_ref, run_url)`, `_verification_row` column order matches the SELECT and the DDL. ✓
- **Agent surface:** new routes are NOT added to `COPILOT_SAFE_OPERATIONS`, so MCP 3-way parity holds (verified in T2 Step 5). ✓
