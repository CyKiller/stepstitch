// Best-effort: point git at the repo's hooks (.githooks/) so the CyKiller-only
// authorship enforcement is active on every clone without a manual step. See
// .githooks/README.md. Runs from `prepare` on `npm install`.
//
// This must NEVER fail an install: it no-ops outside a git work tree (e.g. when
// installed from the published tarball, where .githooks isn't shipped) and
// swallows any git error.
import { execSync } from "node:child_process"
import { existsSync } from "node:fs"

try {
  if (existsSync(".githooks")) {
    execSync("git config core.hooksPath .githooks", { stdio: "ignore" })
  }
} catch {
  // Not a git work tree, or git unavailable — hook wiring is optional, ignore.
}
