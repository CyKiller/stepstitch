"""Repo-wide guard: no unprovable absolute survives on any surface a reader sees.

The website had a scanner already, and it still missed the footer, the Open Graph card
and the site-wide meta description — because it enumerated **eleven files** while the
site had fifty-two. That is the same defect as enumerating exact phrases instead of
matching the shape, moved up one layer: an allowlist of *places* rather than an
allowlist of *words*.

So this guard inverts the default. It walks every text surface in the repository and
requires each hit to be **explicitly justified**, rather than requiring each file to be
explicitly included. A new page, a new MCP tool description, a new runbook or a new
issue template is covered the moment it exists.

The claim being enforced is the one the product actually keeps
(`docs/FINANCIAL-RELEASE-READINESS.md`): capture is minimized, known patterns are
scrubbed, and **arbitrary customer-data absence is not independently verified** — a
customer's name or street address in free text matches no SSN, card, email, phone, date
or long-digit pattern. "No NPI" was never a statement the code could support.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# The shapes, not a list of phrasings. Each is the class of statement the product
# cannot demonstrate, however it happens to be worded.
FORBIDDEN = (
    (re.compile(r"\b(no|zero)\s+NPI\b", re.I), "absence of NPI is not demonstrable"),
    (re.compile(r"\bnever\s+captures?\s+PII\b", re.I), "free text is user-authored"),
    (re.compile(r"\b(NPI|PII)-free\b", re.I), "states an absence nothing measures"),
    (re.compile(r"\bproving\s+no\s+(NPI|PII)\b", re.I), "asserts a proof that does not exist"),
    (re.compile(r"\bguarantees?\s+(no|zero)\b", re.I), "a guarantee is not a control"),
    (re.compile(r"\b(NPI|PII)\s+guarantee\b", re.I), "there is no such guarantee"),
    (re.compile(r"\b(no|zero)\b[^.!?\n]{0,60}\b(PII|NPI)\b", re.I),
     "absence of PII/NPI in user-authored text is not demonstrable"),
)

# Directories that are not a surface anyone reads as a claim.
SKIP_DIRS = (
    "node_modules", ".venv", ".git", "dist", "build", ".next", "test-results",
    ".claude", "coverage", "__pycache__", ".ruff_cache", ".pytest_cache",
)
SUFFIXES = {".ts", ".tsx", ".py", ".md", ".json", ".mjs", ".js", ".yml", ".yaml"}

# --- The justified exceptions ------------------------------------------------------
#
# Each entry says WHY the phrase is legitimate there. The rule the earlier release set:
# never mechanically rewrite a passage that describes a false claim AS false — doing so
# destroys the explanation of why the claim was removed. These are those passages, plus
# the machinery that enforces the rule and therefore has to name it.
JUSTIFIED = {
    # The enforcement machinery must contain the patterns it forbids.
    "service/tests/test_claim_surface.py": "this guard's own patterns",
    "web/tests/copy-claims.test.ts": "the website scanner's patterns and self-tests",
    "web/tests/claims-registry.test.ts": "asserts registered claims contain no absolute",
    # The canonical report lists the banned wording and documents the removals.
    "docs/FINANCIAL-RELEASE-READINESS.md": "records the banned wording and the fixes",
    # Documents that define the rule must be able to quote the wording they forbid.
    "contracts/stepstitch.md": "states the scrub report carries schema_status rather "
                               "than an unprovable 'no NPI' claim",
    "docs/STATUS.md": "the claim-registry ledger row lists the banned phrasings",
    # Tests that assert the ABSENCE of the phrase must be able to name it.
    "service/tests/test_github_content.py": "asserts 'no NPI' is NOT in the issue body",
    "service/tests/test_scrubber.py": "docstring states the hostile-POST thesis",
    "service/tests/test_mcp_surface.py": "drift guard over tool descriptions",
    "service/tests/test_adapter_profile_robustness.py": "NPI-marker matrix",
    "service/tests/test_similar_fixes.py": "module docstring",
    "service/tests/test_fragility_endpoints.py": "module docstring",
    "service/tests/test_diagnostics.py": "planted-credential fixtures",
    "tests/redaction-proof.test.ts": "the SDK proof suite names what it proves",
}


def _files():
    for path in REPO.rglob("*"):
        if not path.is_file() or path.suffix not in SUFFIXES:
            continue
        rel = path.relative_to(REPO)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        yield rel, path


def _strip_comments(text: str, suffix: str) -> str:
    """A code comment explaining a removed claim is not a claim made to a reader."""
    if suffix in {".ts", ".tsx", ".js", ".mjs"}:
        text = re.sub(r"/\*[\s\S]*?\*/", " ", text)
        text = re.sub(r"(^|[^:])//.*$", r"\1", text, flags=re.M)
    elif suffix == ".py":
        text = re.sub(r"^\s*#.*$", "", text, flags=re.M)
    return text


def _violations(rel, path):
    text = _strip_comments(path.read_text(encoding="utf-8", errors="ignore"), path.suffix)
    out = []
    for pattern, why in FORBIDDEN:
        for match in pattern.finditer(text):
            line = text[: match.start()].count("\n") + 1
            out.append(f"{rel}:{line} {match.group(0)!r} — {why}")
    return out


def test_no_unprovable_absolute_survives_anywhere():
    """The whole repository, not an enumerated subset."""
    found = []
    for rel, path in _files():
        if str(rel) in JUSTIFIED:
            continue
        found.extend(_violations(rel, path))
    assert not found, (
        "Unprovable absolute claims found. Replace with what is demonstrable — "
        "'no screens, input values or page text; free text is policy-scrubbed' — or, "
        "if the passage legitimately describes a false claim as false, add it to "
        "JUSTIFIED with a reason:\n  " + "\n  ".join(sorted(found))
    )


def test_the_guard_catches_the_phrasings_that_escaped_the_website_scanner():
    """Self-test using the exact strings that were live in production."""
    escaped = [
        "No screens, no input values, no PII.",          # footer + Open Graph card
        "no screens, input values, or PII",              # site-wide meta description
        "with no NPI captured at any point",             # financial pilot runbook
        "Scrubbed / No NPI",                             # Salesforce integration
        "the no-NPI guarantee is unchanged",             # status ledger
        "structural and NPI-free",                       # MCP / integration docs
    ]
    for phrase in escaped:
        assert any(p.search(phrase) for p, _ in FORBIDDEN), f"not caught: {phrase}"

    # …and the replacement wording, which stops at what is demonstrable, passes.
    for honest in (
        "No screens, input values or page text; free text is policy-scrubbed.",
        "Customer-data absence is not independently verified.",
        "Policy scrubbed / data unverified",
    ):
        assert not any(p.search(honest) for p, _ in FORBIDDEN), f"false positive: {honest}"


def test_every_justified_entry_still_exists_and_still_needs_the_exception():
    """An exception that no longer applies is how an allowlist rots into a loophole."""
    stale = []
    for rel, reason in JUSTIFIED.items():
        path = REPO / rel
        if not path.exists():
            stale.append(f"{rel} (listed but missing) — {reason}")
            continue
        if not _violations(Path(rel), path):
            stale.append(f"{rel} (no longer contains any absolute) — {reason}")
    assert not stale, (
        "JUSTIFIED entries that are no longer needed — remove them:\n  "
        + "\n  ".join(stale)
    )


@pytest.mark.parametrize("surface", [
    "GOVERNANCE.md",
    "CONTRIBUTING.md",
    "contracts/stepstitch.md",
    "docs/STATUS.md",
    "docs/targets/financial-services-pilot.md",
    "docs/integrations/salesforce.md",
    "copilot/action-policy.md",
    "copilot/openapi-v2.json",
    "service/stepstitch_service/mcp_server.py",
    "src/types.ts",
])
def test_named_high_stakes_surfaces_are_covered(surface):
    """These are the surfaces a regulated reviewer, a contributor or an AI agent reads
    directly.

    The property under test is COVERAGE, not silence: each must still be reachable by
    the walk above, so moving one under a skipped directory (or narrowing SUFFIXES)
    fails loudly instead of quietly shrinking the guard. A file may legitimately quote
    the banned wording — `contracts/stepstitch.md` and `docs/STATUS.md` both define the
    rule — and that is what JUSTIFIED is for; what must never happen is a surface
    dropping out of the scan altogether.
    """
    path = REPO / surface
    assert path.exists(), f"{surface} moved or was deleted; update this guard"
    walked = {str(rel) for rel, _ in _files()}
    assert surface in walked, (
        f"{surface} is no longer reached by the walk — a skipped directory or a "
        "narrowed suffix list has silently removed it from the guard"
    )
    if surface not in JUSTIFIED:
        assert not _violations(Path(surface), path)
