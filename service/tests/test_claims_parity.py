"""The README's verification claim must match the table it cites.

`docs/agent-platforms.md` is the living record — one row per platform, dates and failures
included — and the README points at it while summarising the headline number. That pair
drifted once: a commit upgraded the table from one verified platform to three and touched
nothing else, so the README sat understating the product's strongest evidence. The commit
that caused it had, in its own message, criticised exactly this class of quietly-stale
claim. Nothing guards a claim like a test that reads both files.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
          6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def _verified_platform_count() -> int:
    """Rows in the Verified table whose 'Fixed a real bug' column is a bold yes."""
    text = (REPO / "docs" / "agent-platforms.md").read_text(encoding="utf-8")
    table = text.split("## Verified", 1)[1].split("##", 1)[0]
    rows = [line for line in table.splitlines()
            if line.startswith("|") and "---" not in line]
    header, bodies = rows[0], rows[1:]
    columns = [c.strip().lower() for c in header.strip("|").split("|")]
    fixed_idx = next(i for i, c in enumerate(columns) if "fixed a real bug" in c)
    count = 0
    for row in bodies:
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) > fixed_idx and cells[fixed_idx].lower().startswith("**yes"):
            count += 1
    return count


def test_the_readme_headline_matches_the_living_table():
    count = _verified_platform_count()
    assert count >= 1, "the table itself must parse — a zero here means the format moved"

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    claim = re.search(
        r"As of \d{4}-\d{2}-\d{2},? (\w+) platforms? (?:has|have) been verified",
        readme)
    assert claim, "the README must state how many platforms were verified end-to-end"
    stated = claim.group(1).lower()
    expected = _WORDS.get(count, str(count))
    assert stated == expected, (
        f"README claims {stated!r} verified platform(s); docs/agent-platforms.md records "
        f"{count}. Update the README sentence — the table is the source of truth."
    )
