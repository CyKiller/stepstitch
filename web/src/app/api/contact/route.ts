import { NextResponse } from "next/server";

type ContactBody = {
  name?: string;
  email?: string;
  org?: string;
  message?: string;
};

function valid(email: string): boolean {
  // Bound the input before the regex runs. The pattern has adjacent `[^\s@]+`
  // groups around the literal dot, so an unbounded adversarial string could
  // trigger polynomial backtracking (ReDoS, CWE-1333). 320 is the RFC 5321
  // maximum address length, so this rejects nothing a real email needs.
  if (email.length > 320) return false;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export async function POST(request: Request) {
  let body: ContactBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
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

  const summary = `Pilot enquiry from ${name} <${email}>${org ? ` (${org})` : ""}:\n${message}`;

  // Forward to a webhook if configured. The payload carries BOTH a `text`
  // field (Slack incoming webhooks render this) and structured fields (Zapier /
  // Google Sheets / generic relays consume these), so one URL fits any of them.
  const hook = process.env.CONTACT_WEBHOOK_URL;
  if (hook) {
    try {
      const res = await fetch(hook, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: summary,
          source: "stepstitch.dev/contact",
          name,
          email,
          org,
          message,
          submitted_at: new Date().toISOString(),
        }),
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
  } else {
    // No relay configured yet: log so the submission is at least captured.
    console.log("[contact]", { name, email, org, message });
  }

  return NextResponse.json({ ok: true });
}
