"""Compatibility shim: moved to stepstitch_service.host.db in Phase 1.

The host now ships inside the PyPI package so `stepstitch start` works from a clean
install; server/ keeps the repo-deployment pieces plus these re-exports so every
existing ``server.db`` import — tests, entrypoints, docs — keeps resolving.
"""
from stepstitch_service.host.db import *  # noqa: F401,F403
