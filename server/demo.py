"""Compatibility shim: moved to stepstitch_service.host.demo in Phase 1.

The host now ships inside the PyPI package so `stepstitch start` works from a clean
install; server/ keeps the repo-deployment pieces plus these re-exports so every
existing ``server.demo`` import — tests, entrypoints, docs — keeps resolving.
"""
from stepstitch_service.host.demo import *  # noqa: F401,F403
from stepstitch_service.host.demo import _ReadOnlyStore  # noqa: F401  (test seam)
