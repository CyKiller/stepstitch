"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  Lock,
  Warning,
  ShieldCheck,
  Gauge,
  Code,
  GitPullRequest,
  CheckCircle,
  CursorClick,
} from "@phosphor-icons/react";

type Step = { key: string; label: string; caption: string };

const steps: Step[] = [
  { key: "report", label: "Bug", caption: "A user hits a 500 on a transfer." },
  { key: "scrub", label: "Report", caption: "One tap. Scrubbed, structural trace." },
  { key: "score", label: "Score", caption: "Replayability decides if it reproduces." },
  { key: "repro", label: "Reproduce", caption: "A Playwright test, compiled." },
  { key: "ship", label: "Ship", caption: "A reviewed PR. Red turns green." },
];

const AUTO_MS = 4200;

export function WorkflowShowcase() {
  const reduce = useReducedMotion();
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (reduce || paused) return;
    const t = setTimeout(() => setActive((a) => (a + 1) % steps.length), AUTO_MS);
    return () => clearTimeout(t);
  }, [active, paused, reduce]);

  return (
    <div
      className="mt-12"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      {/* Step rail */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {steps.map((s, i) => {
          const isActive = i === active;
          return (
            <button
              key={s.key}
              onClick={() => setActive(i)}
              className={`group relative overflow-hidden rounded-xl border px-4 py-3 text-left transition-colors duration-300 ease-[var(--ease-spring)] ${
                isActive
                  ? "border-accent/40 bg-surface"
                  : "border-line bg-surface/50 hover:border-fg/20"
              }`}
            >
              <span
                className={`font-mono text-[11px] ${isActive ? "text-accent" : "text-muted"}`}
              >
                0{i + 1}
              </span>
              <span className="mt-0.5 block text-sm font-semibold text-fg">
                {s.label}
              </span>
              {isActive && !reduce && !paused && (
                <motion.span
                  key={active}
                  className="absolute bottom-0 left-0 h-0.5 bg-accent-solid"
                  initial={{ width: "0%" }}
                  animate={{ width: "100%" }}
                  transition={{ duration: AUTO_MS / 1000, ease: "linear" }}
                />
              )}
            </button>
          );
        })}
      </div>

      <p className="mt-4 text-sm text-muted">{steps[active].caption}</p>

      {/* Dual panes */}
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <Pane
          label="What your user sees"
          tone="user"
          step={active}
          reduce={!!reduce}
        />
        <Pane
          label="What the developer sees"
          tone="dev"
          step={active}
          reduce={!!reduce}
        />
      </div>
    </div>
  );
}

