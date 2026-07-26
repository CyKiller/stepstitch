"""The Overview's charts are hand-generated SVG — no chart library can run under the
console's ``default-src 'none'`` CSP, so the geometry is ours to get right and ours to test.

Catmull-Rom derives a point's tangent from its NEIGHBOURS, which means a spiky series
(0 -> peak -> 0 — the normal shape for "new failures per day") produces control points well
outside the plot band. Before the clamp this measured y=173.9 against a 170-tall box on the
real seeded corpus, and -21.3/197.3 on a sparser one: the area fill spilled under the
baseline and the stroke clipped at the top. Nothing failed; it just looked broken.

These tests pull ``smoothPath`` out of the page the host actually serves, so they cannot
drift from the shipped implementation the way a reimplementation would.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from server.auth import build_auth
from server.host import build_app

# A cubic bezier is contained in the convex hull of its control points, so if every control
# point's y is inside the band, the rendered curve is too. That is a guarantee, not a heuristic.
PAD, HEIGHT, WIDTH = 6, 170, 660

SERIES = {
    "spiky zero-to-max": [0, 3, 0, 0, 4, 0, 0, 2, 0, 5, 0, 0, 1, 0, 6, 0],
    "all zero": [0, 0, 0, 0, 0, 0, 0, 0],
    "single spike": [0, 0, 0, 0, 9, 0, 0, 0, 0],
    "monotonic rise": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    "sawtooth": [0, 9, 0, 9, 0, 9, 0, 9, 0, 9],
    "flat nonzero": [4, 4, 4, 4, 4, 4],
    "two points": [0, 7],
    "one point": [3],
    # A real 30-day corpus: 6 shapes over 87 traces, with a quiet day in the middle.
    "realistic 30 days": [6, 3, 1, 3, 2, 1, 1, 1, 5, 3, 3, 3, 2, 0, 1, 5,
                          6, 3, 4, 5, 5, 3, 5, 1, 2, 2, 1, 2, 1, 7],
}


def _dashboard_html() -> str:
    get_user_id, require_admin = build_auth("admin-secret", "ingest-secret")

    async def _noop(*a, **k):
        return None

    async def _empty(*a, **k):
        return []

    app = build_app(get_user_id=get_user_id, require_admin=require_admin,
                    execute=_noop, fetchone=_noop, fetchall=_empty)
    return TestClient(app).get("/dashboard").text


def _smooth_path_source() -> str:
    m = re.search(r"(function smoothPath\(series, w, h, close\) \{.*?\n  \})",
                  _dashboard_html(), re.S)
    assert m, "smoothPath is no longer in the served console — update this test"
    return m.group(1)


def test_control_points_are_clamped_in_the_served_source():
    """Structural gate, runs everywhere: both control-point y values pass through the clamp.

    Node is not guaranteed on the Python CI job, so this is the check that always runs.
    The behavioural proof below is stronger but conditional.
    """
    src = _smooth_path_source()
    assert "function clampY" in src, "the overshoot clamp is gone"
    # Both the outgoing and incoming control point must be clamped — clamping one still
    # spills at the other end of every peak.
    assert len(re.findall(r"clampY\(", src)) >= 3, "a control point is no longer clamped"


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node to execute the chart JS")
@pytest.mark.parametrize("name", list(SERIES))
def test_curve_never_leaves_the_plot_band(name: str):
    """Behavioural gate: run the SHIPPED function and check every emitted coordinate."""
    harness = _smooth_path_source() + f"""
var series = {json.dumps(SERIES[name])};
var out = [];
[false, true].forEach(function (close) {{
  var d = smoothPath(series, {WIDTH}, {HEIGHT}, close);
  if (/NaN|Infinity|undefined/.test(d)) {{ out.push("non-finite: " + d.slice(0, 80)); return; }}
  var nums = (d.match(/-?\\d+\\.?\\d*/g) || []).map(Number);
  nums.forEach(function (n, i) {{
    if (i % 2 === 1 && (n < {PAD} - 0.01 || n > {HEIGHT} + 0.01)) {{
      out.push((close ? "area" : "line") + " y=" + n);
    }}
  }});
}});
console.log(JSON.stringify(out));
"""
    proc = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    violations = json.loads(proc.stdout.strip())
    assert violations == [], f"{name}: curve left the [{PAD}, {HEIGHT}] band -> {violations}"
