import { GithubLogo, Package } from "@phosphor-icons/react/dist/ssr";
import { Wordmark } from "./wordmark";
import { GITHUB_URL, NPM_URL } from "@/lib/links";

export function Footer() {
  return (
    <footer className="bg-bg">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6">
        <div className="flex flex-col gap-8 sm:flex-row sm:items-center sm:justify-between">
          <div className="max-w-sm">
            <Wordmark />
            <p className="mt-3 text-sm leading-relaxed text-muted">
              Issue-to-repro infrastructure. Privacy-safe debugging evidence and
              reproducibility, not analytics.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-fg transition-colors hover:border-fg/30"
            >
              <GithubLogo size={16} weight="bold" />
              GitHub
            </a>
            <a
              href={NPM_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-fg transition-colors hover:border-fg/30"
            >
              <Package size={16} weight="bold" />
              npm
            </a>
          </div>
        </div>

        <div className="mt-10 flex flex-col gap-2 border-t border-line pt-6 text-xs text-muted sm:flex-row sm:items-center sm:justify-between">
          <p>Apache-2.0 licensed. Self-hosted.</p>
          <p>Structural evidence only. No screens, no input values, no PII.</p>
        </div>
      </div>
    </footer>
  );
}
