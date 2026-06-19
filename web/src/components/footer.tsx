import { GithubLogo, Package } from "@phosphor-icons/react/dist/ssr";
import { Wordmark } from "./wordmark";
import { GITHUB_URL, NPM_URL, DOCS_URL } from "@/lib/links";

const columns = [
  {
    title: "Product",
    links: [
      { href: "/#how", label: "How it works" },
      { href: "/#workflow", label: "Workflow" },
      { href: "/#demo", label: "Live demo" },
      { href: "/#compare", label: "Comparison" },
    ],
  },
  {
    title: "Developers",
    links: [
      { href: "/self-host", label: "Self-host" },
      { href: DOCS_URL, label: "Docs", external: true },
      { href: GITHUB_URL, label: "GitHub", external: true },
      { href: NPM_URL, label: "npm", external: true },
    ],
  },
  {
    title: "Trust",
    links: [
      { href: "/security", label: "Security & compliance" },
      {
        href: `${GITHUB_URL}/blob/main/COMPLIANCE-EVIDENCE.md`,
        label: "Compliance evidence",
        external: true,
      },
      {
        href: `${GITHUB_URL}/blob/main/LICENSE`,
        label: "Apache-2.0 license",
        external: true,
      },
    ],
  },
];

export function Footer() {
  return (
    <footer className="border-t border-line bg-bg">
      <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
        <div className="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div className="max-w-sm">
            <Wordmark />
            <p className="mt-3 text-sm leading-relaxed text-muted">
              Issue-to-repro infrastructure. Privacy-safe debugging evidence and
              reproducibility, not analytics.
            </p>
            <div className="mt-5 flex items-center gap-2">
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noreferrer"
                aria-label="GitHub"
                className="grid size-9 place-items-center rounded-full border border-line text-muted transition-colors hover:border-fg/30 hover:text-fg"
              >
                <GithubLogo size={16} weight="bold" />
              </a>
              <a
                href={NPM_URL}
                target="_blank"
                rel="noreferrer"
                aria-label="npm"
                className="grid size-9 place-items-center rounded-full border border-line text-muted transition-colors hover:border-fg/30 hover:text-fg"
              >
                <Package size={16} weight="bold" />
              </a>
            </div>
          </div>

          {columns.map((col) => (
            <div key={col.title}>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                {col.title}
              </p>
              <ul className="mt-3 space-y-2.5">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <a
                      href={l.href}
                      target={l.external ? "_blank" : undefined}
                      rel={l.external ? "noreferrer" : undefined}
                      className="text-sm text-muted transition-colors hover:text-fg"
                    >
                      {l.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-2 border-t border-line pt-6 text-xs text-muted sm:flex-row sm:items-center sm:justify-between">
          <p>Apache-2.0 licensed. Self-hosted.</p>
          <p>Structural evidence only. No screens, no input values, no PII.</p>
        </div>
      </div>
    </footer>
  );
}
