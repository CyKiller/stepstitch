"use client";

import { useEffect, useState } from "react";
import {
  CheckCircle,
  XCircle,
  CircleNotch,
} from "@phosphor-icons/react/dist/ssr";
import { useReducedMotion } from "motion/react";

// The literal product promise, animated: the compiled Playwright repro runs
// RED while the bug is present, then GREEN once the fix lands. It is the real
// reproduction text from SAMPLE_TRACE: not a faux screenshot: cycled through
// its run states. Reduced-motion settles straight on the passing state.

type Phase = "run" | "red" | "green";
const ORDER: Phase[] = ["run", "red", "green"];
const DURATIONS: Record<Phase, number> = { run: 1100, red: 2400, green: 2900 };

export function RedToGreen() {
  const reduce = useReducedMotion();
  const [phase, setPhase] = useState<Phase>("run");

  useEffect(() => {
    if (reduce) return;
    const t = setTimeout(() => {
      setPhase((p) => ORDER[(ORDER.indexOf(p) + 1) % ORDER.length]);
    }, DURATIONS[phase]);
    return () => clearTimeout(t);
  }, [phase, reduce]);

  // Reduced-motion users get the final passing state, no cycling: derived,
  // not stored, so the effect never sets state synchronously.
  const display: Phase = reduce ? "green" : phase;

  const pill =
    display === "green"
      ? { Icon: CheckCircle, label: "1 passing", cls: "text-ok", spin: false }
      : display === "red"
        ? { Icon: XCircle, label: "1 failing", cls: "text-bad", spin: false }
        : {
            Icon: CircleNotch,
            label: "running",
            cls: "text-muted",
            spin: true,
          };

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface font-mono shadow-[var(--shadow-brand)]">
      {/* Title bar */}
      <div className="flex items-center justify-between border-b border-line bg-surface-2/40 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="flex gap-1.5" aria-hidden>
            <span className="size-2.5 rounded-full bg-bad/40" />
            <span className="size-2.5 rounded-full bg-muted/30" />
            <span className="size-2.5 rounded-full bg-ok/40" />
          </span>
          <span className="ml-1 text-[12px] text-muted">
            stepstitch-repro.spec.ts
          </span>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 rounded-md border border-line bg-surface px-2 py-1 text-[11.5px] font-semibold ${pill.cls}`}
        >
          <pill.Icon
            size={13}
            weight="bold"
            className={pill.spin ? "animate-spin" : ""}
          />
          {pill.label}
        </span>
      </div>

      {/* Body: fixed height so the run/red/green states don't shift layout */}
      <div className="min-h-[148px] space-y-2 px-4 py-4 text-[13px] leading-relaxed">
        <p className="text-muted">
          <span className="text-accent">$</span> npx playwright test
          stepstitch-repro.spec.ts
        </p>

        {display === "run" ? (
          <p className="text-muted">Running StepStitch reproduction…</p>
        ) : null}

        {display === "red" ? (
          <>
            <p className="text-bad">
              ✗ POST /api/accounts/:id/transfers: received{" "}
              <span className="font-semibold">500</span>
            </p>
            <p className="text-muted">
              expect(res.status).toBeLessThan(500)
            </p>
            <p className="pt-1 text-[12.5px] text-muted">
              Bug present: the test fails. This is your reproduction.
            </p>
          </>
        ) : null}

        {display === "green" ? (
          <>
            <p className="text-ok">
              ✓ POST /api/accounts/:id/transfers: received{" "}
              <span className="font-semibold">200</span>
            </p>
            <p className="text-muted">1 passed (1.2s)</p>
            <p className="pt-1 text-[12.5px] text-muted">
              Fix shipped: the same test passes, so it stays fixed.
            </p>
          </>
        ) : null}
      </div>
    </div>
  );
}
