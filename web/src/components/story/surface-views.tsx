"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import type { ReactNode } from "react";
import {
  PRIORITY_DRAFTS,
  RUN,
  SCOPES,
  STAGES,
  TABS,
  TEST_LINES,
  packetFor,
  type Scope,
} from "./story-data";

// The six states of the product surface. Each view takes `t`, how far the visitor is through
// its beat (0 to 1, quantised by the parent), and reveals its parts at fixed points so the
// whole page is the same frame for the same scroll position, in either direction.

type ViewProps = { t: number; technical: boolean };

const ease = [0.22, 1, 0.36, 1] as const;

function Reveal({ show, children, className = "" }: { show: boolean; children: ReactNode; className?: string }) {
  return (
    <motion.div
      initial={false}
      animate={{ opacity: show ? 1 : 0, y: show ? 0 : 8 }}
      transition={{ duration: 0.35, ease }}
      className={className}
      aria-hidden={!show}
    >
      {children}
    </motion.div>
  );
}

function Typed({ text, progress }: { text: string; progress: number }) {
  const n = Math.round(text.length * Math.min(Math.max(progress, 0), 1));
  return (
    <span>
      {text.slice(0, n)}
      {n < text.length && n > 0 ? <span className="ml-px inline-block h-[1em] w-px translate-y-[2px] bg-fg align-baseline" /> : null}
    </span>
  );
}

const span = (t: number, a: number, b: number) => Math.min(Math.max((t - a) / (b - a), 0), 1);

/* ---------------- Beat 1: the customer's app ---------------- */

export function AppView({ t, technical }: ViewProps) {
  const pressed = t >= 0.22;
  const failed = t >= 0.36;
  const reporting = t >= 0.5;
  const sent = t >= 0.9;
  return (
    <div className="flex h-full flex-col gap-4 p-5 sm:p-6">
      <div className="flex items-center justify-between">
        <span className="text-[15px] font-semibold text-fg">Transfer money</span>
        <span className="font-mono text-[11px] text-muted">{technical ? RUN.route : "Example bank app"}</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-[12px] text-muted">
          Payee
          <span className="rounded-lg border border-line bg-surface px-3 py-2 text-[14px] text-fg">Saved payee</span>
        </label>
        <label className="flex flex-col gap-1 text-[12px] text-muted">
          Amount
          <span className="rounded-lg border border-line bg-surface px-3 py-2 text-[14px] text-fg">250.00</span>
        </label>
      </div>
      <span
        className={`w-fit rounded-lg px-4 py-2 text-[14px] font-semibold text-white transition-transform duration-200 ${pressed ? "scale-[0.97] bg-emerald-800" : "bg-accent-solid"}`}
      >
        Review transfer
      </span>
      <Reveal show={failed}>
        <div className="flex items-center justify-between rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-[14px] text-bad">
          <span>Something went wrong. Please try again.</span>
          <span className="font-mono text-[11px]">{technical ? `HTTP ${RUN.status}` : "Error"}</span>
        </div>
      </Reveal>
      <Reveal show={reporting}>
        <div className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-4 shadow-[0_8px_24px_-12px_rgba(24,24,27,0.25)]">
          <span className="text-[13px] font-semibold text-fg">Report a problem</span>
          <div className="min-h-[3.5rem] rounded-lg border border-line bg-bg px-3 py-2 text-[13px] leading-relaxed text-fg">
            <Typed text={RUN.rawExplanation} progress={span(t, 0.55, 0.85)} />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-muted">Synthetic example. Placeholders only.</span>
            <span className={`rounded-md px-3 py-1 text-[12px] font-semibold ${sent ? "bg-accent-solid text-white" : "border border-line text-muted"}`}>
              {sent ? "Sent" : "Send report"}
            </span>
          </div>
        </div>
      </Reveal>
    </div>
  );
}

/* ---------------- Beat 2: what left the browser ---------------- */

const ON_SCREEN = [
  { k: "Amount", v: "250.00" },
  { k: "Account", v: "000000" },
  { k: "Email", v: "user@example.test" },
  { k: "Page text", v: "Transfer money" },
];

