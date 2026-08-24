"""Guard `railway.json` against the always-on regression that cost real money.

Railway bills allocated memory per minute for as long as a service is awake, whether or
not a request ever arrives. Between 2026-06-12 and 2026-08-24 both services in the
`stepstitch` project ran with `sleepApplication` disabled and never scaled to zero: the
project burned 1,740 GB-hours of memory against 23.5 vCPU-hours of actual compute —
roughly 74x more memory rented than work done, and ~95% of a ~$25/month bill for a
synthetic demo nobody was querying.

The setting was originally flipped in the Railway dashboard, which is exactly why it
could regress: dashboard state is invisible to review and silently overridden by whatever
`railway.json` declares on the next deploy. `deploy.sleepApplication` is a documented
key of railway.schema.json, so declaring it here makes the intent version-controlled,
reviewable, and authoritative over console drift.

These tests fail closed. A missing key is a failure, not a default — the whole incident
was an absent setting being read as "leave it running".
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAILWAY_JSON = REPO / "railway.json"


def _config() -> dict:
    # Reachability: prove we are reading the real file the platform reads, not a fixture.
    assert RAILWAY_JSON.is_file(), f"{RAILWAY_JSON} is missing; Railway would fall back to console state"
    return json.loads(RAILWAY_JSON.read_text(encoding="utf-8"))


def test_railway_json_parses_and_declares_a_deploy_block():
    cfg = _config()
    assert isinstance(cfg.get("deploy"), dict), "deploy block must exist for sleep to be declarable"


def test_services_scale_to_zero_when_idle():
    """The actual cost guard: idle services must sleep, and it must be declared, not assumed."""
    deploy = _config()["deploy"]
    assert "sleepApplication" in deploy, (
        "railway.json must DECLARE deploy.sleepApplication. Omitting it leaves the value to "
        "Railway console state, which is how the always-on 24/7 billing regression happened."
    )
    assert deploy["sleepApplication"] is True, (
        f"deploy.sleepApplication is {deploy['sleepApplication']!r}; must be True so idle "
        "services scale to zero instead of billing memory around the clock."
    )


def test_no_environment_override_silently_re_enables_always_on():
    """Rot check: a per-environment block can override the top-level deploy config."""
    cfg = _config()
    for name, env in (cfg.get("environments") or {}).items():
        override = (env.get("deploy") or {}).get("sleepApplication", True)
        assert override is True, (
            f"environment {name!r} overrides deploy.sleepApplication to {override!r}, "
            "re-enabling the always-on billing this guard exists to prevent."
        )


def test_replica_count_is_not_scaled_up_unreviewed():
    """A sleeping service still bills per replica while awake; keep the demo at one."""
    replicas = _config()["deploy"].get("numReplicas", 1)
    assert replicas == 1, f"numReplicas={replicas!r}; more than one replica multiplies the memory bill"
