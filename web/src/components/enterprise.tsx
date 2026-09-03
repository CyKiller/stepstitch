import {
  Fingerprint,
  UserGear,
  FirstAid,
  Trash,
  Clock,
  MagnifyingGlass,
} from "@phosphor-icons/react/dist/ssr";
import type { Icon } from "@phosphor-icons/react";
import { Reveal } from "./reveal";
import { Section, SectionHeader } from "./section";

type Control = {
  icon: Icon;
  title: string;
  desc: string;
  proof: string;
};

// Each control maps to a real, named place in the open-source code: same
// proof-over-promises stance as the rest of the page. Verified against
// server/oidc.py, service/.../profiles.py, and the router endpoints.
const controls: Control[] = [
  {
    icon: Fingerprint,
    title: "SSO via any OIDC issuer",
    desc: "RS256 JWTs from any standards-compliant provider, with issuer, audience, and expiry enforced. Every action is attributed to the real person, not a shared admin.",
    proof: "server/oidc.py",
  },
  {
    icon: UserGear,
    title: "Least-privilege RBAC",
    desc: "Operators read evidence; only admins can deliver, delete, or purge. The destructive gate is a separate role, checked per request.",
    proof: "require_roles · require_destructive",
  },
  {
    icon: FirstAid,
    title: "Healthcare-strict / PHI profile",
    desc: "A profile where free text is dropped entirely and forbidden keys hard-reject the request (HTTP 422). A profile can only tighten the boundary, never loosen it.",
    proof: "profiles/healthcare-strict.json",
  },
  {
    icon: Trash,
    title: "Right to delete (GDPR / CCPA)",
    desc: "Delete every trace body for a user on request. The deletion itself is written to the audit log, so the erasure is provable.",
    proof: "DELETE /session/by-user/{id}",
  },
  {
    icon: Clock,
    title: "Split retention clocks",
    desc: "Trace bodies expire on a short clock; the audit trail is kept on a separate ~5-year clock for recordkeeping. A background job purges expired bodies automatically.",
    proof: "retention.py · retention_job.py",
  },
  {
    icon: MagnifyingGlass,
    title: "Reverse correlation lookup",
    desc: "Hold a ServiceNow or Salesforce ticket and resolve it straight back to the sanitized trace behind it. Closed-loop traceability for auditors.",
    proof: "GET /correlation/{id}/summary",
  },
];

export function Enterprise() {
  return (
    <Section id="enterprise" className="border-b border-line">
      <SectionHeader
        title="The controls your security team will ask for"
        body="SSO, role separation, data-subject deletion, and a PHI posture are built in and self-hosted, not reserved for a future enterprise add-on. Each one points at the open-source code that implements it."
      />

      {/* A bordered spec-sheet: a 2-col divided grid, distinct from the
          feature bento above it. */}
      <Reveal className="mt-12">
        <div className="overflow-hidden rounded-2xl border border-line bg-surface">
          <div className="grid sm:grid-cols-2">
            {controls.map((c, i) => {
              const Glyph = c.icon;
              return (
                <div
                  key={c.title}
                  className={`border-line p-6 md:p-7 ${
                    i % 2 === 0 ? "sm:border-r" : ""
                  } ${i >= 2 ? "border-t" : ""}`}
                >
                  <div className="flex items-center gap-2.5">
                    <Glyph size={18} weight="bold" className="text-accent" />
                    <h3 className="text-base font-semibold text-fg">
                      {c.title}
                    </h3>
                  </div>
                  <p className="mt-3 text-[15px] leading-relaxed text-muted">
                    {c.desc}
                  </p>
                  <p className="mt-4 font-mono text-[12px] text-accent/90">
                    {c.proof}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </Reveal>
    </Section>
  );
}
