"""The public demo console: the real operator UI, over synthetic data, with no credentials.

Everything about StepStitch is invisible until someone deploys it, which is a bad way to
evaluate a product whose entire claim is about what it *shows* you. This mounts a second,
credential-free copy of the console at ``/demo`` — the **same** ``DASHBOARD_HTML``, driven by
the **same** ``create_stepstitch_router``, so it cannot drift from the real thing. What
changes is only what sits underneath it: an immutable in-memory dataset instead of Postgres.

Three independent reasons it cannot mutate anything:

1. ``_ReadOnlyStore.execute`` does nothing at all — there is no write path to reach.
2. A middleware refuses any method other than GET/HEAD, except the two draft-preview POSTs
   the console needs (which are pure functions of the trace and write nothing).
3. It is a separate sub-application with its own dependency overrides, so the production
   ``/api`` and ``/admin`` routes keep their real auth. Nothing here loosens them.

The dataset is built by ``scripts/build_demo_dataset.py`` from the real pipeline and
committed at ``server/demo_dataset.json``.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from stepstitch_service import create_stepstitch_router, generate_playwright_test
from stepstitch_service.evidence import ASSERTED
from stepstitch_service.execution import execution_summary
from stepstitch_service.profiles import load_profile
from stepstitch_service.repro_config import ReproConfig, readiness

from .dashboard import DASHBOARD_HTML
from .fonts import GEIST_SANS_WOFF2_B64

DATASET_PATH = pathlib.Path(__file__).resolve().parent / "demo_dataset.json"

# The app under test that the demo's generated reproductions point at. Fictional on purpose:
# it must never be a URL anyone could actually be pointed at.
DEMO_BASE_URL = "https://demo-bank.example.test"

# POSTs the console makes that are pure previews — they compute a draft from a trace and
# store nothing. Everything else is refused regardless of method.
_PREVIEW_SUFFIXES = ("/export-preview", "/financial-services-export-preview")


def load_dataset(path: pathlib.Path = DATASET_PATH) -> Dict[str, Any]:
    return json.loads(path.read_text())


class _ReadOnlyStore:
    """Serves the router's queries from memory. ``execute`` is a no-op by construction.

    The router speaks a small, fixed set of SQL statements (all of them ``?``-placeholder
    reads). This answers those and nothing else: an unrecognised query returns empty rather
    than guessing, so a new query surfaces as a visibly missing panel rather than as
    plausible-looking fabricated data.
    """

    def __init__(self, dataset: Dict[str, Any]) -> None:
        self.traces: List[Dict[str, Any]] = list(dataset.get("traces", []))
        self.verifications: List[Dict[str, Any]] = list(dataset.get("verifications", []))
        self.audit: List[Dict[str, Any]] = list(dataset.get("audit", []))
        self._by_id = {t["id"]: t for t in self.traces}
        # Newest first, matching every ORDER BY created_at DESC in the router.
        self._traces_desc = sorted(self.traces, key=lambda t: t["created_at"], reverse=True)
        self._verifs_desc = sorted(
            self.verifications, key=lambda v: v["created_at"], reverse=True)
        self.writes_attempted = 0

    async def execute(self, query: str, params: Tuple = ()) -> None:
        # Demo data is immutable. Count attempts so a test can assert none happen.
        self.writes_attempted += 1

    async def fetchone(self, query: str, params: Tuple = ()) -> Optional[Tuple]:
        q = " ".join(query.split())
        if q.startswith("SELECT count(*)"):
            table = q.split("FROM ")[1].split()[0]
            return ({"stepstitch_traces": len(self.traces),
                     "stepstitch_audit": len(self.audit),
                     "stepstitch_verifications": len(self.verifications),
                     "stepstitch_agents": 0}.get(table, 0),)
        if "FROM stepstitch_config" in q:
            return None  # no operator overrides in the demo
        if q.startswith("SELECT verdict, fix_ref, run_url, evidence_grade "
                        "FROM stepstitch_verifications"):
            for v in self._verifs_desc:
                if v["trace_id"] == params[0]:
                    return (v["verdict"], v["fix_ref"], v["run_url"],
                            v.get("evidence_grade", ASSERTED))
            return None

        row = self._by_id.get(params[0]) if params else None
        if row is None:
            return None
        if q.startswith("SELECT footsteps, project_id, trace_metadata"):
            return (row["footsteps"], row["project_id"], row["trace_metadata"])
        if q.startswith("SELECT footsteps, project_id"):
            return (row["footsteps"], row["project_id"])
        if q.startswith("SELECT footsteps, explanation, user_id, project_id, created_at"):
            return (row["footsteps"], row["explanation"], row["user_id"],
                    row["project_id"], row["created_at"])
        if q.startswith("SELECT footsteps FROM stepstitch_traces"):
            return (row["footsteps"],)
        if q.startswith("SELECT trace_metadata FROM stepstitch_traces"):
            return (row["trace_metadata"],)
        return None

    async def fetchall(self, query: str, params: Tuple = ()) -> List[Tuple]:
        q = " ".join(query.split())

        if q.startswith("SELECT id, app_id, project_id, user_id, explanation, created_at"):
            limit = int(params[-1]) if params else 50
            return [(t["id"], t["app_id"], t["project_id"], t["user_id"],
                     t["explanation"], t["created_at"]) for t in self._traces_desc[:limit]]

        if q.startswith("SELECT id, action, actor, detail, created_at"):
            limit = int(params[-1]) if params else 50
            rows = sorted(self.audit, key=lambda a: a["created_at"], reverse=True)
            return [(a["id"], a["action"], a["actor"], a["detail"], a["created_at"])
                    for a in rows[:limit]]

        if q.startswith("SELECT id, fingerprint, created_at FROM stepstitch_traces"):
            limit = int(params[0]) if params else 500
            return [(t["id"], t["fingerprint"], t["created_at"])
                    for t in self._traces_desc if t["fingerprint"]][:limit]

        if q.startswith("SELECT trace_id, fix_ref, run_url, fingerprint, evidence_grade "
                        "FROM stepstitch_verifications"):
            want = params[0] if params else None
            grades = set(params[1:3])
            return [
                (v["trace_id"], v["fix_ref"], v["run_url"], v["fingerprint"],
                 v.get("evidence_grade", ASSERTED))
                for v in self._verifs_desc
                if v["verdict"] == want and v.get("fingerprint") is not None
                and v.get("evidence_grade", ASSERTED) in grades
            ]
        if q.startswith("SELECT trace_id, verdict FROM stepstitch_verifications"):
            limit = int(params[0]) if params else 500
            return [(v["trace_id"], v["verdict"]) for v in self._verifs_desc[:limit]]

        if q.startswith("SELECT trace_id, fix_ref, run_url, fingerprint"):
            verdict, limit = params[0], int(params[1])
            return [(v["trace_id"], v["fix_ref"], v["run_url"], v["fingerprint"])
                    for v in self._verifs_desc
                    if v["verdict"] == verdict and v["fingerprint"]][:limit]

        if q.startswith("SELECT trace_id, pre_passed, post_passed, verdict, fix_ref, run_url"):
            if "WHERE trace_id = ?" in q:
                rows = [v for v in self._verifs_desc if v["trace_id"] == params[0]]
            else:  # the corpus: WHERE verdict = ? LIMIT ?
                rows = [v for v in self._verifs_desc if v["verdict"] == params[0]]
                rows = rows[:int(params[1])]
            return [(v["trace_id"], v["pre_passed"], v["post_passed"], v["verdict"],
                     v["fix_ref"], v["run_url"], v["created_at"]) for v in rows]

        return []


def render_dashboard(nonce: str, *, demo: bool) -> str:
    """The one console template, in operator mode or public-demo mode."""
    # The API base is derived in the browser from the page's own path, so this template
    # works unchanged at "/dashboard", "/demo/dashboard", or behind a site proxy.
    return (
        DASHBOARD_HTML
        .replace("__CSP_NONCE__", nonce)
        .replace("__FONT_SANS_B64__", GEIST_SANS_WOFF2_B64)
        .replace("__DEMO_MODE__", "true" if demo else "false")
    )


def dashboard_csp(nonce: str) -> str:
    return (
        "default-src 'none'; "
        f"script-src 'nonce-{nonce}'; "
        "style-src 'unsafe-inline'; "
        "connect-src 'self'; "
        "img-src 'self' data:; "
        "font-src data:; "
        "base-uri 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'none'"
    )


def build_demo_app(dataset: Optional[Dict[str, Any]] = None) -> FastAPI:
    """A credential-free, read-only copy of the console over synthetic data."""
    import secrets

    store = _ReadOnlyStore(dataset if dataset is not None else load_dataset())
    profile = load_profile("financial-services-enterprise")

    async def _no_audit(action: str, actor: str, detail: dict) -> None:
        return None  # the demo's audit trail is part of the dataset, not written at runtime

    async def _repro_config() -> ReproConfig:
        return ReproConfig.from_dict({
            "base_url": DEMO_BASE_URL,
            "route_params": {"id": "1001"},
            "auth": {"fixture": "tests/auth.setup.ts", "env_vars": ["E2E_USER_EMAIL"]},
        })

    router = create_stepstitch_router(
        # No credential is required or accepted: the demo has nothing worth gating.
        get_user_id=lambda: "demo",
        require_admin=lambda: {"user_id": "demo"},
        execute=store.execute,
        fetchone=store.fetchone,
        fetchall=store.fetchall,
        audit=_no_audit,
        generate_playwright_test=generate_playwright_test,
        base_url=DEMO_BASE_URL,
        scrub_policy=profile,
        repro_config_provider=_repro_config,
    )

    app = FastAPI(title="StepStitch demo console", docs_url=None, redoc_url=None)
    app.include_router(router, prefix="/api")

    @app.middleware("http")
    async def _read_only(request, call_next):
        # Defence in depth. The store cannot write, but a demo that merely *looks* immutable
        # is not the same as one that refuses.
        if request.method not in ("GET", "HEAD"):
            if not any(request.url.path.endswith(s) for s in _PREVIEW_SUFFIXES):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "the demo console is read-only"},
                )
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    @app.get("/dashboard")
    async def demo_dashboard() -> HTMLResponse:
        nonce = secrets.token_urlsafe(16)
        return HTMLResponse(content=render_dashboard(nonce, demo=True),
                            headers={"Content-Security-Policy": dashboard_csp(nonce)})

    # Demo twins of the admin reads the console makes. Read-only, fixture-backed.
    @app.get("/admin/status")
    async def demo_status() -> dict:
        return {
            "status": "ok", "profile": profile.name, "retention_days": 30,
            "traces": len(store.traces), "audit_events": len(store.audit),
            "agents_total": 2, "agents_active": 2,
            "verifications": len(store.verifications),
            "base_url_configured": True, "repro_config_ready": True,
            "demo": True,
        }

    @app.get("/admin/config/scrub")
    async def demo_scrub_config() -> dict:
        return {"status": "ok", "base_profile": profile.name,
                "extra_redactions": [], "extra_forbidden_keys": []}

    @app.get("/admin/config/repro")
    async def demo_repro_config() -> dict:
        cfg = await _repro_config()
        return {"status": "ok", "config": cfg.as_dict(), "env_base_url": DEMO_BASE_URL,
                "default_base_url": DEMO_BASE_URL, "readiness": []}

    @app.get("/admin/session/{trace_id}/execution")
    async def demo_execution(trace_id: str) -> dict:
        # The same projection the real host serves (execution_summary over the
        # trace's readiness + verification rows), so the console's unified
        # status header renders — and stays honest — in the demo too.
        trace = next((t for t in store.traces if t["id"] == trace_id), None)
        if trace is None:
            return JSONResponse(status_code=404, content={"detail": "Trace not found"})
        cfg = await _repro_config()
        footsteps = json.loads(trace["footsteps"])
        rows = [v for v in store.verifications if v.get("trace_id") == trace_id]
        summary = execution_summary(
            readiness(cfg, footsteps, fallback_base_url=DEMO_BASE_URL),
            verifications=rows,
        )
        return {"status": "ok", "trace_id": trace_id, "demo": True,
                "profile": profile.name, "customer_data_status": "not_verified",
                **summary}

    @app.get("/admin/agents")
    async def demo_agents() -> dict:
        # Illustrative only — no token exists for any of these, and none can be issued.
        return {"status": "ok", "agents": [
            {"id": "agt_demo_assistant", "name": "Coding assistant (read-only)",
             "scope": "repros", "revoked": False,
             "created_at": "2026-07-14T10:00:00+00:00", "created_by": "demo"},
            {"id": "agt_demo_ci", "name": "CI verification", "scope": "verify",
             "revoked": False,
             "created_at": "2026-07-14T10:05:00+00:00", "created_by": "demo"},
        ]}

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok", "demo": True}

    return app
