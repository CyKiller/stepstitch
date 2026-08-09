"""Optional tenant-controlled evidence signer (cosign).

If the deployer sets ``STEPSTITCH_SIGNING_KEY``, Evidence Attestation bundles are signed with
THAT key via the ``cosign`` CLI (out-of-process). The service core never holds a key — signing
lives here in the host, bound to the tenant's own key. If cosign is unavailable or signing fails,
the attestation is returned unsigned; the tamper-evident hash always holds regardless.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Awaitable, Callable, Optional

# The Ed25519 path lives in the packaged host (so `stepstitch start` signs too); these
# re-exports keep `server.signing` the one import site for every signer flavor.
from stepstitch_service.host.signing import (  # noqa: F401
    load_signing_seed,
    make_ed25519_signer,
)

logger = logging.getLogger("stepstitch.signing")


def make_cosign_signer(key_ref: str) -> Callable[[bytes], Awaitable[Optional[str]]]:
    """Return an async ``sign(blob) -> signature|None`` bound to the tenant's cosign key."""

    async def sign(blob: bytes) -> Optional[str]:
        def _run() -> Optional[str]:
            try:
                proc = subprocess.run(
                    ["cosign", "sign-blob", "--yes", "--key", key_ref, "-"],
                    input=blob, capture_output=True, timeout=30,
                )
            except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
                logger.warning("cosign signing unavailable: %s", exc)
                return None
            if proc.returncode != 0:
                logger.warning("cosign sign-blob failed: %s",
                               proc.stderr.decode(errors="replace")[:200])
                return None
            return proc.stdout.decode(errors="replace").strip() or None

        return await asyncio.get_running_loop().run_in_executor(None, _run)

    return sign
