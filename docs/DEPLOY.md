# StepStitch — deployment & packaging

How to install and run StepStitch as a product. Companion to
[PRODUCT-PLAN.md](PRODUCT-PLAN.md) (P3) and [../COMMERCIAL.md](../COMMERCIAL.md).

## The deployable units

StepStitch ships as three things, not one monolith:

| Unit | What it is | Install |
|---|---|---|
| **SDK** (`@stepstitch/tracker`) | browser capture + redaction | `npm i @stepstitch/tracker` |
| **Service** (`stepstitch-service`) | privacy/repro engine — a **library** a host mounts | `pip install stepstitch-service` |
| **MCP connector** | the universal agentic surface | `pip install 'stepstitch-service[mcp]'` |
| **Ingest API host** (`server/`) | a ready-to-run FastAPI app that mounts the service — the Railway/Docker deploy target | `docker build . ` / `railway up` |

The service is a **decoupled router factory**, not a standalone server: the host injects
its own auth + DB and mounts the router. This is deliberate — StepStitch never holds your
identity provider or database. See `contracts/stepstitch.md`. The repo includes a
reference host in `server/` (demo shared-bearer auth + asyncpg) so you can deploy today —
see [Deploy on Railway](#deploy-the-ingest-api-on-railway) below.

## 1. Mount the service in your host app

```python
from stepstitch_service import create_stepstitch_router, generate_playwright_test
from stepstitch_service.profiles import load_profile

router = create_stepstitch_router(
    get_user_id=my_auth_dependency,         # FastAPI dependency
    require_admin=my_admin_dependency,
    execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
    audit=my_audit_sink,
    generate_playwright_test=generate_playwright_test,
    capture_enabled=my_killswitch_flag,     # org-wide incident kill switch
    scrub_policy=load_profile("financial-services-enterprise"),
    # Commercial pack (optional): system-of-record draft adapters.
    # from stepstitch_service.integrations.bundle import default_draft_adapters
    # draft_adapters=default_draft_adapters(),
)
app.include_router(router, prefix="/api")
```

The **open core runs with no adapters**: every read-only/draft operation works; export
previews return an empty draft set until the commercial adapter pack is injected.

## Deploy the ingest API on Railway

The `server/` host (FastAPI + asyncpg, demo shared-bearer auth) is the deploy target. The
root `Dockerfile` builds it and `railway.json` health-checks `/healthz`.

**Steps**
1. From the repo root: `railway up` (creates the project + service and deploys the Dockerfile).
2. Add a Postgres: `railway add --database postgres` — Railway injects `DATABASE_URL`.
3. Set the variables below, then redeploy.

**Variables to set**

| Variable | Required | Provided by | Notes |
|---|---|---|---|
| `DATABASE_URL` | yes | **Railway Postgres** (auto) | added when you attach the Postgres plugin |
| `PORT` | — | **Railway** (auto) | the Dockerfile binds uvicorn to `$PORT` |
| `STEPSTITCH_ADMIN_TOKEN` | yes | you | bearer for operator reads/exports; also the MCP connector's `STEPSTITCH_TOKEN` |
| `STEPSTITCH_INGEST_TOKEN` | yes | you | bearer the SDK/clients use to POST traces |
| `STEPSTITCH_PROFILE` | no (default FS) | you | `financial-services-enterprise` / `healthcare-strict` / `internal-enterprise` / `open-source-default` |
| `RETENTION_DAYS` | no (default 30) | you | trace-body retention window |
| `STEPSTITCH_ENABLE_ADAPTERS` | no (default on) | you | `0` to run open-core only (no ServiceNow/Salesforce/Genesys drafts) |

```bash
railway variables \
  --set "STEPSTITCH_ADMIN_TOKEN=$(openssl rand -hex 24)" \
  --set "STEPSTITCH_INGEST_TOKEN=$(openssl rand -hex 24)" \
  --set "STEPSTITCH_PROFILE=financial-services-enterprise"
```

Then point the SDK at `https://<your-app>.up.railway.app/api/stepstitch/v1/session` and
the MCP connector at `…/api/stepstitch/v1` with `STEPSTITCH_TOKEN=$STEPSTITCH_ADMIN_TOKEN`.

> Demo-grade auth: two shared bearer tokens. For production, replace `server/auth.py`'s
> `build_auth` with a real JWT/OIDC verifier — no change to StepStitch core. Audit events
> are logged in the demo host; persist them to a separate 5-year store for Reg S-P.

## 2. Deployment posture — the `STEPSTITCH_PROFILE` knob

A profile is a named scrub posture; it may only *tighten* the privacy boundary, never
weaken it. Pick per vertical (drift-guarded by `test_profiles.py`):

| Profile | free-text | forbidden keys |
|---|---|---|
| `financial-services-enterprise` (default) | scrub | drop |
| `healthcare-strict` | disabled | reject (422) |
| `internal-enterprise` | scrub (longer notes) | drop |
| `open-source-default` | scrub | drop |

## 3. Run the MCP connector (the universal agentic surface)

```bash
pip install 'stepstitch-service[mcp]'
export STEPSTITCH_BASE_URL="https://stepstitch.internal/api/stepstitch/v1"
export STEPSTITCH_TOKEN="<operator-bearer-token>"   # admin; reads are audited
python -m stepstitch_service.mcp_cli
```

Or containerized (`service/Dockerfile.mcp`):

```bash
docker build -f service/Dockerfile.mcp -t stepstitch-mcp ./service
docker run --rm -i \
  -e STEPSTITCH_BASE_URL="https://stepstitch.internal/api/stepstitch/v1" \
  -e STEPSTITCH_TOKEN="$OPERATOR_TOKEN" stepstitch-mcp
```

Register it with any MCP client — see [../copilot/MCP-SETUP.md](../copilot/MCP-SETUP.md).
Transport is stdio today; remote clients (Copilot Studio) front it with streamable-HTTP.

## 4. Open-core boundary (what's publishable as OSS)

Apache-2.0 core vs. commercial pack is defined in [../COMMERCIAL.md](../COMMERCIAL.md) and
**enforced**: `test_open_core_boundary.py` (dependency-free AST check) and the
`.importlinter` contract (`lint-imports`) both prove no core module imports a commercial
adapter. The commercial adapters live in this repo for now but are import-isolated, so they
extract into a separate distribution without touching core.

## Release steps (gated)

- **npm:** the SDK is Apache-2.0 with `publishConfig.access=public`. `private:true` is kept
  as a safety gate — flip it to publish (`npm publish`). *(Requires npm credentials.)*
- **PyPI:** `python -m build` in `service/` → `twine upload`. *(Requires PyPI credentials.)*
- **Image:** `service/Dockerfile.mcp` is written but not yet built/pushed in this repo.

These are credential-gated, not engineering-gated (mirrors STATUS.md).
