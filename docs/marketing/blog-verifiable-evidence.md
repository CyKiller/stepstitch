# Your AI agents are acting on evidence nobody can verify

*Draft blog post / launch essay. ~800 words. Voice: technical, declarative, no hype.*

---

We spent the last decade making it easy to *capture* what happened when software broke — session
recordings, traces, replays. We spent almost no time on a harder question that suddenly matters a
great deal: **can anyone prove the evidence is real?**

That question used to be academic. A human engineer looked at a recording, used judgment, moved on.
But the consumer of troubleshooting evidence is changing. Increasingly it's an **agent** — reading a
trace, proposing a fix, sometimes opening the PR. And when an automated system acts on evidence, the
unanswered questions compound:

- What *produced* this evidence — which build, which capture, which policy?
- Has it been **tampered with** since?
- What did it **contain** — did it carry a customer's PII into a model's context?
- Can a regulator or a customer verify any of that **without trusting the vendor that produced it?**

Today, for every mainstream tool, the answer is no. Session replays live in a vendor's cloud:
not portable, not deterministic, not independently verifiable. Observability traces aren't signed.
CI has pass/fail but no privacy proof. The evidence is a black box you're asked to trust.

## The supply chain already solved this

We've seen this movie. A decade ago, "is this build what it claims to be?" was also a black box —
until **SLSA**, **in-toto**, **Sigstore**, and **SBOMs** turned software provenance into something
you can verify with a command, no trust required. Signed, tamper-evident, portable.

**Troubleshooting evidence needs the same treatment.** Not "trust our dashboard" — a signed,
canonical artifact anyone can check.

## What a verifiable evidence bundle looks like

StepStitch 0.6 ships **Evidence Attestation**. For any reproduced bug, it composes the facts that
already exist into a canonical bundle:

- the **scrub report** — what was redacted, under which policy;
- the **replayability** score — is the repro reliable;
- the **verification verdict** — did the fix go red→green;
- the **build** that captured it.

It serializes that deterministically (sorted keys, no whitespace) and produces a `sha256` **anyone
can recompute with no tooling**. If you configure a key, the host signs the canonical bytes with
**your** key via `cosign` — StepStitch never holds one. To verify, independently:

```bash
# 1. recompute the hash — no account, no vendor
sha256sum <(jq -cS . bundle.json)   # must equal bundle_sha256

# 2. if signed, verify with the producer's public key
cosign verify-blob --key tenant.pub --signature attestation.sig bundle.json
```

The bundle is structural and structural by construction — it only composes already-sanitized reads. So
the thing you can verify is also the thing that was always safe to share.

## Why this is only possible on the right substrate

You can't bolt this onto a session-replay tool. Verifiable evidence needs three properties most
tools don't have:

1. **Determinism** — the same input must always produce the same artifact, or the hash and signature
   are meaningless. StepStitch's compiler is a pure function: same trace → same test, byte for byte.
2. **A provable privacy boundary** — the bundle has to be safe to share *and* prove what it
   excluded. The server-side scrubber is the trust boundary, with a redaction-proof test suite.
3. **Signing infrastructure** — provenance, SBOM, SRI, and per-artifact signatures, already part of
   how StepStitch ships.

Hold all three and you can do something new: make troubleshooting evidence **a standard, not a
screenshot.**

## The shift

The EU AI Act becomes enforceable in August 2026; DORA is live now. The 2026 pattern that regulated
teams keep landing on is the same one: **least-privilege access for automated systems, human review
of consequential actions, and data that stays under your control.** "Trust the vendor's recording"
runs in exactly the wrong direction.

So here's the bet StepStitch is making: as agents take over more of the debugging loop, the winning
evidence layer won't be the one with the prettiest replay. It'll be the one whose evidence you can
**hold, scope, sign, and hand to a skeptic** — and have them verify it without trusting you at all.

That's the standard. We'd rather help define it than wait for it.

*StepStitch is open-source (Apache-2.0) and self-hostable: `github.com/CyKiller/stepstitch`.*