export function LeftView({ t, technical }: ViewProps) {
  const rows = RUN.timeline;
  const shown = Math.floor(span(t, 0.12, 0.5) * rows.length + 0.0001);
  const struck = t >= 0.25;
  const scrubbed = t >= 0.58;
  const counted = t >= 0.72;
  return (
    <div className="grid h-full gap-4 p-5 sm:grid-cols-[0.8fr_1.2fr] sm:p-6">
      <div className="flex flex-col gap-2">
        <span className="text-[12px] font-semibold uppercase tracking-[0.12em] text-muted">On their screen</span>
        {ON_SCREEN.map((r, i) => (
          <div key={r.k} className="flex items-center justify-between rounded-lg border border-line px-3 py-2 text-[13px]">
            <span className="text-muted">{r.k}</span>
            <span
              className={`font-mono transition-all duration-500 ${struck ? "text-muted line-through decoration-bad/70" : "text-fg"}`}
              style={{ transitionDelay: `${i * 90}ms` }}
            >
              {r.v}
            </span>
          </div>
        ))}
        <span className="mt-1 text-[12px] text-muted">Stays in the browser. Never captured.</span>
      </div>
      <div className="flex min-w-0 flex-col gap-2">
        <span className="text-[12px] font-semibold uppercase tracking-[0.12em] text-accent">What left the browser</span>
        <ol className="flex flex-col gap-1">
          {rows.map((r, i) => (
            <motion.li
              key={r.index}
              initial={false}
              animate={{ opacity: i < shown ? 1 : 0.15 }}
              transition={{ duration: 0.25 }}
              className={`flex items-center justify-between gap-3 rounded-md px-2.5 py-1.5 text-[12.5px] ${r.kind === "api_error" ? "bg-bad/10 text-bad" : "bg-bg text-fg"}`}
            >
              <span>{technical ? r.kind : r.label}</span>
              <span className="truncate font-mono text-[11.5px] opacity-80">{r.detail ?? r.selector}</span>
            </motion.li>
          ))}
        </ol>
        <Reveal show={scrubbed}>
          <div className="rounded-lg border border-line bg-surface px-3 py-2 text-[12.5px] leading-relaxed">
            <span className="text-muted">Their message, as stored: </span>
            <span className="font-mono text-fg">{RUN.scrubbedExplanation}</span>
          </div>
        </Reveal>
        <Reveal show={counted}>
          <div className="flex items-center justify-between rounded-lg bg-accent/10 px-3 py-2 text-[13px] text-accent">
            <span className="font-semibold">
              {technical ? `${RUN.scrubbedFields.length} fields scrubbed under ${RUN.policy}` : `${RUN.scrubbedFields.length} private details removed on the server`}
            </span>
          </div>
        </Reveal>
      </div>
    </div>
  );
}

/* ---------------- Console chrome shared by beats 3 to 5 ---------------- */

function Console({ active, children }: { active: string; children: ReactNode }) {
  const nav = ["Overview", "Failures", "Agents", "Governance"];
  return (
    <div className="grid h-full sm:grid-cols-[7.5rem_1fr]">
      <aside className="hidden flex-col gap-1 border-r border-line bg-bg p-3 text-[12.5px] sm:flex">
        <span className="mb-2 font-mono text-[11px] text-muted">StepStitch</span>
        {nav.map((n) => (
          <span key={n} className={`rounded-md px-2 py-1 ${n === active ? "bg-accent/10 font-semibold text-accent" : "text-muted"}`}>
            {n}
          </span>
        ))}
      </aside>
      <div className="min-w-0 p-4 sm:p-5">{children}</div>
    </div>
  );
}

function Tabs({ active, technical }: { active: keyof typeof TABS; technical: boolean }) {
  return (
    <div className="flex flex-wrap gap-1">
      {(Object.keys(TABS) as (keyof typeof TABS)[]).map((k) => (
        <span
          key={k}
          className={`rounded-md px-2 py-1 text-[11.5px] ${k === active ? "bg-accent/10 font-semibold text-accent" : "text-muted"}`}
        >
          {technical ? TABS[k].label : TABS[k].plain}
        </span>
      ))}
    </div>
  );
}

/* ---------------- Beat 3: the board ---------------- */

function plainPriority(tool: string, value: string): string {
  if (tool === "Slack") return value.includes("red") ? "red alert" : "alert";
  if (tool === "Linear" && value === "1") return "urgent";
  if (tool === "ServiceNow") return "default urgency";
  return value.toLowerCase();
}

