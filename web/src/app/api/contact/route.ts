import { NextResponse } from "next/server";

type ContactBody = {
  name?: string;
  email?: string;
  org?: string;
  message?: string;
};

function valid(email: string): boolean {
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

  // Forward to a webhook if configured (e.g. a Slack/email relay). Without one,
  // accept and log server-side so the form is functional before wiring a relay.
  const hook = process.env.CONTACT_WEBHOOK_URL;
  if (hook) {
    try {
      await fetch(hook, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `Pilot enquiry from ${name} <${email}>${org ? ` (${org})` : ""}:\n${message}`,
        }),
      });
    } catch {
      return NextResponse.json({ error: "relay_failed" }, { status: 502 });
    }
  } else {
    console.log("[contact]", { name, email, org, message });
  }

  return NextResponse.json({ ok: true });
}
