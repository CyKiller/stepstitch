import { Bezel } from "./bezel";

// A faithful, theme-aware mock of the console's pipeline board — the same pattern as
// <RedToGreen>, drawn in CSS/SVG rather than shipped as a screenshot. The site has no raster
// images anywhere and supports both themes; a dark screenshot on a light page would read as
// broken, and a PNG goes stale silently. Stage names and the glyph algorithm below are the real
// ones from server/dashboard.py, so this can drift out of date but it cannot drift into fiction.

// FNV-1a, byte-for-byte the console's hash32 — so a given fingerprint field yields the same
// shape and shade here as it does in the running console.
function hash32(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = (h + (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24)) >>> 0;
  }
  return h >>> 0;
}

const FP_KEYS = [
  "route",
  "diagnostic_type",
  "failing_status",
  "exception_type",
  "diagnostic_endpoint",
  "terminal_selector",
] as const;

type Fingerprint = Partial<Record<(typeof FP_KEYS)[number], string>>;

const SHADES = [
  "var(--accent)",
  "var(--accent-2)",
  "color-mix(in oklab, var(--accent) 55%, var(--fg))",
];

/** Six structural fields as a deterministic 3x2 mark. Null fields render hollow. */
function Glyph({ fp, size = 26 }: { fp: Fingerprint; size?: number }) {
  const cell = size / 3;
  const pad = cell * 0.18;
  const r = cell / 2 - pad;
  return (
    <svg
      width={size}
      height={(size * 2) / 3}
      viewBox={`0 0 ${size} ${(size * 2) / 3}`}
      aria-hidden
      className="shrink-0"
    >
      {FP_KEYS.map((key, i) => {
        const cx = (i % 3) * cell + cell / 2;
        const cy = Math.floor(i / 3) * cell + cell / 2;
        const raw = fp[key];
        if (!raw) {
          return (
            <circle
              key={key}
              cx={cx}
              cy={cy}
              r={r * 0.55}
              fill="none"
              stroke="var(--line)"
              strokeWidth={1}
            />
          );
        }
        const h = hash32(`${key}:${raw}`);
        const fill = SHADES[h % 3];
        switch ((h >> 3) % 4) {
          case 0:
            return <circle key={key} cx={cx} cy={cy} r={r} fill={fill} />;
          case 1:
            return (
              <rect
                key={key}
                x={cx - r}
                y={cy - r}
                width={r * 2}
                height={r * 2}
                rx={r * 0.32}
                fill={fill}
              />
            );
          case 2:
            return (
              <polygon
                key={key}
                points={`${cx},${cy - r} ${cx + r},${cy + r} ${cx - r},${cy + r}`}
                fill={fill}
              />
            );
          default:
            return (
              <rect
                key={key}
                x={cx - r}
                y={cy - r * 0.42}
                width={r * 2}
                height={r * 0.84}
                rx={r * 0.42}
                fill={fill}
              />
            );
        }
      })}
    </svg>
  );
}

const TRANSFER: Fingerprint = {
  route: "/accounts/:id/transfer",
  diagnostic_type: "api_error",
  failing_status: "500",
  diagnostic_endpoint: "/api/accounts/:id/transfers",
  terminal_selector: "[data-testid=review-transfer]",
};
const CHECKOUT: Fingerprint = {
  route: "/checkout",
  diagnostic_type: "api_error",
  failing_status: "422",
  diagnostic_endpoint: "/api/checkout/promo",
  terminal_selector: "[data-testid=apply-promo]",
};

// The real board columns, derived from the verdict state machine in verification/verdict.py.
const COLUMNS: {
  label: string;
  why: string;
  tone?: string;
  cards: { fp: Fingerprint; facts: string; seen?: string }[];
}[] = [
  {
    label: "Untriaged",
    why: "no CI result yet",
    cards: [],
  },
  {
    label: "Known shape",
    why: "you fixed this before",
    tone: "text-accent",
    cards: [
      {
        fp: { ...TRANSFER, terminal_selector: "[data-testid=confirm-transfer]" },
        facts: "HTTP 500 · 1 report",
        seen: "Seen before · PR-42 · 88% match",
      },
    ],
  },
  {
    label: "Reproduced",
    why: "red confirmed",
    cards: [{ fp: CHECKOUT, facts: "HTTP 422 · 1 report" }],
  },
  {
    label: "Fixed",
    why: "red to green",
    tone: "text-ok",
    cards: [{ fp: TRANSFER, facts: "HTTP 500 · 4 reports" }],
  },
];

export function ConsoleBoard() {
  return (
    <Bezel>
      <div className="overflow-x-auto">
        <div className="flex min-w-[640px] gap-3 p-4">
          {COLUMNS.map((col) => (
            <div key={col.label} className="min-w-0 flex-1">
              <div className="flex items-baseline gap-2">
                <p
                  className={`font-mono text-[10.5px] font-semibold uppercase tracking-[0.08em] ${col.tone ?? "text-muted"}`}
                >
                  {col.label}
                </p>
                <span className="font-mono text-[10.5px] tabular-nums text-muted">
                  {col.cards.length}
                </span>
              </div>
              <p className="mt-0.5 text-[10.5px] leading-tight text-muted">
                {col.why}
              </p>

              <div className="mt-3 space-y-2">
                {col.cards.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-line px-3 py-4 text-[11px] text-muted">
                    Nothing waiting.
                  </div>
                ) : (
                  col.cards.map((card) => (
                    <div
                      key={card.fp.terminal_selector}
                      className="rounded-xl border border-line bg-surface p-3"
                    >
                      <div className="flex items-center gap-2">
                        <Glyph fp={card.fp} />
                        <p className="truncate font-mono text-[11.5px] font-medium text-fg">
                          {card.fp.route}
                        </p>
                      </div>
                      <p className="mt-1.5 text-[11px] text-muted">
                        {card.facts}
                      </p>
                      {card.seen ? (
                        <p className="mt-1.5 text-[11px] text-accent">
                          {card.seen}
                        </p>
                      ) : null}
                    </div>
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
        <p className="border-t border-line px-4 py-2.5 font-mono text-[11px] text-muted">
          GET /dashboard · four reports of one bug are one card, not four rows
        </p>
      </div>
    </Bezel>
  );
}
