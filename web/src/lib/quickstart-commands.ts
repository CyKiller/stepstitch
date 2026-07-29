// Single source of truth for the install commands the product documents. The quickstart
// page renders these, and tests/quickstart-parity.test.ts asserts the repository README
// documents the same commands verbatim, so the website and README cannot drift apart.
// Every command here must work, in this order, on a clean machine with only the stated
// prerequisites — that claim is enforced by the clean-install CI gate.

/** Journey A — add the SDK to an app. Needs Node and npm only. */
export const SDK_INSTALL = "npm install @stepstitch/tracker";

/**
 * Journey B — prove the loop offline. Needs Git, Node 20+, and Python 3.10+.
 * The demo imports the real service modules, so the service package must be installed
 * before `npm run demo`; the venv keeps that install disposable.
 */
export const OFFLINE_DEMO = `git clone https://github.com/CyKiller/stepstitch.git
cd stepstitch
python3 -m venv .venv
source .venv/bin/activate
pip install ./service
npm run demo
npm run smoke`;

/** Windows (PowerShell) replacement for the activate line above. */
export const OFFLINE_DEMO_WINDOWS_ACTIVATE = ".venv\\Scripts\\Activate.ps1";

/** Journey C — the full host. Docker path. */
export const DOCKER_UP = "docker compose up --build";

/** Seeding requires both variables — the script refuses to guess them. */
export const DOCKER_SEED = `STEPSTITCH_BASE_URL=http://localhost:8000 STEPSTITCH_INGEST_TOKEN=dev-ingest \\
  node scripts/seed-demo-trace.mjs`;

/**
 * doctor must run where the Compose variables actually live — inside the container.
 * Run on the host shell it would report missing env, because DATABASE_URL and the
 * tokens exist only in the container environment.
 */
export const DOCKER_DOCTOR = "docker compose exec stepstitch stepstitch doctor";

/** Journey C — manual path, in an order that works on a clean machine. */
export const MANUAL_HOST = `python3 -m venv .venv && source .venv/bin/activate
pip install ./service
pip install -r server/requirements.txt
export DATABASE_URL=postgres://localhost/stepstitch
export STEPSTITCH_INGEST_TOKEN=dev-ingest
export STEPSTITCH_ADMIN_TOKEN=dev-admin
export STEPSTITCH_APP_BASE_URL=https://staging.your-app.example
uvicorn server.app:app --port 8000`;

/** Same shell as the exports above, or doctor cannot see the configuration. */
export const MANUAL_DOCTOR = "stepstitch doctor";