function Pane({
  label,
  tone,
  step,
  reduce,
}: {
  label: string;
  tone: "user" | "dev";
  step: number;
  reduce: boolean;
}) {
  return (
    <div className="bezel-outer border border-line/60">
      <div className="bezel-inner h-full overflow-hidden border border-line bg-surface">
        <div className="flex items-center justify-between border-b border-line bg-surface-2/50 px-4 py-2.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">
            {label}
          </span>
          <span
            className={`size-2 rounded-full ${tone === "dev" ? "bg-accent-solid" : "bg-muted/50"}`}
          />
        </div>
        <div className="min-h-[260px] p-5">
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={reduce ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduce ? undefined : { opacity: 0, y: -10 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              {tone === "user" ? userPane(step) : devPane(step)}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

/* ---- USER side: an intentionally abstract phone/app frame. The masked bars
   are the point: this content never leaves the user's device. ---- */
function MaskedRow({ w = "w-32" }: { w?: string }) {
  return (
    <div className="flex items-center gap-2">
      <Lock size={12} weight="bold" className="text-muted/60" />
      <span className={`h-2.5 rounded bg-muted/25 ${w}`} />
    </div>
  );
}

function userPane(step: number) {
  if (step === 0) {
    return (
      <div className="space-y-4">
        <p className="text-sm font-medium text-fg">Transfer · review</p>
        <div className="space-y-3 rounded-xl border border-line bg-surface-2/40 p-4">
          <MaskedRow w="w-40" />
          <MaskedRow w="w-24" />
          <MaskedRow w="w-36" />
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">
          <Warning size={15} weight="bold" /> Something went wrong (500)
        </div>
        <button className="inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 px-3.5 py-1.5 text-xs font-semibold text-accent">
          <CursorClick size={13} weight="bold" /> Report a problem
        </button>
      </div>
    );
  }
  if (step === 1) {
    return (
      <div className="flex h-full flex-col justify-center gap-3 text-center">
        <ShieldCheck size={30} weight="fill" className="mx-auto text-ok" />
        <p className="text-base font-semibold text-fg">Report sent</p>
        <p className="mx-auto max-w-[34ch] text-sm text-muted">
          No screenshot. No input values. Nothing sensitive left your device.
        </p>
      </div>
    );
  }
  if (step === 4) {
    return (
      <div className="flex h-full flex-col justify-center gap-3 text-center">
        <CheckCircle size={30} weight="fill" className="mx-auto text-ok" />
        <p className="text-base font-semibold text-fg">Transfer complete</p>
        <p className="text-sm text-muted">The bug they hit is now a test.</p>
      </div>
    );
  }
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
      <div className="space-y-2 opacity-50">
        <MaskedRow w="w-40" />
        <MaskedRow w="w-28" />
        <MaskedRow w="w-36" />
      </div>
      <p className="mt-3 text-xs text-muted">The user moved on. Nothing to do.</p>
    </div>
  );
}

/* ---- DEVELOPER side: real structural evidence, no PII. ---- */
function devPane(step: number) {
  if (step === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
        <span className="grid size-10 place-items-center rounded-xl border border-line bg-surface-2 text-muted">
          <Code size={18} weight="bold" />
        </span>
        <p className="text-sm text-muted">Awaiting a report. Capture is off until consent.</p>
      </div>
    );
  }
  if (step === 1) {
    const rows = [
      "nav  /accounts/:id",
      "nav  /accounts/:id/transfer",
      "click [data-testid=review-transfer]",
      "api_error  POST /api/accounts/:id/transfers  500",
    ];
    return (
      <div className="space-y-3">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-ok/12 px-2.5 py-1 text-xs font-semibold text-ok">
          <ShieldCheck size={13} weight="bold" /> scrubbed · structure only
        </span>
        <div className="space-y-1.5 rounded-xl border border-line bg-surface-2/40 p-3 font-mono text-[12px] text-muted">
          {rows.map((r) => (
            <div key={r} className="truncate">
              {r}
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (step === 2) {
    return (
      <div className="flex items-center gap-5">
        <span className="grid size-20 place-items-center rounded-2xl border border-accent/30 bg-accent/5 text-3xl font-semibold text-accent">
          B
        </span>
        <div>
          <p className="font-mono text-2xl font-semibold tabular-nums text-fg">0.76</p>
          <p className="text-sm text-muted">replayability score</p>
          <p className="mt-1 inline-flex items-center gap-1.5 text-xs text-muted">
            <Gauge size={13} weight="bold" className="text-accent" /> reproducible
          </p>
        </div>
      </div>
    );
  }
  if (step === 3) {
    return (
      <pre className="overflow-hidden rounded-xl border border-line bg-surface-2/40 p-3 font-mono text-[11.5px] leading-relaxed text-fg/90">
        <code>{`test('repro: transfer 500', async ({ page }) => {
  await page.goto('/accounts/:id/transfer');
  const failing = page.waitForResponse(
    r => r.url().includes('/transfers') && r.status() === 500);
  await page.getByTestId('review-transfer').click();
  expect((await failing).status()).toBeLessThan(500);
});`}</code>
      </pre>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 rounded-lg border border-line bg-surface-2/40 px-3 py-2.5 text-sm">
        <GitPullRequest size={16} weight="bold" className="text-accent" />
        <span className="font-medium text-fg">PR #214</span>
        <span className="text-muted">fix: guard transfer review</span>
      </div>
      <div className="inline-flex items-center gap-2.5 rounded-lg border border-line bg-surface-2/40 px-3 py-2 font-mono text-[12px]">
        <span className="text-bad">pre: fail</span>
        <span className="text-muted">→</span>
        <span className="text-ok">post: pass</span>
        <span className="text-muted">=</span>
        <span className="text-fg">confirmed_fixed</span>
      </div>
    </div>
  );
}
