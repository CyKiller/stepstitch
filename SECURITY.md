# Security Policy

StepStitch handles a privacy-critical boundary (it must never persist or expose NPI), so
security reports are taken seriously.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Instead, report privately via one of:

- GitHub **Security Advisories**: use the *"Report a vulnerability"* button under the
  repository's **Security** tab (preferred — creates a private advisory).
- Email the maintainer: **devway83@gmail.com** with subject `SECURITY: StepStitch`.

Please include: affected version/commit, a description, reproduction steps, and the impact
(especially any path that could cause NPI to be captured, stored, logged, or returned).

## What to expect

- **Acknowledgement:** within 3 business days.
- **Triage + severity assessment:** within 7 business days.
- **Fix / coordinated disclosure:** timeline shared after triage; we'll credit you unless you
  prefer to remain anonymous.

## Scope highlights

High-priority classes of issue for StepStitch:

- Any way the SDK or service captures, stores, logs, or returns input values, page text,
  screenshots, raw URLs, request/response bodies, headers, cookies, stack traces, or the
  free-text explanation.
- Any way the scrubber (`service/stepstitch_service/scrubber.py`) can be bypassed.
- Any way a destructive or direct-write operation becomes reachable from the MCP / Copilot
  agent surface.
- Auth/audit bypass on admin endpoints.

## Operational security

Self-host incident-response guidance (kill switch, retention purge, forensics) lives in
[INCIDENT-RESPONSE.md](INCIDENT-RESPONSE.md). Supply-chain posture (SBOM, SRI, signed tags)
is described in [RELEASE.md](RELEASE.md).
