"""Egress guard — the last check on anything that leaves toward an AI agent.

The ingest scrubber (``scrubber.py``) decides what is *stored*. It runs once, at the door,
and it cannot vouch for text written afterwards: the compiled reproduction, the local
run's console output, a failure signature, a summary. An agent reads all of those. This
module is the matching boundary on the way OUT — one pass over the whole outbound
document, run where responses leave for an agent (the host's agent-token path and the MCP
server), so a gap anywhere upstream is caught here instead of in someone else's model
context.

It is deliberately a *high-precision* subset of the ingest rules. Ingest may be aggressive
because it is looking at a customer's free text; egress is looking at evidence an engineer
needs verbatim — Playwright code full of URLs and timeouts, commands, timestamps, digests
and signatures. So egress runs the secret and encoded-payload detectors, emails, SSNs,
IBANs, IP and MAC addresses, Luhn-valid card numbers and any host-registered advisory
detector — and leaves out the generic URL, phone, date and long-number passes, whose
false positives on code would vandalise the reproduction.

Two modes:

- ``redact`` (default): return a redacted copy and a report of what was removed.
- ``scan``: return the document unchanged and a report of what *would* have been removed.
  Used for signed artifacts (attestation, FixProof) — editing a signed statement breaks its
  signature, so the right response to a finding there is a loud report, not a silent edit.

Detection is evidence, not proof: an empty report means no known shape was found, never
that no customer data is present. Names and postal addresses match no pattern here.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Tuple

from .scrubber import luhn_valid, redact_text_counted

# Built-in PII passes egress leaves out: each would fire on ordinary code and evidence.
_EGRESS_SKIP = frozenset({"url", "phone", "phone_intl", "date", "number", "card"})

# Values under these keys are cryptographic material StepStitch produced itself. They are
# high-entropy by design and are never customer text.
_STRUCTURAL_KEYS = frozenset({"signature", "signatures", "sig", "public_key", "key_id"})
_STRUCTURAL_SUFFIXES = ("sha256", "_digest")

# Digest and commit shapes inside running text ("digest sha256:3f1c… recorded") are
# protected from the entropy detector and restored afterwards.
_DIGEST_TOKEN = re.compile(r"(?:sha256:)?\b[0-9a-f]{40,64}\b")
_CARD_RUN = re.compile(r"\b(?:\d[ -]?){13,19}\b")

REDACT = "redact"
SCAN = "scan"


def egress_detector_kinds() -> List[str]:
    """The kinds the egress guard can report — the built-in set minus the passes it skips,
    plus the Luhn-confirmed card check it runs itself."""
    from .scrubber import built_in_detector_kinds

    skipped = {"url", "phone", "date", "number", "card"}
    kinds = [k for k in built_in_detector_kinds() if k not in skipped]
    return kinds + ["card"]


def _structural(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    k = key.lower()
    return k in _STRUCTURAL_KEYS or k == "digest" or k.endswith(_STRUCTURAL_SUFFIXES)


def redact_outbound_text(text: str) -> Tuple[str, Dict[str, int]]:
    """The egress detector set over one string: ``(text, {kind: count})``."""
    protected: List[str] = []

    def _protect(match: "re.Match[str]") -> str:
        protected.append(match.group(0))
        return f"\x00D{len(protected) - 1}\x00"

    work = _DIGEST_TOKEN.sub(_protect, text)
    out, counts = redact_text_counted(work, skip=_EGRESS_SKIP)
    out = out or ""

    def _card(match: "re.Match[str]") -> str:
        if not luhn_valid(re.sub(r"\D", "", match.group(0))):
            return match.group(0)
        counts["card"] = counts.get("card", 0) + 1
        return "[redacted:card]"

    out = _CARD_RUN.sub(_card, out)
    for index, original in enumerate(protected):
        out = out.replace(f"\x00D{index}\x00", original)
    return out, counts


def guard_outbound(doc: Any, mode: str = REDACT) -> Tuple[Any, Dict[str, Any]]:
    """Guard an outbound JSON-shaped document. Never mutates ``doc``.

    Returns ``(document, report)`` where ``report`` is
    ``{"mode": ..., "kinds": {kind: count}, "fields": [paths]}``. In ``scan`` mode the
    returned document is ``doc`` itself, untouched.
    """
    kinds: Dict[str, int] = {}
    fields: List[str] = []

    def _record(path: str, counts: Dict[str, int]) -> None:
        if not counts:
            return
        for kind, n in counts.items():
            kinds[kind] = kinds.get(kind, 0) + n
        if path not in fields:
            fields.append(path)

    def walk(value: Any, path: str) -> Any:
        if isinstance(value, str):
            out, counts = redact_outbound_text(value)
            _record(path, counts)
            return out
        if isinstance(value, list):
            return [walk(v, f"{path}[{i}]") for i, v in enumerate(value)]
        if isinstance(value, dict):
            clean: Dict[Any, Any] = {}
            for key, item in value.items():
                child = f"{path}.{key}" if path else str(key)
                new_key = key
                if isinstance(key, str):
                    new_key, counts = redact_outbound_text(key)
                    _record(child, counts)
                if _structural(key):
                    clean[new_key] = copy.deepcopy(item)
                else:
                    clean[new_key] = walk(item, child)
            return clean
        return value

    guarded = walk(doc, "")
    report = {"mode": mode, "kinds": kinds, "fields": fields}
    if mode == SCAN:
        return doc, report
    return guarded, report


__all__ = ["guard_outbound", "redact_outbound_text", "egress_detector_kinds", "REDACT", "SCAN"]
