"""Filesystem paths in free text never survive ingest.

A user describing a bug often pastes where a file lives — ``C:\\Users\\<name>\\...`` or
``/Users/<name>/...`` — and the home folder carries their name. The ``path`` kind
redacts the whole path, leaf included, under every profile. Ordinary prose with slashes
and web routes stay readable; the accepted false positives are pinned here so nobody
"fixes" them into a leak.
"""
import pytest

from stepstitch_service.profiles import available_profiles, load_profile
from stepstitch_service.scrubber import (
    built_in_detector_kinds,
    redact_text,
    route_template,
    scrub_trace_payload,
)

P = "[redacted:path]"


@pytest.mark.parametrize("text,expected", [
    ("it failed on C:\\Users\\dana\\AppData\\Local\\Temp\\x.tmp today", f"it failed on {P} today"),
    ("c:/Users/dana/Desktop/notes.txt", P),
    ("\\\\fileserver\\share\\team\\plan.docx", P),
    ("\\\\?\\C:\\Users\\dana\\big.iso", P),
    ("%USERPROFILE%\\Documents\\tax.pdf", P),
    ("/Users/dana/Library/Caches/x", P),
    ("/home/dana/.cache/pip", P),
    ("~/Downloads/report.pdf", P),
    ("/Volumes/Backup/2026", P),
    ("/var/folders/ab/cd/T/x", P),
    ("/tmp/upload-7/x.bin", P),
    ('"C:\\Program Files\\Acme App\\acme.exe" crashed', f"{P} crashed"),
    ("'/Users/Zoë Ångström/Notes/x.txt' is gone", f"{P} is gone"),
    ("C:\\Users\\Zoë\\x", P),
    ("see C:\\Users\\dana\\a.txt.", f"see {P}."),
    ("(/home/dana/x.log)", f"({P})"),
    ("AppData\\Local\\Acme", P),
    ("C:\\Program Files\\Acme", f"{P} {P}"),          # unquoted space: both halves go
    ("/home/feed broke", f"{P} broke"),                 # accepted false positive: a route with a following segment
    ("one\\nline", P),                                  # accepted: escaped text reads as a relative path
])
def test_paths_are_redacted_whole(text, expected):
    out, kinds = redact_text(text)
    assert out == expected
    assert "path" in kinds


def test_a_path_with_a_high_entropy_segment_leaves_no_fragment():
    out, _ = redact_text("C:\\Users\\dana\\Temp\\3f9a8c7d6e5b4a39281706f5e4d3c2b1\\x.dmp ok")
    assert out.endswith(" ok") and "Users" not in out and "Temp" not in out and "x.dmp" not in out


@pytest.mark.parametrize("text", [
    "3/4 of the scans", "and/or", "the /accounts/:id page", "/api/users/:id returned 500",
    "the /home page", "a\\b", "build 26100 on 1.2.3",
])
def test_prose_with_slashes_is_left_alone(text):
    out, kinds = redact_text(text)
    assert out == text and "path" not in kinds


@pytest.mark.parametrize("route", ["/accounts/:id", "/srv/app/src/pay.ts", "/home", "/home/feed", "/api/users/:id"])
def test_route_templates_are_unchanged(route):
    assert route_template(route) == route


@pytest.mark.parametrize("seg", ["accounts", "home", "users", "feed", "Users", "tmp", "~", "C:", "pay.ts"])
def test_single_route_segments_are_not_ids(seg):
    from stepstitch_service.scrubber import _is_id_like_segment
    assert _is_id_like_segment(seg) is False


def test_a_backslash_segment_is_an_id():
    from stepstitch_service.scrubber import _is_id_like_segment
    assert _is_id_like_segment("src\\pay.ts") is True


def test_path_is_a_built_in_kind():
    assert "path" in built_in_detector_kinds()


@pytest.mark.parametrize("name", available_profiles())
def test_every_profile_redacts_a_pasted_path(name):
    payload = {"explanation": "it broke in C:\\Users\\dana\\x", "metadata": {},
               "footsteps": [{"timestamp": "2026-07-30T12:00:00Z", "type": "click",
                              "route": "/transfer", "target": "#send", "label": "[masked]"}]}
    policy = load_profile(name)
    if policy.free_text == "disabled":
        pytest.skip("this profile drops explanation whole, which is stricter")
    scrubbed, report = scrub_trace_payload(payload, policy)
    assert "dana" not in scrubbed["explanation"] and P in scrubbed["explanation"]
    assert report["kinds"].get("path") == 1
