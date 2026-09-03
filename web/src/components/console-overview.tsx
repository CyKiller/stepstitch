import { Bezel } from "./bezel";

const days = [28, 42, 34, 58, 46, 72, 87];
const pages = [
  { route: "/accounts/:id/transfer", people: 41, failures: 3 },
  { route: "/checkout", people: 29, failures: 2 },
  { route: "/settings/billing", people: 17, failures: 1 },
];

export function ConsoleOverview() {
  return (
    <Bezel>
      <div className="bg-surface">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <p className="text-sm font-semibold text-fg">Overview</p>
            <p className="mt-0.5 text-xs text-muted">Committed synthetic dataset</p>
          </div>
          <span className="rounded-full border border-line px-2.5 py-1 font-mono text-[11px] text-muted">
            Last 24 hours
          </span>
        </div>

        <div className="grid gap-8 p-5 sm:p-7 lg:grid-cols-[1fr_1.1fr]">
          <div className="flex flex-col justify-center">
            <p className="max-w-lg text-3xl font-semibold leading-tight tracking-tight text-fg sm:text-4xl">
              6 failures are open. They affected 87 people.
            </p>
            <p className="mt-4 max-w-md text-sm leading-relaxed text-muted">
              Reports with the same structural fingerprint collapse into one
              failure, so the number reflects decisions to make, not tickets to
              triage.
            </p>
          </div>

          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line">
            {[
              ["Open failures", "6"],
              ["People affected", "87"],
              ["Ready to reproduce", "4"],
              ["Fixed and proven", "12"],
            ].map(([label, value]) => (
              <div key={label} className="bg-bg p-4 sm:p-5">
                <dt className="text-xs text-muted">{label}</dt>
                <dd className="mt-2 font-mono text-2xl font-semibold text-fg">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="grid border-t border-line lg:grid-cols-2">
          <div className="border-b border-line p-5 sm:p-7 lg:border-b-0 lg:border-r">
            <div className="flex items-baseline justify-between gap-4">
              <h3 className="text-sm font-semibold text-fg">People affected</h3>
              <span className="text-xs text-muted">7 days</span>
            </div>
            <div
              className="mt-6 flex h-32 items-end gap-2"
              role="img"
              aria-label="People affected increased from 28 to 87 over seven days"
            >
              {days.map((value, index) => (
                <div
                  key={`${value}-${index}`}
                  className="flex-1 rounded-t-md bg-accent-solid/70"
                  style={{ height: `${Math.round((value / 87) * 100)}%` }}
                />
              ))}
            </div>
          </div>

          <div className="p-5 sm:p-7">
            <h3 className="text-sm font-semibold text-fg">Worst-hit pages</h3>
            <div className="mt-4 divide-y divide-line border-y border-line">
              {pages.map((page) => (
                <div
                  key={page.route}
                  className="grid grid-cols-[1fr_auto] gap-4 py-3 text-sm"
                >
                  <div className="min-w-0">
                    <p className="truncate font-mono text-xs text-fg">
                      {page.route}
                    </p>
                    <p className="mt-1 text-xs text-muted">
                      {page.failures} grouped failures
                    </p>
                  </div>
                  <p className="font-mono text-xs text-muted">
                    {page.people} people
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </Bezel>
  );
}
