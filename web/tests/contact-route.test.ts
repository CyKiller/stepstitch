import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { POST } from "@/app/api/contact/route";

const ORIGINAL_ENV = { ...process.env };

function makeRequest(body: string): Request {
  return new Request("http://localhost/api/contact", {
    method: "POST",
    body,
  });
}

function makeJsonRequest(payload: unknown): Request {
  return makeRequest(JSON.stringify(payload));
}

const validPayload = {
  name: "Ada Lovelace",
  email: "ada@example.com",
  org: "Analytical Engines",
  message: "We would like a pilot.",
};

beforeEach(() => {
  delete process.env.CONTACT_WEBHOOK_URL;
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  process.env = { ...ORIGINAL_ENV };
  delete process.env.CONTACT_WEBHOOK_URL;
});

describe("POST /api/contact validation", () => {
  it("returns 400 invalid_json for unparseable body", async () => {
    const res = await POST(makeRequest("{not json"));
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "invalid_json" });
  });

  it("returns 400 missing_fields when name/email/message are absent", async () => {
    const res = await POST(makeJsonRequest({ org: "only org" }));
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "missing_fields" });
  });

  it("returns 400 missing_fields when message is blank", async () => {
    const res = await POST(
      makeJsonRequest({ name: "A", email: "a@b.co", message: "   " }),
    );
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "missing_fields" });
  });

  it("returns 400 invalid_email for a malformed address", async () => {
    const res = await POST(
      makeJsonRequest({ name: "A", email: "not-an-email", message: "hi" }),
    );
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "invalid_email" });
  });

  it("rejects an over-long email quickly without ReDoS backtracking", async () => {
    // Adversarial input for the email regex: tens of thousands of `[^\s@]`
    // chars with no final match. Before the length guard this triggered
    // polynomial backtracking (CWE-1333); it must now short-circuit to 400.
    const pathological = "a".repeat(50_000) + "!";
    const started = performance.now();
    const res = await POST(
      makeJsonRequest({ name: "A", email: pathological, message: "hi" }),
    );
    const elapsedMs = performance.now() - started;

    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "invalid_email" });
    expect(elapsedMs).toBeLessThan(100);
  });

  it("returns 400 too_long when a field exceeds its cap", async () => {
    const res = await POST(
      makeJsonRequest({
        name: "A".repeat(201),
        email: "a@b.co",
        message: "hi",
      }),
    );
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "too_long" });
  });
});

describe("POST /api/contact without a webhook", () => {
  it("refuses with 503 relay_unconfigured instead of faking success", async () => {
    // The original behavior returned ok:true here — the visitor saw "your
    // message reached our team" while the submission was discarded. The route
    // must now refuse honestly so the form can say the message did not send.
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(makeJsonRequest(validPayload));
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ error: "relay_unconfigured" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("the canary also reports the missing relay as 503", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(makeJsonRequest({ canary: true }));
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ error: "relay_unconfigured" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("POST /api/contact canary", () => {
  const HOOK = "https://hooks.example.test/relay";

  it("relays a clearly-labeled canary payload and returns the real status", async () => {
    process.env.CONTACT_WEBHOOK_URL = HOOK;
    const fetchSpy = vi.fn(async () => ({ ok: true, status: 200 }) as Response);
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(makeJsonRequest({ canary: true }));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true, canary: true });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe(HOOK);
    const sent = JSON.parse(String(init.body));
    // The receiving channel must be able to tell this is not a real enquiry.
    expect(sent.canary).toBe(true);
    expect(sent.text).toContain("[canary]");
    expect(sent.text).toContain("not a real enquiry");
    // No fabricated personal fields ride along.
    expect(sent.name).toBeUndefined();
    expect(sent.email).toBeUndefined();
  });

  it("surfaces a failing webhook as 502 so the deploy check goes red", async () => {
    process.env.CONTACT_WEBHOOK_URL = HOOK;
    const fetchSpy = vi.fn(async () => ({ ok: false, status: 500 }) as Response);
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(makeJsonRequest({ canary: true }));
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "relay_failed" });
  });
});

describe("POST /api/contact with a webhook", () => {
  const HOOK = "https://hooks.example.test/relay";

  it("POSTs the structured payload to the exact webhook url and returns ok", async () => {
    process.env.CONTACT_WEBHOOK_URL = HOOK;
    const fetchSpy = vi.fn(async () => ({ ok: true, status: 200 }) as Response);
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(makeJsonRequest(validPayload));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe(HOOK);
    expect(init.method).toBe("POST");
    // JSON content type + a bounded abort signal are the abuse-mitigations
    // (don't let the relay hang / be content-sniffed); assert they don't regress.
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json",
    );
    expect(init.signal).toBeInstanceOf(AbortSignal);

    const sent = JSON.parse(String(init.body));
    expect(sent.text).toContain(validPayload.name);
    expect(sent.text).toContain(validPayload.email);
    expect(sent.name).toBe(validPayload.name);
    expect(sent.email).toBe(validPayload.email);
    expect(sent.org).toBe(validPayload.org);
    expect(sent.message).toBe(validPayload.message);
  });

  it("relays a non-2xx webhook response as 502 relay_failed", async () => {
    process.env.CONTACT_WEBHOOK_URL = HOOK;
    const fetchSpy = vi.fn(async () => ({ ok: false, status: 500 }) as Response);
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(makeJsonRequest(validPayload));
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "relay_failed" });
  });

  it("relays a thrown webhook error as 502 relay_failed", async () => {
    process.env.CONTACT_WEBHOOK_URL = HOOK;
    const fetchSpy = vi.fn(async () => {
      throw new Error("relay unreachable");
    });
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(makeJsonRequest(validPayload));
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "relay_failed" });
  });
});
