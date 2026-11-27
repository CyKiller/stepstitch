"use client";

import { track } from "@vercel/analytics";
import {
  AnimatePresence,
  motion,
  useMotionValueEvent,
  useScroll,
  useSpring,
  useTransform,
  type MotionValue,
} from "motion/react";
import { useRef, useState, useSyncExternalStore, type CSSProperties } from "react";
import { GITHUB_URL } from "@/lib/links";
import { BEATS, BEAT_STARTS, RUN, TOTAL_VH, locate, type Beat, type Scope } from "./story-data";
import { AiView, AppView, BoardView, LeftView, ProofView, StartView } from "./surface-views";

// "Follow one request": a live-surface scroll story. The page behaves like the product, a
// bright console that fills in as you scroll, following one customer's report from the moment
// it fails to a proven fix. Native scroll only; the "camera" is a CSS tilt and focus zoom on
// the surface. Phones and reduced motion get every beat as a complete still state.

// The story is always high-key, even when the site is dark: override the site's colour
// tokens on the stage so every token-driven utility inside renders light.
const LIGHT: CSSProperties = {
  ["--bg" as string]: "#f7f8f7",
  ["--surface" as string]: "#ffffff",
  ["--surface-2" as string]: "#f1f3f2",
  ["--line" as string]: "#e2e6e4",
  ["--fg" as string]: "#18181b",
  ["--muted" as string]: "#56605b",
  ["--accent" as string]: "#047857",
  ["--accent-solid" as string]: "#047857",
  ["--accent-2" as string]: "#0d9488",
  ["--accent-fg" as string]: "#ffffff",
  ["--bad" as string]: "#b91c1c",
  colorScheme: "light",
};

/* ---------- per-visitor preferences (remembered when storage allows) ---------- */

function makeFlag(key: string) {
  const listeners = new Set<() => void>();
  let memory = false;
  const read = () => {
    try {
      const v = window.localStorage.getItem(key);
      return v === null ? memory : v === "1";
    } catch {
      return memory;
    }
  };
  return {
    subscribe(cb: () => void) {
      listeners.add(cb);
      return () => {
        listeners.delete(cb);
      };
    },
    get: read,
    set(next: boolean) {
      memory = next;
      try {
        window.localStorage.setItem(key, next ? "1" : "0");
      } catch {
        /* storage blocked: still works for this visit */
      }
      listeners.forEach((l) => l());
    },
  };
}

const technicalFlag = makeFlag("ss-story-technical");

type Mode = "checking" | "motion" | "still";
let modeCache: Mode | null = null;
function currentMode(): Mode {
  if (modeCache) return modeCache;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  modeCache = reduce || window.innerWidth < 900 ? "still" : "motion";
  return modeCache;
}
const noSubscribe = () => () => {};

/* ---------- the camera: tilt to flat, then focus zooms, from absolute scroll ---------- */

type Cam = { s: number; x: number; y: number; rx: number };
// Where the camera rests at the END of each beat. Each beat holds its start (the previous end)
// for its first 20%, moves for 60%, and holds its end for the last 20%.
const CAM_START: Cam = { s: 0.9, x: 0, y: 3, rx: 16 };
const CAM_END: Record<Beat["id"], Cam> = {
  help: { s: 1, x: 0, y: 0, rx: 0 },
  left: { s: 1.06, x: -2.5, y: 0, rx: 0 },
  board: { s: 1, x: 0, y: 0, rx: 0 },
  ai: { s: 1.04, x: 1.5, y: -1, rx: 0 },
  proof: { s: 1.1, x: 0, y: -2, rx: 0 },
  start: { s: 1, x: 0, y: 0, rx: 0 },
};

function camStops(key: keyof Cam): { input: number[]; output: number[] } {
  const input: number[] = [0];
  const output: number[] = [CAM_START[key]];
  let prev = CAM_START[key];
  BEATS.forEach((b, i) => {
    const start = BEAT_STARTS[i] ?? 0;
    const len = b.vh / TOTAL_VH;
    const end = CAM_END[b.id][key];
    input.push(start + len * 0.2, start + len * 0.8);
    output.push(prev, end);
    prev = end;
  });
  input.push(1);
  output.push(prev);
  return { input, output };
}

function useCam(progress: MotionValue<number>, key: keyof Cam) {
  const { input, output } = camStops(key);
  const raw = useTransform(progress, input, output);
  return useSpring(raw, { stiffness: 140, damping: 26, mass: 0.6 });
}

/* ---------- pieces ---------- */

