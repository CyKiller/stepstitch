import { NextResponse } from "next/server";

type ContactBody = {
  name?: string;
  email?: string;
  org?: string;
  message?: string;
  canary?: unknown;
};

function valid(email: string): boolean {
  // Bound the input before the regex runs. The pattern has adjacent `[^\s@]+`
  // groups around the literal dot, so an unbounded adversarial string could
  // trigger polynomial backtracking (ReDoS, CWE-1333). 320 is the RFC 5321
  // maximum address length, so this rejects nothing a real email needs.
  if (email.length > 320) return false;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

async function relay(hook: string, payload: Record<string, unknown>): Promise<NextResponse | null> {
  // Returns an error response, or null when the webhook accepted the payload.
  try {
    const res = await fetch(hook, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) {
      console.error("[contact] relay non-2xx", res.status);
      return NextResponse.json({ error: "relay_failed" }, { status: 502 });
    }
  } catch (err) {
    console.error("[contact] relay error", err);
    return NextResponse.json({ error: "relay_failed" }, { status: 502 });
  }
  return null;
}

export async function POST(request: Request) {
  let body: ContactBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const hook = process.env.CONTACT_WEBHOOK_URL;

  // Deploy-verification canary: proves the production relay path end to end
  // (env var present AND the webhook accepting) without a fabricated enquiry.
  // The payload is clearly labeled so the receiving channel can ignore it.
  if (body.canary === true) {
    if (!hook) {
      return NextResponse.json({ error: "relay_unconfigured" }, { status: 503 });
    }
    const failed = await relay(hook, {
      text: "[canary] stepstitch.dev contact relay check: not a real enquiry",
      source: "stepstitch.dev/contact",
      canary: true,
      submitted_at: new Date().toISOString(),
    });
    if (failed) return failed;
    return NextResponse.json({ ok: true, canary: true });
  }

  const name = (body.name ?? "").trim();
  const email = (body.email ?? "").trim();
  const message = (body.message ?? "").trim();
  const org = (body.org ?? "").trim();

  if (!name || !email || !message) {
    return NextResponse.json({ error: "missing_fields" }, { status: 400 });
  }
  if (!valid(email)) {
    return NextResponse.json({ error: "invalid_email" }, { status: 400 });
  }
  // Length caps so a webhook payload can't be abused as a giant relay.
  if (name.length > 200 || email.length > 320 || org.length > 200 || message.length > 4000) {
    return NextResponse.json({ error: "too_long" }, { status: 400 });
  }

  if (!hook) {
    // No relay configured: the submission has nowhere to go, and saying "ok"
    // here would show the visitor a success screen while their message was
    // discarded. Refuse honestly instead; the form tells them it did not send.
    // (PII stays out of logs: only the fact of the refusal is recorded.)
    console.warn(
      "[contact] CONTACT_WEBHOOK_URL is not set; refusing the submission rather than discarding it",
    );
    return NextResponse.json({ error: "relay_unconfigured" }, { status: 503 });
  }

  const summary = `Pilot enquiry from ${name} <${email}>${org ? ` (${org})` : ""}:\n${message}`;

  // The payload carries BOTH a `text` field (Slack incoming webhooks render
  // this) and structured fields (Zapier / Google Sheets / generic relays
  // consume these), so one URL fits any of them.
  const failed = await relay(hook, {
    text: summary,
    source: "stepstitch.dev/contact",
    name,
    email,
    org,
    message,
    submitted_at: new Date().toISOString(),
  });
  if (failed) return failed;

  return NextResponse.json({ ok: true });
}
