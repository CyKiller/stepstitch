"""The StepStitch host, packaged: everything ``stepstitch start`` needs from PyPI.

Until Phase 1 these modules lived at the repo's ``server/`` — the reference deployment —
which meant the published ``stepstitch-service`` wheel could compile reproductions but
could not *serve* anything: no dashboard, no auth, no storage wiring. StepStitch Local's
promise (``npx stepstitch start`` on a clean machine) requires the host in the package,
so the deployment-agnostic host modules moved here.

``server/`` remains as the repo-level deployment layer: thin import shims for
compatibility (every existing ``from server.X import …`` keeps working), plus the pieces
that only make sense with a repo/container around them — the production entrypoint
(``app.py``), Postgres migrations, OIDC (whose ``pyjwt`` dependency stays out of the
base wheel), cosign signing, and the demo entrypoint.
"""