function TechSwitch({ technical }: { technical: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={technical}
      onClick={() => {
        technicalFlag.set(!technical);
        track("story_technical_view", { on: String(!technical) });
      }}
      className="inline-flex min-h-9 items-center gap-2.5 rounded-full border border-line bg-surface px-3 text-[13px] text-fg shadow-sm hover:border-fg/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
    >
      <span aria-hidden="true" className={`relative block h-5 w-9 shrink-0 overflow-hidden rounded-full transition-colors ${technical ? "bg-accent-solid" : "bg-line"}`}>
        <span className={`absolute left-0.5 top-0.5 block size-4 rounded-full bg-white shadow transition-transform ${technical ? "translate-x-4" : "translate-x-0"}`} />
      </span>
      <span className="whitespace-nowrap">{technical ? "Hide technical detail" : "Show technical detail"}</span>
    </button>
  );
}

function ReportChip({ upTo, technical, scope }: { upTo: number; technical: boolean; scope: Scope }) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      <span className="rounded-md bg-fg px-2 py-0.5 font-mono text-[11px] text-bg">
        {technical ? RUN.traceId : "Their report"}
      </span>
      <AnimatePresence initial={false}>
        {BEATS.slice(0, upTo + 1).map((b) => {
          const text = b.id === "ai" ? (technical ? `scope: ${scope}` : `AI gets: ${scope}`) : technical ? b.badge.technical : b.badge.plain;
          const tone =
            b.badge.tone === "bad" ? "border-bad/40 bg-bad/10 text-bad" : b.badge.tone === "ok" ? "border-accent/50 bg-accent/10 text-accent" : "border-line bg-bg text-muted";
          return (
            <motion.span
              key={b.id}
              layout
              initial={{ opacity: 0, scale: 0.85 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.85 }}
              transition={{ duration: 0.3 }}
              className={`rounded-md border px-2 py-0.5 text-[11px] font-medium ${tone}`}
            >
              {text}
            </motion.span>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

function Window({
  beat,
  index,
  t,
  technical,
  scope,
  setScope,
  interactive,
  still = false,
}: {
  beat: Beat;
  index: number;
  t: number;
  technical: boolean;
  scope: Scope;
  setScope: (s: Scope) => void;
  interactive: boolean;
  still?: boolean;
}) {
  const path =
    beat.id === "help" ? "bank.example / transfer" : beat.id === "left" ? "what left the browser" : beat.id === "start" ? "your terminal" : "stepstitch console";
  const view =
    beat.id === "help" ? <AppView t={t} technical={technical} />
    : beat.id === "left" ? <LeftView t={t} technical={technical} />
    : beat.id === "board" ? <BoardView t={t} technical={technical} />
    : beat.id === "ai" ? <AiView t={t} technical={technical} scope={scope} setScope={setScope} interactive={interactive} />
    : beat.id === "proof" ? <ProofView t={t} technical={technical} />
    : <StartView t={t} technical={technical} interactive={interactive} />;
  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-[0_1px_2px_rgba(24,24,27,0.06),0_30px_60px_-30px_rgba(24,24,27,0.35)]">
      <div className="flex items-center gap-3 border-b border-line px-4 py-2.5">
        <span className="flex gap-1.5" aria-hidden="true">
          <i className="size-2.5 rounded-full bg-line" />
          <i className="size-2.5 rounded-full bg-line" />
          <i className="size-2.5 rounded-full bg-line" />
        </span>
        <span className="font-mono text-[11.5px] text-muted">{path}</span>
      </div>
      <div className="border-b border-line px-4 py-2">
        <ReportChip upTo={index} technical={technical} scope={scope} />
      </div>
      {still ? (
        <div>{view}</div>
      ) : (
      <div className="relative min-h-0 flex-1">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={beat.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="absolute inset-0 overflow-hidden"
          >
            {view}
          </motion.div>
        </AnimatePresence>
      </div>
      )}
    </div>
  );
}

function Guide({ beat, technical }: { beat: Beat; technical: boolean }) {
  const copy = technical ? beat.technical : beat.plain;
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={`${beat.id}-${technical ? "t" : "p"}`}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.3 }}
        className="flex flex-col gap-3"
      >
        <h3 className={`text-balance text-[1.7rem] font-semibold leading-tight tracking-tight text-fg ${technical ? "font-mono text-[1.25rem]" : ""}`}>
          {copy.title}
        </h3>
        <p className="text-[15.5px] leading-relaxed text-muted">{copy.body}</p>
        <a
          href={`${GITHUB_URL}/blob/main/${beat.source}`}
          className="w-fit font-mono text-[11.5px] text-accent underline-offset-2 hover:underline"
        >
          Check it: {beat.source}
        </a>
      </motion.div>
    </AnimatePresence>
  );
}

/* ---------- the story ---------- */

export function StorySurface() {
  const mode = useSyncExternalStore(noSubscribe, currentMode, (): Mode => "checking");
  const technical = useSyncExternalStore(technicalFlag.subscribe, technicalFlag.get, () => false);
  const [scope, setScopeState] = useState<Scope>("repros");
  const setScope = (s: Scope) => {
    setScopeState(s);
    track("story_ai_scope", { scope: s });
  };

  if (mode === "motion") return <MotionStory technical={technical} scope={scope} setScope={setScope} />;
  return <StillStory technical={technical} scope={scope} setScope={setScope} />;
}

function MotionStory({ technical, scope, setScope }: { technical: boolean; scope: Scope; setScope: (s: Scope) => void }) {
  const wrapper = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: wrapper, offset: ["start start", "end end"] });
  const [pos, setPos] = useState({ index: 0, t: 0 });
  const reached = useRef(new Set<string>());

  useMotionValueEvent(scrollYProgress, "change", (p) => {
    const { index, local } = locate(p);
    const t = Math.round(local * 60) / 60;
    if (index !== pos.index || t !== pos.t) setPos({ index, t });
    const id = BEATS[index]?.id;
    if (id && !reached.current.has(id)) {
      reached.current.add(id);
      track("story_beat", { beat: id });
    }
  });

  const s = useCam(scrollYProgress, "s");
  const x = useCam(scrollYProgress, "x");
  const y = useCam(scrollYProgress, "y");
  const rx = useCam(scrollYProgress, "rx");
  const xPct = useTransform(x, (v) => `${v}%`);
  const yPct = useTransform(y, (v) => `${v}%`);

  const beat = BEATS[pos.index] ?? BEATS[0]!;

  return (
    <div style={LIGHT} className="bg-bg">
      <a href="#after-story" className="sr-only focus:not-sr-only focus:m-3 focus:inline-block focus:text-accent">
        Skip the story
      </a>
      <div ref={wrapper} style={{ height: `${TOTAL_VH + 100}vh` }} className="relative">
        <div className="sticky top-0 flex h-[100svh] items-center overflow-hidden">
          <div className="mx-auto grid w-full max-w-7xl grid-cols-[minmax(0,22rem)_minmax(0,1fr)] items-center gap-10 px-6 pt-16 xl:gap-14">
            <div className="flex flex-col gap-6">
              <ol className="flex flex-col gap-1.5" aria-label="Story steps">
                {BEATS.map((b, i) => (
                  <li key={b.id} className={`flex items-center gap-2.5 text-[13px] transition-colors ${i === pos.index ? "font-semibold text-fg" : i < pos.index ? "text-muted" : "text-muted/60"}`}>
                    <span aria-hidden="true" className={`h-px transition-all duration-300 ${i === pos.index ? "w-6 bg-accent-solid" : "w-3 bg-line"}`} />
                    {b.name}
                  </li>
                ))}
              </ol>
              <Guide beat={beat} technical={technical} />
              <TechSwitch technical={technical} />
            </div>
            <div className="[perspective:1600px]">
              <motion.div
                style={{ scale: s, x: xPct, y: yPct, rotateX: rx, transformOrigin: "50% 40%" }}
                className="h-[min(540px,66svh)] will-change-transform"
              >
                <Window beat={beat} index={pos.index} t={pos.t} technical={technical} scope={scope} setScope={setScope} interactive />
              </motion.div>
            </div>
          </div>
          <div className="pointer-events-none absolute inset-x-6 bottom-5 h-0.5 overflow-hidden rounded-full bg-line">
            <motion.div style={{ scaleX: scrollYProgress }} className="h-full origin-left bg-accent-solid" />
          </div>
        </div>
      </div>
      <ol className="sr-only">
        {BEATS.map((b) => (
          <li key={b.id}>
            {(technical ? b.technical : b.plain).title}. {(technical ? b.technical : b.plain).body}
          </li>
        ))}
      </ol>
      <div id="after-story" />
    </div>
  );
}

function StillStory({ technical, scope, setScope }: { technical: boolean; scope: Scope; setScope: (s: Scope) => void }) {
  return (
    <div style={LIGHT} className="rounded-3xl bg-bg px-4 py-8 sm:px-8">
      <div className="mb-8 flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-prose text-[14px] text-muted">Follow one customer&rsquo;s report from the moment it fails to a proven fix.</p>
        <TechSwitch technical={technical} />
      </div>
      <ol className="flex flex-col gap-12">
        {BEATS.map((b, i) => (
          <li key={b.id} className="grid gap-5 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:items-center">
            <Guide beat={b} technical={technical} />
            <Window beat={b} index={i} t={1} technical={technical} scope={scope} setScope={setScope} interactive={b.id === "ai" || b.id === "start"} still />
          </li>
        ))}
      </ol>
    </div>
  );
}
