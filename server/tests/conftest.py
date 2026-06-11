import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
# `import server` (repo root) and `import stepstitch_service` (service/ package).
for p in (str(_ROOT), str(_ROOT / "service")):
    if p not in sys.path:
        sys.path.insert(0, p)
