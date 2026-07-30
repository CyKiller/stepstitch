"""Compatibility shim: moved to stepstitch_service.host.auth in Phase 1.

The host now ships inside the PyPI package so `stepstitch start` works from a clean
install; server/ keeps the repo-deployment pieces plus these re-exports so every
existing ``server.auth`` import — tests, entrypoints, docs — keeps resolving.
"""
from stepstitch_service.host.auth import *  # noqa: F401,F403
from stepstitch_service.host.auth import _bearer  # noqa: F401  (host-internal seam)
