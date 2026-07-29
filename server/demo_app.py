"""Standalone entrypoint for the public demo console.

    uvicorn server.demo_app:app --port 8020

Needs no DATABASE_URL, no tokens and no environment at all — the dataset is a committed
JSON file and the store is in memory. That is what makes it runnable in CI (the browser
smoke test boots exactly this) and what makes it safe to expose publicly.

A deployment that already runs the real host does not need this: set
``STEPSTITCH_DEMO_MODE=1`` and the same demo application is mounted at ``/demo``.
"""
from __future__ import annotations

from .demo import build_demo_app

app = build_demo_app()
