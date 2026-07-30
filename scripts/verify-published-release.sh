#!/usr/bin/env bash
# Meet StepStitch the way a stranger does: published artifacts only, no checkout.
#
#   scripts/verify-published-release.sh 0.9.1
#
# This exists because green CI has twice said a release was fine when it was not — the
# launcher was missing from npm entirely, and then the launcher installed an engine
# without the extra that `start` needs. Both survived a full CI run because the first-run
# gate tests a LOCAL pack of the shim. Only the real registries can answer the question
# a release actually makes, so this script refuses to look at the working tree.
#
# Run it after publishing, and before telling anyone the release is good.
set -euo pipefail

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
  echo "usage: $0 <version>   e.g. $0 0.9.1" >&2
  exit 2
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/stepstitch-verify.XXXXXX")"
SERVER_PID=""
cleanup() {
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

# A port nobody else is on. A stale server from an earlier run answering /healthz would
# make this script report success for a build it never launched — the exact false pass
# it exists to prevent.
free_port() {
  python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
}
PORT="$(free_port)"

say() { printf '\n== %s ==\n' "$1"; }

say "1/4  PyPI: a clean venv installs stepstitch-service[local]==${VERSION}"
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install -q "stepstitch-service[local]==${VERSION}"
"$WORK/venv/bin/python" - <<'PY'
import pathlib
import stepstitch_service
from stepstitch_service.evidence import derive_grade
from stepstitch_service.runner import script_digest  # noqa: F401  (import must work)

pkg = pathlib.Path(stepstitch_service.__file__).parent
assert (pkg / "py.typed").exists(), "py.typed is missing from the published wheel"
# A claimed grade must not survive into the published build either.
assert derive_grade(measured_by_stepstitch=False, signature="sig") == "asserted"
print("   wheel installs; py.typed present; evidence + runner import")
PY

say "2/4  npm: the launcher and the tracker are both published"
npm view "stepstitch@${VERSION}" version >/dev/null
npm view "@stepstitch/tracker@${VERSION}" version >/dev/null
echo "   stepstitch@${VERSION} and @stepstitch/tracker@${VERSION} are on the registry"

say "3/4  npx stepstitch start, on a machine with no checkout (port ${PORT})"
export STEPSTITCH_ADMIN_TOKEN=stranger-admin STEPSTITCH_INGEST_TOKEN=stranger-ingest
npx -y "stepstitch@${VERSION}" start --no-browser --port "$PORT" \
  --db "$WORK/local.db" > "$WORK/start.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 90); do
  curl -sf "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1 && break
  sleep 2
done
if ! curl -sf "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
  echo "   FAIL: never became healthy. Server output:" >&2
  cat "$WORK/start.log" >&2
  exit 1
fi
echo "   healthy"

say "4/4  a stranger's report becomes a reproduction"
TRACE="$(curl -s -X POST "http://127.0.0.1:${PORT}/api/stepstitch/v1/session" \
  -H "Authorization: Bearer stranger-ingest" -H "Content-Type: application/json" \
  -d '{"app_id":"stranger","footsteps":[{"timestamp":"t","type":"exception","route":"/x","label":"[masked]","metadata":{"error_type":"TypeError"}}],"metadata":{}}' \
  | "$WORK/venv/bin/python" -c "import json,sys; print(json.load(sys.stdin).get('trace_id',''))")"
[ -n "$TRACE" ] || { echo "   FAIL: ingest returned no trace_id" >&2; exit 1; }
# The checker lives in a file, not a heredoc: piping curl into `python - <<EOF` gives the
# heredoc stdin, so the program would read an empty stream and never see the response.
cat > "$WORK/check_repro.py" <<'PY'
import json
import sys

code = json.load(sys.stdin)["playwright_code"]
# The exception assertion must carry e.name: matching on e.message alone made every
# exception reproduction vacuously pass (fixed in Phase 3 — this keeps it shipped).
assert "${e.name}: ${e.message}" in code, "the e.name fix is missing from the published build"
assert "import { test, expect }" in code
print("   compiled a reproduction that asserts the reported failure")
PY
curl -s -H "Authorization: Bearer stranger-admin" \
  "http://127.0.0.1:${PORT}/api/stepstitch/v1/session/${TRACE}/playwright" \
  | "$WORK/venv/bin/python" "$WORK/check_repro.py"

printf '\nAll stranger checks passed for %s\n' "$VERSION"
