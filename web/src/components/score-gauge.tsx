"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import { useRef } from "react";
import { CountUp } from "./count-up";

// Circular gauge that sweeps to the replayability score on scroll-in, with the
// grade in the center. Communicates "this is a measured 0-1 result".
export function ScoreGauge({ score, grade }: { score: number; grade: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const reduce = useReducedMotion();

  const r = 52;
  const circumference = 2 * Math.PI * r;
  const offset = circumference * (1 - Math.max(0, Math.min(1, score)));
  const active = inView || reduce;

  return (
    <div ref={ref} className="relative grid size-32 shrink-0 place-items-center">
      <svg className="size-32 -rotate-90" viewBox="0 0 120 120" aria-hidden>
        <circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          stroke="var(--color-line)"
          strokeWidth="8"
        />
        <motion.circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          stroke="url(#gauge-grad)"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: reduce ? offset : circumference }}
          animate={{ strokeDashoffset: active ? offset : circumference }}
          transition={{ duration: 1.3, ease: [0.16, 1, 0.3, 1] }}
        />
        <defs>
          <linearGradient id="gauge-grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--color-accent)" />
            <stop offset="100%" stopColor="var(--color-accent-2)" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-4xl font-semibold text-fg">{grade}</span>
        <span className="font-mono text-xs tabular-nums text-muted">
          <CountUp to={score} decimals={2} />
        </span>
      </div>
    </div>
  );
}