export function BoardView({ t, technical }: ViewProps) {
  const landed = t >= 0.15;
  const graded = t >= 0.32;
  const drafts = t >= 0.5;
  const shownDrafts = Math.floor(span(t, 0.52, 0.8) * PRIORITY_DRAFTS.length + 0.0001);
  return (
    <Console active="Failures">
      <div className="flex h-full flex-col gap-3">
        <div className="flex flex-wrap gap-1.5">
          {STAGES.map((s) => (
            <span
              key={s.id}
              className={`rounded-full border px-2.5 py-0.5 text-[11.5px] ${s.id === "untriaged" && landed ? "border-accent bg-accent/10 font-semibold text-accent" : "border-line text-muted"}`}
            >
              {technical ? s.label : s.plain} · {s.id === "untriaged" && landed ? 1 : 0}
            </span>
          ))}
        </div>
        <motion.div
          initial={false}
          animate={{ opacity: landed ? 1 : 0, x: landed ? 0 : -24 }}
          transition={{ duration: 0.45, ease }}
          className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface p-3 shadow-[0_8px_24px_-14px_rgba(24,24,27,0.3)]"
        >
          <div className="flex min-w-0 flex-col">
            <span className="truncate text-[13.5px] font-semibold text-fg">
              {technical ? RUN.drafts.linear.title : "A transfer fails with a server error"}
            </span>
            <span className="truncate font-mono text-[11px] text-muted">{RUN.route}</span>
          </div>
          <motion.span
            initial={false}
            animate={{ opacity: graded ? 1 : 0, scale: graded ? 1 : 0.8 }}
            className="shrink-0 rounded-full bg-accent-solid px-2.5 py-0.5 text-[12px] font-semibold text-white"
          >
            {technical ? `${RUN.score} · ${RUN.grade}` : `Grade ${RUN.grade}`}
          </motion.span>
        </motion.div>
        <Reveal show={graded && technical}>
          <span className="font-mono text-[11px] text-muted">warning: {RUN.warning}</span>
        </Reveal>
        <Reveal show={drafts} className="flex flex-col gap-1.5">
          <span className="text-[12px] font-semibold uppercase tracking-[0.12em] text-muted">
            {technical ? TABS.drafts.label : TABS.drafts.plain}
          </span>
          {PRIORITY_DRAFTS.map((d, i) => (
            <motion.div
              key={d.tool}
              initial={false}
              animate={{ opacity: i < shownDrafts ? 1 : 0.15 }}
              className="flex items-center justify-between rounded-md bg-bg px-2.5 py-1.5 text-[12.5px]"
            >
              <span className="text-fg">{d.tool}</span>
              <span className="font-mono text-[11.5px] text-muted">
                {technical ? `${d.field}: ${d.value}` : plainPriority(d.tool, d.value)}
              </span>
            </motion.div>
          ))}
          <span className="text-[11.5px] text-muted">{technical ? `Drafts carry the priority each tool supports. Delivery: ${RUN.delivery}.` : "Each draft carries the priority its tool supports. Nothing is sent until you choose."}</span>
        </Reveal>
      </div>
    </Console>
  );
}

/* ---------------- Beat 4: what an AI sees (the signature move) ---------------- */

