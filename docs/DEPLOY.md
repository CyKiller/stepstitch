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
| `STEPSTITCH_ADMIN_TOKEN` | yes (unless SSO) | you | bearer for operator reads/exports; also the MCP connector's `STEPSTITCH_TOKEN`. Not required when OIDC SSO is enabled (below) |
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

> Demo-grade default: two shared bearer tokens (above). For FI / multi-operator
> deployments, enable **per-operator SSO** below — StepStitch core is unchanged (auth is
> host-injected). Audit events persist to the `stepstitch_audit` table (`make_db_audit`) on a
> separate Reg S-P clock; under SSO each record carries the **real operator identity**, not a
> shared `admin`.

### Operator SSO (OIDC) + RBAC

Set `STEPSTITCH_OIDC_ISSUER` to switch the operator surface from the shared admin token to
**per-operator OIDC** (RS256, validated against the IdP's JWKS). Any standards-compliant OIDC
issuer works. The SDK keeps using `STEPSTITCH_INGEST_TOKEN` (machine auth) — only the human
operator/admin surface uses SSO.

| Variable | Required (SSO) | Notes |
|---|---|---|
| `STEPSTITCH_OIDC_ISSUER` | yes | enables SSO; your IdP's issuer URL, e.g. `https://<your-oidc-issuer>/<tenant>` |
| `STEPSTITCH_OIDC_AUDIENCE` | yes | the API app-registration audience, e.g. `api://stepstitch` |
| `STEPSTITCH_OIDC_JWKS_URI` | no | discovered from the issuer's OpenID config if unset |
| `STEPSTITCH_OIDC_OPERATOR_ROLES` | no (default `stepstitch-operator`) | roles allowed on the read surface |
| `STEPSTITCH_OIDC_ADMIN_ROLES` | no (default `stepstitch-admin`) | roles allowed to deliver / delete / purge (least privilege) |
| `STEPSTITCH_OIDC_ROLES_CLAIM` | no (default `roles`) | JWT claim carrying the issuer's roles |

With SSO on, `STEPSTITCH_ADMIN_TOKEN` is not required. Map the issuer's roles
`stepstitch-operator` (read) and `stepstitch-admin` (destructive) to the relevant operator
groups; an operator without `stepstitch-admin` is denied deliver/delete/purge (403).

### Database migrations

The schema is managed by **Alembic** (`server/migrations/`). The ingest host runs
`alembic upgrade head` automatically at startup (in the FastAPI `lifespan`, before it
serves traffic), so a fresh `DATABASE_URL` is provisioned on first deploy with no manual
step. Migrations run on a sync psycopg2 engine and are independent of the asyncpg runtime
pool.

To apply migrations manually (e.g. against a new environment):

```bash
cd server
DATABASE_URL=postgresql://user:pass@host:5432/db alembic upgrade head
```

To author a new revision:

```bash
cd server
DATABASE_URL=... alembic revision -m "describe the change"   # creates versions/<rev>.py
# edit the generated upgrade()/downgrade(), then:
DATABASE_URL=... alembic upgrade head
```

The baseline revision `0001` applies `server.db.SCHEMA_SQL` verbatim, so the migrated
schema is identical to the idempotent `ensure_schema` used by the test harness.

**Adopting Alembic on an existing (pre-Alembic) database.** A database created by an
earlier release already has the three tables but no `alembic_version` row. The baseline is
written with `CREATE TABLE IF NOT EXISTS`, so the first boot on this release stamps the DB
to `0001` cleanly with no data loss. To keep the version table honest, **ship this
baseline-bearing release on its own and let every environment boot on it once (so each DB
is stamped to `0001`) before introducing any `0002`.** For a live DB you can pre-stamp
without running DDL: `cd server && DATABASE_URL=... alembic stamp head`.

**Multiple instances starting at once.** The baseline is fully idempotent, so concurrent
startups are safe. A *future non-idempotent* migration (e.g. an `ALTER TABLE` or a
backfill) is not — two instances racing `upgrade head` could both attempt it. For such
migrations, run them as a one-shot job / init step (not in every instance's `lifespan`),
or guard `command.upgrade` with a Postgres advisory lock.

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
