"use client";

import { useState } from "react";
import { track } from "@vercel/analytics";
import { ArrowRight, CheckCircle } from "@phosphor-icons/react";

type State = "idle" | "submitting" | "done" | "error" | "not_delivered";

export function Contact() {
  const [state, setState] = useState<State>("idle");

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setState("submitting");
    const form = new FormData(e.currentTarget);
    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.get("name"),
          email: form.get("email"),
          org: form.get("org"),
          message: form.get("message"),
        }),
      });
      // 502/503 mean the relay is down or unconfigured: the message was NOT
      // delivered, and the honest thing is to say so — never a success screen
      // over a discarded submission.
      if (res.status === 502 || res.status === 503) {
        setState("not_delivered");
        return;
      }
      if (!res.ok) throw new Error();
      track("contact_submit");
      setState("done");
    } catch {
      setState("error");
    }
  }

  return (
    <section id="contact" className="border-b border-line">
      <div className="mx-auto grid max-w-7xl gap-12 px-4 py-20 sm:px-6 md:grid-cols-2 md:py-28">
        <div className="flex flex-col justify-center">
          <h2 className="text-3xl font-semibold tracking-tight text-fg md:text-4xl">
            Book a pilot
          </h2>
          <p className="mt-4 max-w-md text-lg leading-relaxed text-muted">
            Self-host the open-source core today, or talk to us about a managed
            pilot with white-glove integration and a compliance packet for your
            reviewers.
          </p>
        </div>

        <div className="rounded-2xl border border-line bg-surface p-6 sm:p-8">
          {state === "done" ? (
            <div className="flex min-h-[280px] flex-col items-start justify-center">
              <CheckCircle size={32} weight="fill" className="text-ok" />
              <p className="mt-4 text-lg font-semibold text-fg">
                Thanks. We will be in touch.
              </p>
              <p className="mt-1 text-sm text-muted">
                Your message reached our team.
              </p>
            </div>
          ) : state === "not_delivered" ? (
            <div className="flex min-h-[280px] flex-col items-start justify-center">
              <p className="text-lg font-semibold text-fg">
                Your message was not sent.
              </p>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                Our contact relay is unavailable right now, so nothing was
                delivered — we would rather tell you that than show a success
                screen. Please reach us on{" "}
                <a
                  href="https://github.com/CyKiller/stepstitch/issues"
                  className="font-medium text-fg underline underline-offset-2"
                  target="_blank"
                  rel="noreferrer"
                >
                  GitHub
                </a>{" "}
                instead, or try again later.
              </p>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="grid gap-4">
              <Field label="Name" name="name" type="text" autoComplete="name" />
              <Field
                label="Work email"
                name="email"
                type="email"
                autoComplete="email"
              />
              <Field
                label="Organization"
                name="org"
                type="text"
                required={false}
                autoComplete="organization"
              />
              <div className="grid gap-2">
                <label
                  htmlFor="message"
                  className="text-sm font-medium text-fg"
                >
                  What are you trying to reproduce?
                </label>
                <textarea
                  id="message"
                  name="message"
                  required
                  rows={4}
                  className="resize-none rounded-lg border border-line bg-bg px-3.5 py-2.5 text-sm text-fg placeholder:text-muted focus:border-accent-solid focus:outline-none focus:ring-1 focus:ring-accent-solid"
                  placeholder="A sentence or two about your stack and the problem."
                />
              </div>

              {state === "error" && (
                <p className="text-sm text-bad">
                  Something went wrong. Please try again.
                </p>
              )}

              <button
                type="submit"
                disabled={state === "submitting"}
                className="group mt-1 inline-flex items-center justify-center gap-2.5 self-start rounded-full bg-accent-solid py-2 pl-5 pr-2 text-sm font-semibold text-accent-fg shadow-[var(--shadow-brand)] transition-transform duration-300 ease-[var(--ease-spring)] active:scale-[0.98] disabled:opacity-60"
              >
                {state === "submitting" ? "Sending" : "Book a pilot"}
                <span className="grid size-8 place-items-center rounded-full bg-black/15 transition-transform duration-300 ease-[var(--ease-spring)] group-hover:translate-x-0.5 group-hover:-translate-y-px dark:bg-black/25">
                  <ArrowRight size={15} weight="bold" />
                </span>
              </button>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}

function Field({
  label,
  name,
  type,
  autoComplete,
  required = true,
}: {
  label: string;
  name: string;
  type: string;
  autoComplete?: string;
  required?: boolean;
}) {
  return (
    <div className="grid gap-2">
      <label htmlFor={name} className="text-sm font-medium text-fg">
        {label}
        {!required && <span className="text-muted"> (optional)</span>}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        required={required}
        autoComplete={autoComplete}
        className="rounded-lg border border-line bg-bg px-3.5 py-2.5 text-sm text-fg placeholder:text-muted focus:border-accent-solid focus:outline-none focus:ring-1 focus:ring-accent-solid"
      />
    </div>
  );
}
