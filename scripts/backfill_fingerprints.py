#!/usr/bin/env python3
"""Backfill ``stepstitch_traces.fingerprint`` for traces ingested before migration 0005.

Migration 0005 added the column and the ingest path started populating it, but existing rows
kept ``NULL``. A trace without a fingerprint never clusters into a failure shape, so those
traces are invisible on the console's board — silently. This closes that gap (recorded as a
known gap in docs/STATUS.md).

The fingerprint is derived with the SAME function the ingest path uses
(``fix_memory.fingerprint`` over ``build_trace_summary``), so a backfilled row is
indistinguishable from a freshly ingested one. It is structural and NPI-free: templated route,
diagnostic type, failing status, exception type, endpoint, terminal selector.

Usage:
    DATABASE_URL=postgres://… python3 scripts/backfill_fingerprints.py [--dry-run] [--batch N]

Idempotent: only rows with a NULL fingerprint are touched, so re-running is a no-op. Traces
whose bodies were already purged by retention have no footsteps to derive from and are
reported as skipped rather than guessed at.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "service"))

from stepstitch_service.fix_memory import fingerprint as fix_fingerprint  # noqa: E402
from stepstitch_service.integrations.base import build_trace_summary  # noqa: E402


def _loads(value):
    return json.loads(value) if isinstance(value, (str, bytes)) else value


async def backfill(conn, *, batch: int, dry_run: bool) -> dict:
    rows = await conn.fetch(
        "SELECT id, project_id, footsteps FROM stepstitch_traces "
        "WHERE fingerprint IS NULL ORDER BY created_at LIMIT $1",
        batch,
    )
    scanned = updated = skipped = 0
    for row in rows:
        scanned += 1
        footsteps = _loads(row["footsteps"])
        if not footsteps:
            # Body purged by retention (or never had one) — nothing structural to derive.
            skipped += 1
            continue
        summary = build_trace_summary(row["id"], footsteps, project_id=row["project_id"])
        fp = json.dumps(fix_fingerprint(summary.as_dict(), footsteps))
        if not dry_run:
            await conn.execute(
                "UPDATE stepstitch_traces SET fingerprint = $1 WHERE id = $2", fp, row["id"])
        updated += 1
    return {"scanned": scanned, "updated": updated, "skipped": skipped}


async def main_async(args) -> int:
    import asyncpg

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set (the Postgres DSN of the StepStitch host).",
              file=sys.stderr)
        return 2

    conn = await asyncpg.connect(dsn=dsn)
    try:
        remaining = await conn.fetchval(
            "SELECT count(*) FROM stepstitch_traces WHERE fingerprint IS NULL")
        print(f"traces without a fingerprint: {remaining}")
        if not remaining:
            print("nothing to backfill.")
            return 0
        totals = {"scanned": 0, "updated": 0, "skipped": 0}
        while True:
            result = await backfill(conn, batch=args.batch, dry_run=args.dry_run)
            for key in totals:
                totals[key] += result[key]
            # A dry run never clears rows, so one pass is all it can report on.
            if result["scanned"] == 0 or args.dry_run or result["updated"] == 0:
                break
        verb = "would update" if args.dry_run else "updated"
        print(f"scanned={totals['scanned']} {verb}={totals['updated']} "
              f"skipped={totals['skipped']} (skipped = body already purged)")
        return 0
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing")
    parser.add_argument("--batch", type=int, default=500,
                        help="rows per pass (default 500)")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