export function AiView({
  t,
  technical,
  scope,
  setScope,
  interactive,
}: ViewProps & { scope: Scope; setScope: (s: Scope) => void; interactive: boolean }) {
  const packet = packetFor(scope);
  const showCols = t >= 0.12;
  const showKey = t >= 0.6;
  return (
    <Console active="Failures">
      <div className="flex h-full flex-col gap-3">
        <Tabs active="agent" technical={technical} />
        <fieldset className="flex flex-col gap-1.5">
          <legend className="mb-1 text-[12px] font-semibold text-fg">What your AI assistant may receive</legend>
          <div className="flex flex-wrap gap-1.5">
            {SCOPES.map((s) => (
              <label key={s} className="relative">
                <input
                  type="radio"
                  name="story-scope"
                  value={s}
                  checked={scope === s}
                  onChange={() => setScope(s)}
                  disabled={!interactive}
                  className="peer absolute inset-0 cursor-pointer opacity-0"
                />
                <span className="inline-flex min-h-8 cursor-pointer items-center rounded-full border border-line px-3 text-[12.5px] text-fg peer-checked:border-accent-solid peer-checked:bg-accent-solid peer-checked:font-semibold peer-checked:text-white peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent">
                  {s[0]!.toUpperCase() + s.slice(1)}
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <Reveal show={showCols} className="grid min-h-0 flex-1 gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1 rounded-xl border border-accent/40 bg-accent/5 p-3">
            <span className="text-[11.5px] font-semibold uppercase tracking-[0.12em] text-accent">Your AI gets</span>
            <AnimatePresence initial={false} mode="popLayout">
              {packet.length === 0 ? (
                <motion.span key="none" layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="text-[12.5px] italic text-muted">
                  Nothing. The assistant isn&rsquo;t connected.
                </motion.span>
              ) : (
                packet.map((p) => (
                  <motion.div
                    key={p.key}
                    layout
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -8 }}
                    transition={{ duration: 0.25 }}
                    className="flex flex-col rounded-md bg-surface px-2 py-1 text-[12px]"
                  >
                    <span className="font-mono text-[11px] text-accent">{p.key}</span>
                    {technical ? <span className="truncate font-mono text-[11px] text-muted">{p.value}</span> : null}
                  </motion.div>
                ))
              )}
            </AnimatePresence>
          </div>
          <div className="flex flex-col gap-1 rounded-xl border border-line bg-bg p-3">
            <span className="text-[11.5px] font-semibold uppercase tracking-[0.12em] text-muted">Never from the customer</span>
            {RUN.neverCaptured.map((n) => (
              <span key={n} className="flex items-center gap-1.5 text-[12px] text-muted">
                <svg aria-hidden="true" viewBox="0 0 16 16" className="size-3 shrink-0 fill-current"><path d="M5 7V5a3 3 0 1 1 6 0v2h1v7H4V7h1Zm1.5 0h3V5a1.5 1.5 0 0 0-3 0v2Z" /></svg>
                {n}
              </span>
            ))}
          </div>
        </Reveal>
        <Reveal show={showKey}>
          <span className="flex items-center gap-2 rounded-md border border-dashed border-line px-2.5 py-1.5 text-[12px] text-muted">
            <svg aria-hidden="true" viewBox="0 0 16 16" className="size-3 shrink-0 fill-current"><path d="M5 7V5a3 3 0 1 1 6 0v2h1v7H4V7h1Zm1.5 0h3V5a1.5 1.5 0 0 0-3 0v2Z" /></svg>
            {technical ? "verify scope: CI only. Records a verdict, cannot read or propose." : "The key that checks a fix belongs to your CI, not to the AI."}
          </span>
        </Reveal>
      </div>
    </Console>
  );
}

/* ---------------- Beat 5: proof (the peak) ---------------- */

function RunRow({ label, state, technical, verdict }: { label: string; state: "idle" | "running" | "fail" | "pass"; technical: boolean; verdict: string }) {
  const tone =
    state === "fail" ? "border-bad/40 bg-bad/10 text-bad" : state === "pass" ? "border-accent/50 bg-accent/10 text-accent" : "border-line bg-bg text-muted";
  const text =
    state === "idle" ? "Waiting" : state === "running" ? "Running the test" : state === "fail" ? (technical ? `failed · ${verdict}` : "Fails. The bug is real.") : technical ? `passed · ${verdict}` : "Passes. The bug is gone.";
  return (
    <div className={`flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-lg border px-3 py-2 text-[13px] transition-colors duration-300 ${tone}`}>
      <span className="font-semibold">{label}</span>
      <span className="flex items-center gap-2 font-mono text-[12px]">
        {state === "running" ? <span className="size-2 animate-pulse rounded-full bg-current" /> : null}
        {text}
      </span>
    </div>
  );
}

export function ProofView({ t, technical }: ViewProps) {
  const v = RUN.verification;
  const run1 = t < 0.18 ? "idle" : t < 0.3 ? "running" : "fail";
  const run2 = t < 0.44 ? "idle" : t < 0.56 ? "running" : "pass";
  const sealed = t >= 0.66;
  const pr = t >= 0.78;
  const fixedStage = t >= 0.88;
  return (
    <Console active="Failures">
      <div className="flex h-full flex-col gap-3">
        <Tabs active="verify" technical={technical} />
        <span className="text-[11.5px] font-semibold uppercase tracking-[0.12em] text-muted">
          {technical ? "Generated Playwright test" : "The test StepStitch wrote from their steps"}
        </span>
        <div className="rounded-lg border border-line bg-bg p-2.5 font-mono text-[11px] leading-relaxed text-muted">
          {TEST_LINES.map((l, i) => (
            <div key={i} className="truncate">{l}</div>
          ))}
        </div>
        <RunRow label="On the old code" state={run1} technical={technical} verdict={v.measurement.red_verdict} />
        <RunRow label="With the fix" state={run2} technical={technical} verdict={v.measurement.green_verdict} />
        <motion.div
          initial={false}
          animate={{ opacity: sealed ? 1 : 0, scale: sealed ? 1 : 0.96 }}
          transition={{ duration: 0.4, ease }}
          className="flex items-center justify-between rounded-xl bg-accent-solid px-4 py-3 text-white"
        >
          <span className="flex items-center gap-2 text-[15px] font-semibold">
            <svg aria-hidden="true" viewBox="0 0 16 16" className="size-4 fill-current"><path d="M6.5 11.2 3.3 8l1-1 2.2 2.2 5.2-5.2 1 1z" /></svg>
            {technical ? v.verdict : "Fixed and proven"}
          </span>
          <span className="font-mono text-[12px] opacity-90">evidence: {v.measurement.evidence_grade}</span>
        </motion.div>
        <Reveal show={pr}>
          <span className="text-[12.5px] text-muted">
            {technical ? `Regression PR drafted (${v.fix_ref}). StepStitch never merges.` : "The test is drafted as a pull request. A person reviews and merges it."}
          </span>
        </Reveal>
        <Reveal show={fixedStage}>
          <span className="w-fit rounded-full border border-accent bg-accent/10 px-2.5 py-0.5 text-[11.5px] font-semibold text-accent">
            {technical ? "Fixed · 1" : "Fixed and proven · 1"}
          </span>
        </Reveal>
      </div>
    </Console>
  );
}

/* ---------------- Beat 6: start (the close is a real input) ---------------- */

export function StartView({ t, interactive }: ViewProps & { interactive: boolean }) {
  const cmd = "npx stepstitch start --connect claude";
  const typed = span(t, 0.1, 0.45);
  const links = t >= 0.55;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(cmd);
    } catch {
      /* clipboard refused: the command stays selectable */
    }
  };
  return (
    <div className="flex h-full flex-col justify-center gap-5 p-6">
      <span className="text-[13px] text-muted">Your terminal</span>
      <div className="flex items-center gap-3 rounded-xl border border-fg/80 bg-surface px-4 py-3 font-mono text-[15px] text-fg">
        <span className="text-accent">$</span>
        <span className="min-w-0 flex-1 select-all break-all">
          {interactive ? <Typed text={cmd} progress={typed} /> : cmd}
        </span>
        <button
          type="button"
          onClick={copy}
          disabled={!interactive}
          className="shrink-0 rounded-md border border-line px-2.5 py-1 font-sans text-[12px] text-muted hover:border-fg/40 hover:text-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        >
          Copy
        </button>
      </div>
      <ul className="flex flex-col gap-1.5 text-[13.5px] text-muted">
        <li>Opens the StepStitch console on your own machine, at 127.0.0.1</li>
        <li>Connects your AI assistant over MCP, with a scoped key</li>
        <li>Free and open source, Apache-2.0</li>
      </ul>
      <Reveal show={links}>
        <div className="flex flex-wrap items-center gap-3 text-[14px]">
          <Link href="/quickstart" className="rounded-full bg-accent-solid px-4 py-2 font-semibold text-white hover:opacity-90">
            Read the quickstart
          </Link>
          <Link href="/#contact" className="rounded-full border border-line px-4 py-2 text-fg hover:border-fg/40">
            Plan a pilot
          </Link>
          <Link href="/self-host" className="px-1 py-2 text-accent underline underline-offset-2">
            Self-host it
          </Link>
        </div>
      </Reveal>
    </div>
  );
}
